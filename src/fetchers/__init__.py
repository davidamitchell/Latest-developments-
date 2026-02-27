"""Fetcher protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class FetchedItem:
    """A single piece of content ready for summarisation."""

    id: str  # Stable unique identifier — video ID, URL, or HN story ID
    title: str
    url: str
    content: str  # Full text content
    source_name: str  # Display name shown in the digest
    published: datetime | None = None
    source_type: str = ""  # e.g. "YouTube", "Hacker News", "RSS", "Substack"


@runtime_checkable
class Fetcher(Protocol):
    """Interface all source fetchers must implement."""

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        """Return new items, excluding any ID present in already_processed."""
        ...
