"""Stage 3-6 combined — AI enrichment in a single Gemini call.

Replaces the four separate calls (concept_extraction, theme_classification,
summary_extraction, media_id) with one combined prompt.  This cuts API
requests from 4 per item to 1 per item and eliminates most of the 429
pressure on the Gemini free tier.

Returns the item with all AI fields populated, plus an enrichment_ok flag
(True if the call succeeded, False if it failed and defaults were used).
"""

from __future__ import annotations

import dataclasses
import logging

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

    actors_raw = _get("ACTORS")
    actors = [a.strip() for a in actors_raw.split(",")
               if a.strip() and a.strip().lower() != "none"] if actors_raw else []

    impact_raw = _get("IMPACT").lower()
    impact: ImpactVector = impact_raw if impact_raw in _VALID_IMPACTS else "unknown"  # type: ignore[assignment]

    theme = _get("THEME")

    domain_raw = _get("DOMAIN").lower()
    domain: Domain = domain_raw if domain_raw in _VALID_DOMAINS else "unknown"  # type: ignore[assignment]

    summary = _get("SUMMARY")

    marketing_raw = _get("MARKETING").lower()
    is_marketing = marketing_raw == "true"

    try:
        confidence = max(0.0, min(1.0, float(_get("CONFIDENCE"))))
    except ValueError:
        confidence = 0.0

    if not theme:
        logger.debug("enrich: missing THEME for %r — response: %r", item_id, text[:200])

    return dict(
        concepts=concepts,
        actors=actors,
        impact_vector=impact,
        theme=theme,
        domain=domain,
        summary=summary,
        is_marketing=is_marketing,
        marketing_confidence=confidence,
    )


def enrich(item: ProcessedItem, client) -> tuple[ProcessedItem, bool]:
    """Run combined AI enrichment; return (enriched_item, ok).

    ok is False when the API call fails; the item is returned with default
    values so the pipeline can continue and the caller can count failures.
    """
    content = item.cleaned_content or item.title
    prompt = (
        f"Title: {item.title}\n"
        f"Source: {item.source_name} (class: {item.source_class})\n\n"
        f"Content: {content[:5000]}"
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"system_instruction": _SYSTEM_PROMPT, "max_output_tokens": 500},
        )
        parsed = _parse(response.text, item.id)
        return dataclasses.replace(item, **parsed), True
    except Exception as exc:
        logger.warning("AI enrichment failed for %r: %s", item.id, exc)
        return item, False
