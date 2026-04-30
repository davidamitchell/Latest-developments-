"""arXiv RSS fetcher — for the trend analysis pipeline only.

Fetches recent papers from arXiv cs.AI, cs.LG, cs.CL, cs.CV, cs.RO feeds.
NOT wired into the email digest pipeline (src/main.py).
Source class: primary (closest to the claim; peer-submitted research).
"""

from __future__ import annotations

import contextlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_FEED_URL = "https://rss.arxiv.org/rss/{category}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; latest-developments-bot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

_MAX_CONTENT_CHARS = 8_000


class ArxivFetcher:
    """Fetch recent arXiv papers from RSS feeds for given categories."""

    def __init__(self, categories: list[str], max_papers: int = 30) -> None:
        self._categories = categories
        self._max_papers = max_papers

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        items: list[FetchedItem] = []
        for category in self._categories:
            try:
                new = with_backoff(lambda c=category: self._fetch_category(c, already_processed))
                items.extend(new)
                logger.info("arXiv %s: %d new papers", category, len(new))
            except Exception as exc:
                logger.warning("arXiv %s fetch failed: %s", category, exc)
        return items

    def _fetch_category(self, category: str, already_processed: set[str]) -> list[FetchedItem]:
        url = _FEED_URL.format(category=category)
        response = httpx.get(url, headers=_HEADERS, timeout=30, follow_redirects=True)
        response.raise_for_status()
        return self._parse_feed(response.text, category, already_processed)

    def _parse_feed(
        self,
        xml_text: str,
        category: str,
        already_processed: set[str],
    ) -> list[FetchedItem]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("arXiv %s: XML parse error: %s", category, exc)
            return []

        items: list[FetchedItem] = []

        # arXiv RSS feeds are RSS 2.0 format
        channel = root.find("channel")
        if channel is None:
            return []

        for item_el in channel.findall("item"):
            if len(items) >= self._max_papers:
                break

            link_el = item_el.find("link")
            url = (link_el.text or "").strip() if link_el is not None else ""
            if not url:
                continue

            # Normalise: strip trailing slash for dedup consistency
            norm_url = url.rstrip("/")
            if norm_url in already_processed:
                continue

            title_el = item_el.find("title")
            title = (title_el.text or "").strip() if title_el is not None else "Untitled"

            desc_el = item_el.find("description")
            description = (desc_el.text or "").strip() if desc_el is not None else ""
            content = description[:_MAX_CONTENT_CHARS]

            # Parse pubDate if present; non-standard formats are silently ignored.
            pub_date: datetime | None = None
            pubdate_el = item_el.find("pubDate")
            if pubdate_el is not None and pubdate_el.text:
                with contextlib.suppress(Exception):
                    pub_date = parsedate_to_datetime(pubdate_el.text.strip())

            item_id = f"arxiv:{norm_url}"
            items.append(
                FetchedItem(
                    id=item_id,
                    title=title,
                    url=norm_url,
                    content=content,
                    source_name="arXiv",
                    source_type="arXiv",
                    source_class="primary",
                    published=pub_date,
                )
            )

        return items
