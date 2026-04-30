"""Papers with Code fetcher — trend pipeline only.

Fetches trending papers from the Papers with Code public JSON API.
Source class: primary (peer-submitted research with linked code repositories).
has_code=True on every item — reproducibility proxy = 1.0 in credibility scoring.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime

import httpx

from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_API_URL = "https://paperswithcode.com/api/v1/papers/"

_HEADERS = {
    "User-Agent": "latest-developments-bot/1.0",
    "Accept": "application/json",
}

_MAX_CONTENT_CHARS = 8_000


class PapersWithCodeFetcher:
    """Fetch trending papers from Papers with Code."""

    def __init__(
        self,
        page_size: int = 20,
        min_stars: int = 0,
    ) -> None:
        self._page_size = page_size
        self._min_stars = min_stars

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        try:
            return with_backoff(lambda: self._fetch_papers(already_processed))
        except Exception as exc:
            logger.warning("Papers with Code fetch failed: %s", exc)
            return []

    def _fetch_papers(self, already_processed: set[str]) -> list[FetchedItem]:
        params: dict[str, str | int] = {
            "ordering": "-stars",
            "page_size": self._page_size,
        }
        response = httpx.get(_API_URL, params=params, headers=_HEADERS, timeout=30)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            logger.warning("Papers with Code API returned unexpected format")
            return []

        results = data.get("results", [])
        if not isinstance(results, list):
            logger.warning("Papers with Code API: 'results' field missing or not a list")
            return []

        items: list[FetchedItem] = []
        for paper in results:
            try:
                item = self._parse_paper(paper, already_processed)
            except Exception as exc:
                logger.warning("Skipping Papers with Code item due to error: %s", exc)
                continue
            if item is not None:
                items.append(item)

        logger.info("Papers with Code: %d new item(s)", len(items))
        return items

    def _parse_paper(
        self,
        paper: dict,
        already_processed: set[str],
    ) -> FetchedItem | None:
        paper_url = (paper.get("paper", {}) or {}).get("url_pdf", "") or ""
        # Prefer the Papers with Code canonical URL
        pwc_url = paper.get("url", "") or paper_url
        if not pwc_url:
            return None

        norm_url = pwc_url.rstrip("/")
        if norm_url in already_processed:
            return None

        # Apply min_stars filter
        stars = paper.get("stars", 0) or 0
        if stars < self._min_stars:
            return None

        title = paper.get("title", "") or (paper.get("paper", {}) or {}).get("title", "Untitled")
        if not title:
            title = "Untitled"

        arxiv_id = paper.get("arxiv_id", "") or ""
        repo_count = len(paper.get("repository_set", []) or [])

        content_parts = [f"Title: {title}"]
        if arxiv_id:
            content_parts.append(f"arXiv ID: {arxiv_id}")
        if stars:
            content_parts.append(f"Stars: {stars}")
        if repo_count:
            content_parts.append(f"Code repositories: {repo_count}")
        abstract = (paper.get("paper", {}) or {}).get("abstract", "") or ""
        if abstract:
            content_parts.append(f"Abstract: {abstract}")

        content = "\n".join(content_parts)[:_MAX_CONTENT_CHARS]

        pub_date: datetime | None = None
        published_str = (paper.get("paper", {}) or {}).get("published", "") or ""
        if published_str:
            with contextlib.suppress(ValueError):
                pub_date = datetime.fromisoformat(published_str.replace("Z", "+00:00"))

        return FetchedItem(
            id=norm_url,
            title=title,
            url=norm_url,
            content=content,
            source_name="Papers with Code",
            source_type="PapersWithCode",
            source_class="primary",
            published=pub_date,
            has_code=True,
        )
