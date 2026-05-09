"""Stage 3-6 combined — AI enrichment in a single Gemini call.

Replaces the four separate calls (concept_extraction, theme_classification,
summary_extraction, media_id) with one combined prompt.  This cuts API
requests from 4 per item to 1 per item and eliminates most of the 429
pressure on the Gemini free tier.

Returns the item with all AI fields populated, plus an enrichment_ok flag
(True if the call succeeded, False if it failed and defaults were used).

Retry behaviour is handled by src.retry.with_backoff in src/pipeline/run.py.
This stage performs one enrichment attempt and returns (item, ok). The
_RateLimiter in run.py still paces calls to ≤5 RPM so most 429s never occur.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Protocol

from google.genai import types
from google.genai.types import FinishReason

from src.models import Domain, ImpactVector, ProcessedItem

logger = logging.getLogger(__name__)

_VALID_IMPACTS: frozenset[str] = frozenset(
    {"cost", "latency", "capability", "safety", "adoption", "unknown"}
)
_VALID_DOMAINS: frozenset[str] = frozenset(
    {"multimodal", "agents", "infra", "reasoning", "safety", "evals",
     "data", "hardware", "general", "unknown"}
)

_SYSTEM_PROMPT = """\
You are an AI content analyst.  Given an article title and content, return \
structured analysis in EXACTLY this format — one field per line, no extra text:

CONCEPTS: comma-separated key entities, techniques, or methods (max 5)
ACTORS: comma-separated organisations or people named (max 5, or 'none')
IMPACT: one of cost | latency | capability | safety | adoption | unknown
THEME: a 1–3 word descriptive label (e.g. 'agentic RAG', 'inference scaling')
DOMAIN: one of multimodal | agents | infra | reasoning | safety | evals | data | hardware | general | unknown
SUMMARY: 2–3 sentence factual summary of the key finding, method, or announcement
MARKETING: true or false  (is this primarily promotional content rather than substantive technical analysis?)
CONFIDENCE: a float 0.0–1.0  (confidence in the MARKETING assessment)"""


class GenerativeModel(Protocol):
    """Minimal interface required from the Gemini client.

    Defining the Protocol here (DIP) lets callers depend on this abstraction
    rather than on the concrete google.genai.Client.  Tests can pass any object
    with a models.generate_content method; production code passes the real client.
    """

    class _Models(Protocol):
        def generate_content(
            self,
            model: str,
            contents: str,
            config: types.GenerateContentConfig,
        ) -> object: ...

    models: _Models


def _parse(text: str, item_id: str) -> dict:
    """Parse the combined response into a field dict."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip().upper()] = val.strip()

    def _get(key: str) -> str:
        return fields.get(key, "")

    concepts_raw = _get("CONCEPTS")
    concepts = [c.strip() for c in concepts_raw.split(",")
                if c.strip() and c.strip().lower() != "none"] if concepts_raw else []
    if not concepts_raw:
        logger.debug("enrich: missing CONCEPTS for %r — defaulting to []", item_id)

    actors_raw = _get("ACTORS")
    actors = [a.strip() for a in actors_raw.split(",")
               if a.strip() and a.strip().lower() != "none"] if actors_raw else []
    if not actors_raw:
        logger.debug("enrich: missing ACTORS for %r — defaulting to []", item_id)

    impact_raw = _get("IMPACT").lower()
    impact: ImpactVector = impact_raw if impact_raw in _VALID_IMPACTS else "unknown"  # type: ignore[assignment]
    if impact_raw and impact_raw not in _VALID_IMPACTS:
        logger.debug("enrich: unrecognised IMPACT %r for %r — defaulting to 'unknown'", impact_raw, item_id)
    elif not impact_raw:
        logger.debug("enrich: missing IMPACT for %r — defaulting to 'unknown'", item_id)

    theme = _get("THEME")
    if not theme:
        logger.debug("enrich: missing THEME for %r — response: %r", item_id, text[:200])

    domain_raw = _get("DOMAIN").lower()
    domain: Domain = domain_raw if domain_raw in _VALID_DOMAINS else "unknown"  # type: ignore[assignment]
    if domain_raw and domain_raw not in _VALID_DOMAINS:
        logger.debug("enrich: unrecognised DOMAIN %r for %r — defaulting to 'unknown'", domain_raw, item_id)
    elif not domain_raw:
        logger.debug("enrich: missing DOMAIN for %r — defaulting to 'unknown'", item_id)

    summary = _get("SUMMARY")
    if not summary:
        logger.debug("enrich: missing SUMMARY for %r — defaulting to ''", item_id)

    marketing_raw = _get("MARKETING").lower()
    is_marketing = marketing_raw == "true"
    if not marketing_raw:
        logger.debug("enrich: missing MARKETING for %r — defaulting to False", item_id)

    try:
        confidence = max(0.0, min(1.0, float(_get("CONFIDENCE"))))
    except ValueError:
        logger.debug("enrich: non-float CONFIDENCE for %r — defaulting to 0.0", item_id)
        confidence = 0.0
    if not _get("CONFIDENCE"):
        logger.debug("enrich: missing CONFIDENCE for %r — defaulting to 0.0", item_id)

    return {
        "concepts": concepts,
        "actors": actors,
        "impact_vector": impact,
        "theme": theme,
        "domain": domain,
        "summary": summary,
        "is_marketing": is_marketing,
        "marketing_confidence": confidence,
    }


def enrich(
    item: ProcessedItem,
    client: GenerativeModel,
    max_output_tokens: int = 500,
) -> tuple[ProcessedItem, bool]:
    """Run combined AI enrichment; return (enriched_item, ok).

    ok is False when the API call fails for this attempt. The item is returned
    with default values so the pipeline can continue.

    Retry behaviour is handled by the caller (process() in run.py) via
    src.retry.with_backoff.

    Only google.genai transport errors (ClientError, ServerError) are caught.
    Programming errors (AttributeError, TypeError, etc.) propagate so they are
    not silently swallowed as enrichment failures.
    """
    content = item.cleaned_content or item.title
    prompt = (
        f"Title: {item.title}\n"
        f"Source: {item.source_name} (class: {item.source_class})\n\n"
        f"Content: {content[:5000]}"
    )
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT,
        max_output_tokens=max_output_tokens,
        # Disable thinking for structured extraction — this task needs format
        # adherence, not chain-of-thought reasoning. With thinking enabled,
        # gemini-2.5-flash thinking tokens compete for the max_output_tokens
        # budget, truncating the structured response (finish_reason=MAX_TOKENS)
        # and leaving items unenriched. Setting thinking_budget=0 keeps the
        # full output budget for the 8-line structured format.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )
    # finish_reason must be STOP before accessing response.text — other
    # reasons (SAFETY, MAX_TOKENS, RECITATION) mean the response is unusable.
    # Log the actual finish_reason so failures are diagnosable in pipeline logs.
    if not response.candidates:
        logger.warning("AI enrichment for %r returned no candidates — using defaults", item.id)
        return item, False
    candidate = response.candidates[0]
    finish_reason = candidate.finish_reason
    if finish_reason != FinishReason.STOP:
        logger.warning(
            "AI enrichment for %r: finish_reason=%r (expected STOP) — using defaults. "
            "If reason is MAX_TOKENS, increase enrich_max_output_tokens in sources.yaml. "
            "If reason is SAFETY, the content was blocked.",
            item.id, finish_reason.name if hasattr(finish_reason, 'name') else finish_reason,
        )
        return item, False
    parsed = _parse(response.text, item.id)
    return dataclasses.replace(item, **parsed), True
