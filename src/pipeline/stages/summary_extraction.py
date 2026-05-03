"""Stage 5 — Summary Extraction.

Calls Gemini to produce a 2–3 sentence factual summary of the item.
"""

from __future__ import annotations

import dataclasses
import logging

from src.models import ProcessedItem

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a technical writer producing concise, factual summaries of AI research and news.\n"
    "Write 2–3 sentences that summarise the key finding, method, or announcement.\n"
    "Ground all claims in the source material. Do not add opinions or filler phrases.\n"
    "Return only the summary — no labels, no headers."
)


def extract_summary(item: ProcessedItem, client) -> ProcessedItem:
    """Return item with summary populated."""
    content = item.cleaned_content or item.title
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Title: {item.title}\nSource: {item.source_name}\n\nContent: {content[:6000]}",
            config={"system_instruction": _SYSTEM_PROMPT, "max_output_tokens": 300},
        )
        summary = response.text.strip()
    except Exception as exc:
        logger.warning("Summary extraction failed for %r: %s", item.id, exc)
        summary = ""

    return dataclasses.replace(item, summary=summary)
