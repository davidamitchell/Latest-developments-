"""Stage 6 — Media / Marketing Identification.

Calls Gemini to determine whether an item is primarily marketing or promotional
content rather than substantive technical content.

Expected response format:
  MARKETING: true|false
  CONFIDENCE: 0.0–1.0
"""

from __future__ import annotations

import dataclasses
import logging

from src.models import ProcessedItem

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a content analyst identifying marketing and promotional material.\n"
    "Determine whether this item is primarily marketing/promotional content "
    "(product announcements, sales pitches, sponsored content, hype-driven pieces) "
    "rather than substantive technical content (research, analysis, tutorials, benchmarks).\n"
    "Return exactly two lines:\n"
    "  MARKETING: true or false\n"
    "  CONFIDENCE: a float between 0.0 and 1.0\n"
    "No other text."
)


def _parse_response(text: str) -> tuple[bool, float]:
    is_marketing = False
    confidence = 0.0

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("MARKETING:"):
            raw = line.split(":", 1)[1].strip().lower()
            is_marketing = raw == "true"
        elif line.upper().startswith("CONFIDENCE:"):
            raw = line.split(":", 1)[1].strip()
            try:
                confidence = max(0.0, min(1.0, float(raw)))
            except ValueError:
                confidence = 0.0

    return is_marketing, confidence


def identify_marketing(item: ProcessedItem, client) -> ProcessedItem:
    """Return item with is_marketing and marketing_confidence populated."""
    content = item.cleaned_content or item.title
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"Title: {item.title}\n"
                f"Source: {item.source_name} (class: {item.source_class})\n\n"
                f"Content: {content[:3000]}"
            ),
            config={"system_instruction": _SYSTEM_PROMPT, "max_output_tokens": 50},
        )
        is_marketing, confidence = _parse_response(response.text)
    except Exception as exc:
        logger.warning("Marketing identification failed for %r: %s", item.id, exc)
        is_marketing, confidence = False, 0.0

    return dataclasses.replace(item, is_marketing=is_marketing, marketing_confidence=confidence)
