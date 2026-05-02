"""Stage 4 — Theme Classification.

Calls Gemini to assign a 1–3 word theme label and a canonical domain.

Expected response format:
  THEME: agentic RAG
  DOMAIN: agents
"""

from __future__ import annotations

import dataclasses
import logging

from src.models import Domain, ProcessedItem

logger = logging.getLogger(__name__)

_VALID_DOMAINS: set[str] = {
    "multimodal", "agents", "infra", "reasoning",
    "safety", "evals", "data", "hardware", "general", "unknown",
}

_SYSTEM_PROMPT = (
    "You are a technical analyst classifying AI content into themes.\n"
    "Return exactly two lines:\n"
    "  THEME: a 1–3 word descriptive label (e.g. 'agentic RAG', 'inference scaling')\n"
    "  DOMAIN: one of multimodal | agents | infra | reasoning | safety | evals | data | hardware | general | unknown\n"
    "No other text."
)


def _parse_response(text: str) -> tuple[str, Domain]:
    theme = ""
    domain: Domain = "unknown"

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("THEME:"):
            theme = line.split(":", 1)[1].strip()
        elif line.upper().startswith("DOMAIN:"):
            raw = line.split(":", 1)[1].strip().lower()
            if raw in _VALID_DOMAINS:
                domain = raw  # type: ignore[assignment]

    return theme, domain


def classify_theme(item: ProcessedItem, client) -> ProcessedItem:
    """Return item with theme and domain populated."""
    content = item.cleaned_content or item.title
    context = ""
    if item.concepts:
        context = f"\nConcepts: {', '.join(item.concepts)}"
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Title: {item.title}{context}\n\nContent: {content[:2000]}",
            config={"system_instruction": _SYSTEM_PROMPT, "max_output_tokens": 100},
        )
        theme, domain = _parse_response(response.text)
    except Exception as exc:
        logger.warning("Theme classification failed for %r: %s", item.id, exc)
        theme, domain = "", "unknown"

    return dataclasses.replace(item, theme=theme, domain=domain)
