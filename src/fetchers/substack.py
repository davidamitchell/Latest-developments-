"""Substack fetcher.

Reads Substack publications using the internal JSON API
(https://<slug>.substack.com/api/v1/archive), which is less likely to be
blocked by Cloudflare than the RSS feed.  Falls back to the RSS feed if the
JSON API returns a non-retriable HTTP error.

Deduplication key: the canonical post URL, normalised (trailing slash stripped).
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from src.config import SubstackConfig, SubstackPublication
from src.fetchers import FetchedItem
from src.fetchers.rss import _normalise_url, _parse_entries
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 12_000
_API_LIMIT = 12

# Reuse the same browser-like headers from the RSS fetcher to avoid bot detection.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


class _PermanentHTTPError(Exception):
    """4xx HTTP error that will not improve on retry."""


class SubstackFetcher:
    def __init__(self, config: SubstackConfig) -> None:
        self._config = config

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        if not self._config.enabled or not self._config.publications:
            return []

        items: list[FetchedItem] = []
        for pub in self._config.publications:
            try:
                items.extend(self._fetch_publication(pub, already_processed))
            except Exception:
                logger.exception("Failed to fetch Substack publication %r", pub.slug)
        return items

    def _fetch_publication(
        self, pub: SubstackPublication, already_processed: set[str]
    ) -> list[FetchedItem]:
        base_url = f"https://{pub.slug}.substack.com"
        api_url = f"{base_url}/api/v1/archive?sort=new&limit={_API_LIMIT}&offset=0"

        try:
            posts: list[dict] = with_backoff(
                lambda: _fetch_json(api_url),
                label=f"Substack JSON {pub.name}",
                no_retry=(_PermanentHTTPError,),
            )
            entries = _parse_api_posts(posts, base_url)
        except _PermanentHTTPError as exc:
            rss_url = f"{base_url}/feed"
            logger.warning(
                "Substack JSON API %r failed (%s); falling back to RSS %r",
                api_url,
                exc,
                rss_url,
            )
            xml_bytes: bytes = with_backoff(
                lambda: _fetch_xml(rss_url),
                label=f"Substack RSS {pub.name}",
                no_retry=(_PermanentHTTPError,),
            )
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_bytes)
            entries = _parse_entries(root)

        if not entries:
            logger.warning("No entries found for Substack publication %r", pub.slug)
            return []

        normalised_processed = {_normalise_url(u) for u in already_processed}

        items: list[FetchedItem] = []
        for entry in entries:
            url = _normalise_url(entry.get("url", ""))
            if not url:
                continue
            if url in normalised_processed:
                logger.debug("Skip %s — already processed", url)
                continue

            items.append(
                FetchedItem(
                    id=url,
                    title=entry.get("title", "Untitled"),
                    url=url,
                    content=entry.get("content", "")[:_MAX_CONTENT_CHARS],
                    source_name=pub.name,
                    published=entry.get("published"),
                )
            )

        logger.info("Substack %r: %d new item(s)", pub.name, len(items))
        return items


# ---------------------------------------------------------------------------
# JSON API parsing
# ---------------------------------------------------------------------------


def _parse_api_posts(posts: list[dict], base_url: str) -> list[dict]:
    """Convert raw Substack API post objects to the common entry dict format."""
    entries = []
    for post in posts:
        slug = post.get("slug", "")
        url = post.get("canonical_url") or (f"{base_url}/p/{slug}" if slug else "")
        title = post.get("title") or "Untitled"
        content = post.get("body_text") or post.get("description") or ""
        published = _parse_api_date(post.get("post_date"))
        if url:
            entries.append({"url": url, "title": title, "content": content, "published": published})
    return entries


def _parse_api_date(value: str | None) -> datetime | None:
    if not value:
        return None
    # Substack returns ISO-8601 with optional milliseconds, e.g. "2026-02-22T10:00:00.000Z"
    # Strip milliseconds and timezone marker; parse as a naive UTC datetime (consistent
    # with _parse_rfc2822_date in rss.py which also strips tzinfo).
    try:
        normalised = value.replace("Z", "").split(".")[0].split("+")[0]
        return datetime.fromisoformat(normalised)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _fetch_json(url: str) -> list[dict]:
    response = httpx.get(url, follow_redirects=True, timeout=15, headers=_HEADERS)
    if 400 <= response.status_code < 500 and response.status_code != 429:
        raise _PermanentHTTPError(f"HTTP {response.status_code} fetching {url!r} — not retrying")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array from {url!r}, got {type(data).__name__}")
    return data


def _fetch_xml(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=15, headers=_HEADERS)
    if 400 <= response.status_code < 500 and response.status_code != 429:
        raise _PermanentHTTPError(f"HTTP {response.status_code} fetching {url!r} — not retrying")
    response.raise_for_status()
    return response.content
