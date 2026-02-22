"""RSS / Atom feed fetcher.

Reads feeds listed in config.blogs.rss, fetches them with httpx,
and parses with stdlib xml.etree.ElementTree.  Supports both RSS 2.0
(<rss>/<channel>/<item>) and Atom 1.0 (<feed>/<entry>).

Deduplication key: the item URL, normalised (trailing slash stripped).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

from src.config import BlogsConfig, RSSFeed
from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 12_000

# XML namespaces
_NS_ATOM = "http://www.w3.org/2005/Atom"
_NS_CONTENT = "http://purl.org/rss/1.0/modules/content/"

# Cloudflare and many CDNs block the default python-httpx User-Agent string.
# A neutral browser UA avoids the challenge page.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


class _PermanentHTTPError(Exception):
    """4xx HTTP error that will not improve on retry."""


class RSSFetcher:
    def __init__(self, config: BlogsConfig) -> None:
        self._config = config

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        if not self._config.enabled or not self._config.rss:
            return []

        items: list[FetchedItem] = []
        for feed_cfg in self._config.rss:
            try:
                items.extend(self._fetch_feed(feed_cfg, already_processed))
            except Exception:
                logger.exception("Failed to fetch RSS feed %r", feed_cfg.url)
        return items

    def _fetch_feed(self, feed_cfg: RSSFeed, already_processed: set[str]) -> list[FetchedItem]:
        xml_bytes: bytes = with_backoff(
            lambda: _fetch_url(feed_cfg.url),
            label=f"RSS {feed_cfg.name}",
            no_retry=(_PermanentHTTPError,),
        )
        root = ET.fromstring(xml_bytes)
        entries = _parse_entries(root)

        if not entries:
            logger.warning("No entries found in feed %r", feed_cfg.url)
            return []

        # Normalise both sides so URLs with/without trailing slash match.
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
                    source_name=feed_cfg.name,
                    published=entry.get("published"),
                )
            )

        logger.info("Feed %r: %d new item(s)", feed_cfg.name, len(items))
        return items


# ---------------------------------------------------------------------------
# Feed parsing — returns a list of plain dicts for easy testing
# ---------------------------------------------------------------------------

def _parse_entries(root: ET.Element) -> list[dict]:
    tag = root.tag
    if tag == f"{{{_NS_ATOM}}}feed" or tag == "feed":
        return _parse_atom(root)
    # RSS 2.0: root is <rss>, channel items are inside <channel>
    channel = root.find("channel")
    if channel is not None:
        return _parse_rss(channel)
    return []


def _parse_atom(feed: ET.Element) -> list[dict]:
    ns = {"atom": _NS_ATOM}
    entries = []
    for entry in feed.findall("atom:entry", ns) or feed.findall("entry"):
        url = _link_from_atom_entry(entry, ns)
        title = _find_text(entry, "atom:title", ns) or _find_text(entry, "title") or "Untitled"
        content = (
            _find_text(entry, "atom:content", ns)
            or _find_text(entry, "content")
            or _find_text(entry, "atom:summary", ns)
            or _find_text(entry, "summary")
            or ""
        )
        published = _parse_atom_date(
            _find_text(entry, "atom:published", ns) or _find_text(entry, "published")
            or _find_text(entry, "atom:updated", ns) or _find_text(entry, "updated")
        )
        entries.append({"url": url, "title": title, "content": content, "published": published})
    return entries


def _parse_rss(channel: ET.Element) -> list[dict]:
    entries = []
    for item in channel.findall("item"):
        url = _find_text(item, "link") or ""
        title = _find_text(item, "title") or "Untitled"
        # <content:encoded> is the full article body in many RSS feeds
        content_el = item.find(f"{{{_NS_CONTENT}}}encoded")
        content = (
            (content_el.text or "").strip() if content_el is not None else None
        ) or _find_text(item, "description") or ""
        published = _parse_rfc2822_date(_find_text(item, "pubDate"))
        entries.append({"url": url, "title": title, "content": content, "published": published})
    return entries


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_url(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=15, headers=_HEADERS)
    if 400 <= response.status_code < 500 and response.status_code != 429:
        raise _PermanentHTTPError(
            f"HTTP {response.status_code} fetching {url!r} — not retrying"
        )
    response.raise_for_status()
    return response.content


def _normalise_url(url: str) -> str:
    return url.strip().rstrip("/")


def _find_text(element: ET.Element, path: str, ns: dict[str, str] | None = None) -> str:
    el = element.find(path, ns or {})
    return (el.text or "").strip() if el is not None else ""


def _link_from_atom_entry(entry: ET.Element, ns: dict[str, str]) -> str:
    """Extract href from <link rel='alternate'> or the first <link> element."""
    for link in entry.findall("atom:link", ns) or entry.findall("link"):
        if link.get("rel") in ("alternate", None, ""):
            href = link.get("href", "")
            if href:
                return href
    return ""


def _parse_atom_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_rfc2822_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except Exception:
        return None
