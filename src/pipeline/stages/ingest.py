"""Stage 1 — Ingest / Validate.

Converts a FetchedItem into a ProcessedItem, setting fetch_date.
All FetchedItem fields are carried over unchanged.
"""

from __future__ import annotations

from src.fetchers import FetchedItem
from src.models import ProcessedItem


def ingest(item: FetchedItem, fetch_date: str) -> ProcessedItem:
    """Return a ProcessedItem with all FetchedItem fields copied and fetch_date set."""
    return ProcessedItem(
        id=item.id,
        title=item.title,
        url=item.url,
        source_name=item.source_name,
        source_type=item.source_type,
        source_class=item.source_class,
        author=item.author,
        published=item.published,
        has_code=item.has_code,
        evidence_type=item.evidence_type,
        fetch_date=fetch_date,
    )
