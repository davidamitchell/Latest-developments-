"""YouTube channel fetcher using the YouTube Data API and transcript API."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Protocol

import httpx
from youtube_transcript_api import YouTubeTranscriptApi

from src.config import YouTubeChannel, YouTubeConfig
from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 12_000
_SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"


class _TranscriptSnippet(Protocol):
    text: str


class _TranscriptClient:
    def fetch(self, video_id: str) -> list[dict[str, Any] | _TranscriptSnippet]:
        return YouTubeTranscriptApi.get_transcript(video_id)


class YouTubeFetcher:
    def __init__(self, config: YouTubeConfig) -> None:
        self._config = config
        self._api = _TranscriptClient()

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        if not self._config.enabled or not self._config.channels:
            return []

        items: list[FetchedItem] = []
        for channel in self._config.channels:
            try:
                items.extend(self._fetch_channel(channel, already_processed))
            except Exception:
                logger.exception("Failed to fetch YouTube channel %r", channel.channel_id)
        return items

    def _fetch_channel(
        self, channel: YouTubeChannel, already_processed: set[str]
    ) -> list[FetchedItem]:
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            logger.error("YOUTUBE_API_KEY is not set; skipping channel %r", channel.name)
            return []

        params = {
            "part": "snippet",
            "channelId": channel.channel_id,
            "order": "date",
            "type": "video",
            "maxResults": str(channel.max_videos),
            "key": api_key,
        }

        try:
            payload = _fetch_json(_SEARCH_ENDPOINT, params, label=f"YouTube channel {channel.name}")
        except Exception:
            logger.exception("Failed to fetch YouTube Data API for channel %r", channel.channel_id)
            return []

        items: list[FetchedItem] = []
        for entry in payload.get("items", [])[: channel.max_videos]:
            video_id = entry.get("id", {}).get("videoId")
            if not video_id:
                continue
            if video_id in already_processed:
                logger.debug("Skip %s — already processed", video_id)
                continue

            snippet = entry.get("snippet", {})
            title = snippet.get("title", "Untitled")
            description = snippet.get("description", "")
            published = _parse_date(snippet.get("publishedAt", ""))
            content = self._transcript_or_description(video_id, description)

            items.append(
                FetchedItem(
                    id=video_id,
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    content=content[:_MAX_CONTENT_CHARS],
                    source_name=channel.name,
                    published=published,
                )
            )

        logger.info("Channel %r: %d new item(s)", channel.name, len(items))
        return items

    def _transcript_or_description(self, video_id: str, description: str) -> str:
        try:
            transcript = self._api.fetch(video_id)
        except Exception as exc:
            logger.warning("Transcript unavailable for %s: %s", video_id, exc)
            return description

        parts: list[str] = []
        for snippet in transcript:
            if isinstance(snippet, dict):
                text = snippet.get("text", "")
            else:
                text = getattr(snippet, "text", "")
            if text:
                parts.append(text)
        content = " ".join(parts).strip()
        return content or description


def _fetch_json(url: str, params: dict[str, str], *, label: str) -> dict[str, Any]:
    def _request() -> dict[str, Any]:
        try:
            response = httpx.get(url, params=params, timeout=15)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            reason = exc.response.reason_phrase if exc.response else ""
            message = f"{label} failed: HTTP {status} {reason}".strip()
            raise RuntimeError(message) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"{label} failed: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"{label} returned invalid JSON") from exc

    return with_backoff(_request, label=label)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
