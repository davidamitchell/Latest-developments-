"""Stage 3 — Concept Extraction.

Calls Gemini to extract key concepts, actors, and the primary impact vector
from the cleaned content.

Expected response format (one key per line):
  CONCEPTS: term one, term two, term three
  ACTORS: Org A, Person B
  IMPACT: capability
"""

from __future__ import annotations

import dataclasses
import logging

from src.models import ImpactVector, ProcessedItem

logger = logging.getLogger(__name__)

_VALID_IMPACTS: set[str] = {"cost", "latency", "capability", "safety", "adoption", "unknown"}

_SYSTEM_PROMPT = (
    "You are a technical analyst extracting structured metadata from AI research content.\n"
    "Return exactly three lines:\n"
    "  CONCEPTS: comma-separated key entities, techniques, or methods (max 5)\n"
    "  ACTORS: comma-separated organisations or people named (max 5, or 'none')\n"
    "  IMPACT: one of cost | latency | capability | safety | adoption | unknown\n"
    "No other text."
)


def _parse_response(text: str) -> tuple[list[str], list[str], ImpactVector]:
    concepts: list[str] = []
    actors: list[str] = []
    impact: ImpactVector = "unknown"

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("CONCEPTS:"):
            raw = line.split(":", 1)[1].strip()
            concepts = [
                c.strip() for c in raw.split(",") if c.strip() and c.strip().lower() != "none"
            ]
        elif line.upper().startswith("ACTORS:"):
            raw = line.split(":", 1)[1].strip()
            actors = [
                a.strip() for a in raw.split(",") if a.strip() and a.strip().lower() != "none"
            ]
        elif line.upper().startswith("IMPACT:"):
            raw = line.split(":", 1)[1].strip().lower()
            if raw in _VALID_IMPACTS:
                impact = raw  # type: ignore[assignment]

    return concepts, actors, impact


def extract_concepts(item: ProcessedItem, client) -> ProcessedItem:
    """Return item with concepts, actors, and impact_vector populated."""
    content = item.cleaned_content or item.title
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Title: {item.title}\n\nContent: {content[:4000]}",
            config={"system_instruction": _SYSTEM_PROMPT, "max_output_tokens": 200},
        )
        concepts, actors, impact = _parse_response(response.text)
    except Exception as exc:
        logger.warning("Concept extraction failed for %r: %s", item.id, exc)
        concepts, actors, impact = [], [], "unknown"

    return dataclasses.replace(item, concepts=concepts, actors=actors, impact_vector=impact)
