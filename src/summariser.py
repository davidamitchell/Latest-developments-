"""Anthropic Claude summarisation, with a plain link-digest fallback."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import anthropic

from src.config import SummaryConfig
from src.fetchers import FetchedItem

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "Summarise the following AI/ML content for a senior software engineer who follows"
    " the space closely. Be concise and technical. For each item, write 2–4 sentences:"
    " what it is, why it matters, one concrete takeaway if there is one."
)

_ITEM_HEADER = "### {title}\nSource: {source}\nURL: {url}\n\n"


def _digest_header(today: date) -> str:
    return f"Daily AI Digest — {today.strftime('%d %b %Y')}\n{'=' * 40}\n\n"


def format_link_digest(
    items: list[FetchedItem], config: SummaryConfig, today: date | None = None
) -> str:
    """Plain link-list digest — no AI required."""
    if not items:
        return ""

    if today is None:
        today = datetime.now(UTC).date()

    by_source: dict[str, list[FetchedItem]] = {}
    for item in items:
        by_source.setdefault(item.source_name, []).append(item)

    sections: list[str] = []
    for source, source_items in by_source.items():
        capped = source_items[: config.max_items_per_source]
        block = f"## {source}\n\n"
        for item in capped:
            pub = f" ({item.published.strftime('%d %b')})" if item.published else ""
            block += f"- {item.title}{pub}\n  {item.url}\n"
        sections.append(block.strip())

    return _digest_header(today) + "\n\n".join(sections)


def summarise(items: list[FetchedItem], config: SummaryConfig, today: date | None = None) -> str:
    """
    Return a formatted plain-text digest.

    If config.enabled is False, returns a plain link list without calling Claude.
    Otherwise groups items by source, sends to Claude, and returns the AI summary.
    Items are truncated at 12,000 chars before reaching this function by the fetcher.
    """
    if not items:
        return ""

    if not config.enabled:
        logger.info("AI summarisation disabled — producing link digest")
        return format_link_digest(items, config, today)

    if today is None:
        today = datetime.now(UTC).date()

    by_source: dict[str, list[FetchedItem]] = {}
    for item in items:
        by_source.setdefault(item.source_name, []).append(item)

    sections: list[str] = []
    for source, source_items in by_source.items():
        capped = source_items[: config.max_items_per_source]
        block = f"## {source}\n\n"
        for item in capped:
            block += _ITEM_HEADER.format(title=item.title, source=source, url=item.url)
            block += item.content + "\n\n"
        sections.append(block.strip())

    user_content = "\n\n---\n\n".join(sections)
    system_prompt = config.prompt.strip() or _DEFAULT_PROMPT

    logger.info("Summarising %d item(s) with %s", len(items), config.model)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    summary = response.content[0].text
    return _digest_header(today) + summary
