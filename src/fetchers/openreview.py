"""OpenReview fetcher — trend pipeline only.

Fetches accepted papers from top ML venues (ICLR, NeurIPS, ICML) via the
OpenReview public API. Source class: primary; evidence_type: experiment.
Peer-reviewed acceptance represents the highest-quality primary signal.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime

import httpx

from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_API_URL = "https://api2.openreview.net/notes"

_HEADERS = {
    "User-Agent": "latest-developments-bot/1.0",
    "Accept": "application/json",
}

_MAX_CONTENT_CHARS = 8_000


class OpenReviewFetcher:
    """Fetch accepted papers from OpenReview venues."""

    def __init__(self, venues: list[str], limit: int = 25) -> None:
        self._venues = venues
        self._limit = limit

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        if not self._venues:
            return []

        all_items: list[FetchedItem] = []
        for venue in self._venues:
            try:
                items = with_backoff(lambda v=venue: self._fetch_venue(v, already_processed))
                all_items.extend(items)
            except Exception as exc:
                logger.warning("OpenReview fetch for venue %r failed: %s", venue, exc)

        logger.info(
            "OpenReview: %d paper(s) fetched across %d venue(s)", len(all_items), len(self._venues)
        )
        return all_items

    def _fetch_venue(self, venue: str, already_processed: set[str]) -> list[FetchedItem]:
        params: dict[str, str | int] = {
            "details": "replyCount",
            "offset": 0,
            "limit": self._limit,
            "invitation": venue,
        }
        response = httpx.get(_API_URL, params=params, headers=_HEADERS, timeout=30)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            logger.warning("OpenReview API returned unexpected format for venue %r", venue)
            return []

        notes = data.get("notes", [])
        if not isinstance(notes, list):
            logger.warning(
                "OpenReview API: 'notes' field missing or not a list for venue %r", venue
            )
            return []

        items: list[FetchedItem] = []
        for note in notes:
            try:
                item = self._parse_note(note, venue, already_processed)
            except Exception as exc:
                logger.warning("Skipping OpenReview note due to error: %s", exc)
                continue
            if item is not None:
                items.append(item)

        logger.debug("OpenReview venue %r: %d item(s)", venue, len(items))
        return items

    def _parse_note(
        self,
        note: dict,
        venue: str,
        already_processed: set[str],
    ) -> FetchedItem | None:
        note_id = note.get("id", "") or ""
        if not note_id:
            return None

        url = f"https://openreview.net/forum?id={note_id}"
        norm_url = url.rstrip("/")

        if norm_url in already_processed:
            return None

        content = note.get("content", {}) or {}

        # OpenReview stores content values as {"value": "..."} dicts in v2 API
        def _val(field: str) -> str:
            raw = content.get(field, "")
            if isinstance(raw, dict):
                return str(raw.get("value", ""))
            return str(raw) if raw else ""

        title = _val("title") or "Untitled"
        abstract = _val("abstract") or ""
        authors_raw = content.get("authors", [])
        if isinstance(authors_raw, dict):
            authors_raw = authors_raw.get("value", [])
        authors = authors_raw if isinstance(authors_raw, list) else []

        content_parts = [f"Title: {title}"]
        if authors:
            content_parts.append(f"Authors: {', '.join(str(a) for a in authors[:5])}")
        content_parts.append(f"Venue: {_venue_label(venue)}")
        if abstract:
            content_parts.append(f"Abstract: {abstract}")

        text = "\n".join(content_parts)[:_MAX_CONTENT_CHARS]

        pub_date: datetime | None = None
        tcdate = note.get("tcdate") or note.get("cdate")
        if tcdate:
            with contextlib.suppress((ValueError, TypeError)):
                # OpenReview timestamps are milliseconds since epoch
                pub_date = datetime.utcfromtimestamp(int(tcdate) / 1000)

        return FetchedItem(
            id=norm_url,
            title=title,
            url=norm_url,
            content=text,
            source_name="OpenReview",
            source_type="OpenReview",
            source_class="primary",
            published=pub_date,
            evidence_type="experiment",
        )


def _venue_label(invitation: str) -> str:
    """Return a human-readable venue label from an OpenReview invitation string."""
    _known: dict[str, str] = {
        "ICLR.cc": "ICLR 2025",
        "NeurIPS.cc": "NeurIPS 2025",
        "ICML.cc": "ICML 2025",
    }
    for prefix, label in _known.items():
        if prefix in invitation:
            return label
    return invitation
