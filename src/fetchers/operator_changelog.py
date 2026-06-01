"""Operator changelog fetcher — trend pipeline only.

Fetches RSS feeds from major AI lab / operator blogs as source_class="operator".
This is RSS infrastructure reuse: each configured feed is fetched, parsed, and
returned as a FetchedItem with source_class="operator".

Initial targets (all confirmed RSS):
  - Anthropic Blog
  - OpenAI Blog
  - Google AI Blog
  - DeepMind Blog
  - AWS Machine Learning Blog
  - Microsoft AI Blog
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 8_000

# XML namespaces
_NS_ATOM = "http://www.w3.org/2005/Atom"
_NS_CONTENT = "http://purl.org/rss/1.0/modules/content/"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.5",
}

# Keywords that indicate a pricing / cost announcement.
# When any of these appear in title or content the item is tagged
# evidence_type="pricing" for downstream cost-trend analysis.
_PRICING_KEYWORDS: frozenset[str] = frozenset(
    {
        "price",
        "pricing",
        "cost",
        "$/",
        "per million",
        "per 1m token",
        "tokens per dollar",
        "token cost",
        "rate limit",
        "free tier",
        "paid tier",
        "subscription",
    }
)


def _is_pricing_item(title: str, content: str) -> bool:
    """Return True when the item discusses pricing or cost changes."""
    text = (title + " " + content).lower()
    return any(kw in text for kw in _PRICING_KEYWORDS)


class _PermanentHTTPError(Exception):
    """4xx HTTP error that will not improve on retry."""


class OperatorChangelogFetcher:
    """Fetch operator changelog / blog feeds for the trend pipeline.

    Each feed URL is fetched, parsed (RSS 2.0 or Atom), and returned as a
    FetchedItem. ``source_class`` defaults to ``"operator"`` but can be
    overridden (e.g. ``"practitioner"`` for community tool release feeds).
    """

    def __init__(self, feeds: list[str], source_class: str = "operator") -> None:
        self._feeds = feeds
        self._source_class = source_class

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        if not self._feeds:
            return []

        seen_urls: set[str] = set(already_processed)
        items: list[FetchedItem] = []

        for feed_url in self._feeds:
            try:
                new = self._fetch_feed(feed_url, seen_urls)
                items.extend(new)
                for item in new:
                    seen_urls.add(item.url)
            except Exception as exc:
                logger.warning("Operator changelog feed %r failed: %s", feed_url, exc)

        logger.info(
            "Operator changelogs: %d new item(s) across %d feeds", len(items), len(self._feeds)
        )
        return items

    def _fetch_feed(self, feed_url: str, already_processed: set[str]) -> list[FetchedItem]:
        xml_bytes: bytes = with_backoff(
            lambda url=feed_url: _fetch_url(url),
            label=f"operator feed {feed_url}",
            no_retry=(_PermanentHTTPError,),
        )

        root = ET.fromstring(xml_bytes)
        entries = _parse_entries(root)

        if not entries:
            logger.debug("No entries found in operator feed %r", feed_url)
            return []

        normalised_processed = {u.rstrip("/") for u in already_processed}

        items: list[FetchedItem] = []
        for entry in entries:
            url = (entry.get("url", "") or "").rstrip("/")
            if not url:
                continue
            if url in normalised_processed:
                continue

            items.append(
                FetchedItem(
                    id=url,
                    title=entry.get("title", "Untitled"),
                    url=url,
                    content=(entry.get("content", "") or "")[:_MAX_CONTENT_CHARS],
                    source_name=_source_name_from_url(feed_url),
                    published=entry.get("published"),
                    source_type="RSS",
                    source_class=self._source_class,
                    evidence_type="pricing"
                    if _is_pricing_item(entry.get("title", ""), entry.get("content", "") or "")
                    else "",
                )
            )

        logger.debug("Operator feed %r: %d new item(s)", feed_url, len(items))
        return items


# ---------------------------------------------------------------------------
# Feed parsing helpers (shared with rss.py pattern)
# ---------------------------------------------------------------------------


def _parse_entries(root: ET.Element) -> list[dict]:
    tag = root.tag
    if tag == f"{{{_NS_ATOM}}}feed" or tag == "feed":
        return _parse_atom(root)
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
            _find_text(entry, "atom:published", ns)
            or _find_text(entry, "published")
            or _find_text(entry, "atom:updated", ns)
            or _find_text(entry, "updated")
        )
        entries.append({"url": url, "title": title, "content": content, "published": published})
    return entries


def _parse_rss(channel: ET.Element) -> list[dict]:
    entries = []
    for item in channel.findall("item"):
        url = _find_text(item, "link") or ""
        title = _find_text(item, "title") or "Untitled"
        content_el = item.find(f"{{{_NS_CONTENT}}}encoded")
        content = (
            ((content_el.text or "").strip() if content_el is not None else None)
            or _find_text(item, "description")
            or ""
        )
        published = _parse_rfc2822_date(_find_text(item, "pubDate"))
        entries.append({"url": url, "title": title, "content": content, "published": published})
    return entries


def _fetch_url(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=15, headers=_HEADERS)
    if 400 <= response.status_code < 500 and response.status_code != 429:
        raise _PermanentHTTPError(f"HTTP {response.status_code} fetching {url!r} — not retrying")
    response.raise_for_status()
    return response.content


def _find_text(element: ET.Element, path: str, ns: dict[str, str] | None = None) -> str:
    el = element.find(path, ns or {})
    return (el.text or "").strip() if el is not None else ""


def _link_from_atom_entry(entry: ET.Element, ns: dict[str, str]) -> str:
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
    except Exception:  # noqa: BLE001
        return None


def _source_name_from_url(feed_url: str) -> str:
    """Derive a human-readable source name from a feed URL."""
    _known: dict[str, str] = {
        # Major labs (W-0009)
        "anthropic.com": "Anthropic Blog",
        "openai.com": "OpenAI Blog",
        "blog.google": "Google AI Blog",
        "deepmind.google": "DeepMind Blog",
        "aws.amazon.com": "AWS ML Blog",
        "blogs.microsoft.com": "Microsoft AI Blog",
        # New entrant inference providers (W-0021) — verified 2026-05-01
        "groq.com": "Groq Blog",
        "groq/groq-python": "Groq SDK Releases",
        "together.ai": "Together AI Blog",
        "fireworks.ai": "Fireworks AI Blog",
        "cerebras.ai": "Cerebras Blog",
        "Cerebras/cerebras-cloud-sdk": "Cerebras SDK Releases",
        "lambdalabs.com": "Lambda Blog",
        "lambda.ai": "Lambda Blog",
        "blog.perplexity.ai": "Perplexity Blog",
        "mistral.ai": "Mistral AI Blog",
        "mistralai/mistral-inference": "Mistral Inference Releases",
        "mistralai/client-python": "Mistral Python SDK Releases",
        # Local model tools (W-0022)
        "ollama.com": "Ollama Releases",
        "github.com/ollama": "Ollama Releases",
        "github.com/ggerganov": "llama.cpp Releases",
        "github.com/mudler": "LocalAI Releases",
        "lmstudio.ai": "LM Studio",
        "simonwillison.net": "Simon Willison's Weblog",
    }
    for domain, name in _known.items():
        if domain in feed_url:
            return name
    # Fallback: strip scheme and leading www.
    from urllib.parse import urlparse

    netloc = urlparse(feed_url).netloc
    host = netloc[4:] if netloc.startswith("www.") else netloc
    return host or feed_url
