"""Fetcher protocol and shared types.

Schema Contract A — the output of every fetcher, input to the processing pipeline.
All source types (YouTube, RSS, Substack, HN, arXiv, …) normalise to FetchedItem.
The pipeline is source-type-agnostic; it only sees FetchedItem.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class FetchedItem:
    """Schema Contract A: normalised output of any fetcher.

    Every field must be populated by the fetcher. Downstream pipeline stages
    must not infer missing metadata from content — the fetcher is responsible
    for the full contract.
    """

    id: str  # Stable dedup key — video ID, URL, or HN story ID
    title: str
    url: str
    content: str  # Full text from the source (cleaned of markup by the fetcher)
    source_name: str  # Human-readable source label, e.g. "Anthropic Blog"
    source_type: (
        str  # Fetcher category: "youtube" | "rss" | "substack" | "hackernews" | "arxiv" | …
    )
    source_class: (
        str  # Credibility class: "primary" | "operator" | "practitioner" | "media" | "market"
    )
    author: str = ""  # Author name where available; empty string when not provided by the source
    published: datetime | None = None
    has_code: bool = False  # True when item links directly to a code repository
    evidence_type: str = ""  # "experiment" | "benchmark" | "anecdote" | "announcement" | "analysis"

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-serialisable dict for raw data persistence."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "source_class": self.source_class,
            "author": self.author,
            "published": self.published.isoformat() if self.published else None,
            "has_code": self.has_code,
            "evidence_type": self.evidence_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FetchedItem:
        """Deserialise from a dict produced by to_dict()."""
        published = None
        if d.get("published"):
            with suppress(ValueError):
                published = datetime.fromisoformat(d["published"])
        return cls(
            id=d["id"],
            title=d["title"],
            url=d["url"],
            content=d["content"],
            source_name=d["source_name"],
            source_type=d.get("source_type", ""),
            source_class=d.get("source_class", "practitioner"),
            author=d.get("author", ""),
            published=published,
            has_code=d.get("has_code", False),
            evidence_type=d.get("evidence_type", ""),
        )


@runtime_checkable
class Fetcher(Protocol):
    """Interface every source fetcher must implement."""

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        """Return new items, excluding any ID present in already_processed."""
        ...
