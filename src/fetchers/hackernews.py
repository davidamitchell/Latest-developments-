"""Hacker News fetcher via the Algolia search API.

Queries https://hn.algolia.com/api/v1/search_by_date for stories that:
  - are tagged ``story``
  - were created in the last 48 hours
  - have at least ``min_score`` points
  - match at least one keyword from config.keywords in the title or URL

Deduplication key: Algolia ``objectID`` (the HN story ID as a string).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx

from src.config import HackerNewsConfig
from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"
_LOOKBACK_HOURS = 48
_MAX_CONTENT_CHARS = 12_000


class HackerNewsFetcher:
    def __init__(self, config: HackerNewsConfig) -> None:
        self._config = config

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        if not self._config.enabled:
            return []

        try:
            stories = self._fetch_stories()
        except Exception:
            logger.exception("Failed to fetch Hacker News stories")
            return []

        items: list[FetchedItem] = []
        for story in stories:
            story_id = str(story.get("objectID") or "")
            if not story_id:
                continue
            if story_id in already_processed:
                logger.debug("Skip HN story %s — already processed", story_id)
                continue

            title = story.get("title") or "Untitled"
            hn_url = f"https://news.ycombinator.com/item?id={story_id}"
            article_url = story.get("url") or hn_url
            points = story.get("points") or 0
            num_comments = story.get("num_comments") or 0

            # Content is metadata + links; full article body is deferred to slice 5.2.
            content_lines = [
                f"Points: {points}  |  Comments: {num_comments}",
                f"Discussion: {hn_url}",
            ]
            if story.get("url"):
                content_lines.append(f"Article: {story['url']}")
            content = "\n".join(content_lines)

            published = _parse_hn_date(story.get("created_at"))
            items.append(
                FetchedItem(
                    id=story_id,
                    title=title,
                    url=article_url,
                    content=content[:_MAX_CONTENT_CHARS],
                    source_name="Hacker News",
                    published=published,
                    source_type="Hacker News",
                )
            )

        logger.info("Hacker News: %d new item(s)", len(items))
        return items

    def _fetch_stories(self) -> list[dict]:
        """Fetch recent high-scoring stories matching at least one configured keyword."""
        since_ts = int((datetime.now(UTC) - timedelta(hours=_LOOKBACK_HOURS)).timestamp())
        params = {
            "tags": "story",
            "numericFilters": f"points>={self._config.min_score},created_at_i>={since_ts}",
            "hitsPerPage": 100,
        }

        data: dict = with_backoff(
            lambda: _fetch_algolia(params),
            label="HN Algolia search",
        )

        hits = data.get("hits", [])
        lower_keywords = [kw.lower() for kw in self._config.keywords]

        def _matches(story: dict) -> bool:
            haystack = (story.get("title") or "").lower() + " " + (story.get("url") or "").lower()
            return any(kw in haystack for kw in lower_keywords)

        matched = [h for h in hits if _matches(h)]
        matched.sort(key=lambda s: s.get("points") or 0, reverse=True)
        return matched[: self._config.max_stories]


def _fetch_algolia(params: dict) -> dict:
    response = httpx.get(_ALGOLIA_URL, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _parse_hn_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Algolia returns ISO 8601 UTC timestamps like "2026-02-21T07:00:00.000Z"
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
