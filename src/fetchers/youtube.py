"""YouTube channel fetcher using the YouTube Data API v3.

Discovers recent videos via the YouTube Data API search endpoint, then fetches
transcripts via youtube-transcript-api.

Requires YOUTUBE_API_KEY environment variable — set as a GitHub Secret or in
.env for local runs.  Get a free key at https://console.developers.google.com/
with the "YouTube Data API v3" enabled (free tier: 10,000 units/day).
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

import httpx
from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi

from src.config import YouTubeChannel, YouTubeConfig
from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"
_MAX_CONTENT_CHARS = 12_000


class YouTubeFetcher:
    def __init__(self, config: YouTubeConfig) -> None:
        self._config = config
        self._api_key = os.environ.get("YOUTUBE_API_KEY", "")
        self._transcript_api = YouTubeTranscriptApi()

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        if not self._config.enabled or not self._config.channels:
            return []

        if not self._api_key:
            raise RuntimeError("YOUTUBE_API_KEY is not set — add it as a GitHub Secret or in .env")

        items: list[FetchedItem] = []
        for channel in self._config.channels:
            # Errors propagate here so they are captured in the run summary by
            # _safe_fetch in main.py — no silent swallowing of channel failures.
            items.extend(self._fetch_channel(channel, already_processed))
        return items

    def _fetch_channel(
        self, channel: YouTubeChannel, already_processed: set[str]
    ) -> list[FetchedItem]:
        search_results = with_backoff(
            lambda: self._search_channel(channel.channel_id, channel.max_videos),
            label=f"YouTube API {channel.name}",
        )

        if not search_results:
            logger.warning(
                "No videos returned for channel %r (channel_id=%r)"
                " — verify the channel_id is correct in config/sources.yaml",
                channel.name,
                channel.channel_id,
            )
            return []

        items: list[FetchedItem] = []
        for result in search_results:
            video_id = result.get("id", {}).get("videoId", "")
            if not video_id:
                continue
            if video_id in already_processed:
                logger.debug("Skip %s — already processed", video_id)
                continue

            snippet = result.get("snippet", {})
            title = snippet.get("title") or "Untitled"

            # Skip YouTube Shorts — these are short-form videos tagged #Shorts
            if _is_short(title):
                logger.debug("Skip %s — appears to be a YouTube Short", video_id)
                continue

            # Use description from the API as fallback when transcript is unavailable
            # (cloud runner IPs are frequently blocked by YouTube's transcript service).
            description = snippet.get("description", "")
            published = _parse_date(snippet.get("publishedAt", ""))

            transcript = self._get_transcript(video_id, title)
            content = transcript if transcript is not None else description

            items.append(
                FetchedItem(
                    id=video_id,
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    content=content[:_MAX_CONTENT_CHARS],
                    source_name=channel.name,
                    published=published,
                    source_type="YouTube",
                )
            )

        logger.info("Channel %r: %d new item(s)", channel.name, len(items))
        return items

    def _search_channel(self, channel_id: str, max_results: int) -> list[dict]:
        """Call the YouTube Data API search.list to get recent videos for a channel."""
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "maxResults": min(
                max_results, 50
            ),  # YouTube API hard limit is 50; channels with max_videos > 50 are silently capped
            "key": self._api_key,
        }
        response = httpx.get(_SEARCH_API, params=params, timeout=15)
        response.raise_for_status()
        return response.json().get("items") or []

    def _get_transcript(self, video_id: str, title: str) -> str | None:
        # Prefer human captions; fall back to auto-generated (a.en, a.de, …)
        # youtube-transcript-api will translate auto-generated if needed.
        language_prefs = ("en", "en-US", "en-GB", "a.en")
        try:
            result = with_backoff(
                lambda: self._transcript_api.fetch(video_id, languages=language_prefs),
                label=f"transcript {video_id}",
                no_retry=(CouldNotRetrieveTranscript,),
            )
            text = " ".join(s.text for s in result)
            logger.debug("Transcript for %r: %d chars", title, len(text))
            return text
        except CouldNotRetrieveTranscript as e:
            logger.warning("No transcript for %r: %s", title, e)
            return None
        except RuntimeError:
            logger.error("Transcript fetch failed after retries for %r", title)
            return None


def _is_short(title: str) -> bool:
    """Return True if the video appears to be a YouTube Short based on its title hashtag."""
    return bool(re.search(r"#shorts?\b", title, re.IGNORECASE))


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
