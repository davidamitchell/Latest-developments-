"""YouTube channel fetcher.

Discovers recent videos via each channel's public RSS/Atom feed
(no API key required), then fetches transcripts via youtube-transcript-api.

The YouTube channel feed format is:
  https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID
It returns up to 15 recent videos as Atom XML, parsed here with stdlib etree.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx
from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi

from src.config import YouTubeChannel, YouTubeConfig
from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_MAX_CONTENT_CHARS = 12_000

# Atom and YouTube XML namespaces used in the channel feed
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


class YouTubeFetcher:
    def __init__(self, config: YouTubeConfig) -> None:
        self._config = config
        self._api = YouTubeTranscriptApi()

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        if not self._config.enabled or not self._config.channels:
            return []

        items: list[FetchedItem] = []
        for channel in self._config.channels:
            try:
                items.extend(self._fetch_channel(channel, already_processed))
            except Exception:
                logger.exception("Failed to process channel %r", channel.name)
        return items

    def _fetch_channel(
        self, channel: YouTubeChannel, already_processed: set[str]
    ) -> list[FetchedItem]:
        url = _FEED_URL.format(channel_id=channel.channel_id)
        xml_bytes: bytes = with_backoff(
            lambda: _fetch_url(url),
            label=f"RSS {channel.name}",
        )

        root = ET.fromstring(xml_bytes)
        entries = root.findall("atom:entry", _NS)

        if not entries:
            logger.warning("No entries in feed for %r", channel.name)
            return []

        items: list[FetchedItem] = []
        checked = 0
        for entry in entries:
            if checked >= channel.max_videos:
                break
            checked += 1

            video_id = _text(entry, "yt:videoId", _NS)
            if not video_id:
                continue
            if video_id in already_processed:
                logger.debug("Skip %s — already processed", video_id)
                continue

            title = _text(entry, "atom:title", _NS) or "Untitled"
            link_el = entry.find("atom:link[@rel='alternate']", _NS)
            url_str = link_el.get("href") if link_el is not None else f"https://youtu.be/{video_id}"

            # Use description from the feed as fallback when transcript is unavailable
            # (cloud runner IPs are frequently blocked by YouTube's transcript service).
            description = _text(entry, "media:group/media:description", _NS)

            transcript = self._get_transcript(video_id, title)
            content = transcript if transcript is not None else description

            published = _parse_date(_text(entry, "atom:published", _NS))
            items.append(
                FetchedItem(
                    id=video_id,
                    title=title,
                    url=url_str or f"https://youtu.be/{video_id}",
                    content=content[:_MAX_CONTENT_CHARS],
                    source_name=channel.name,
                    published=published,
                    source_type="YouTube",
                )
            )

        logger.info("Channel %r: %d new item(s)", channel.name, len(items))
        return items

    def _get_transcript(self, video_id: str, title: str) -> str | None:
        # Prefer human captions; fall back to auto-generated (a.en, a.de, …)
        # youtube-transcript-api will translate auto-generated if needed.
        language_prefs = ("en", "en-US", "en-GB", "a.en")
        try:
            result = with_backoff(
                lambda: self._api.fetch(video_id, languages=language_prefs),
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


def _fetch_url(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=15)
    response.raise_for_status()
    return response.content


def _text(element: ET.Element, path: str, ns: dict[str, str]) -> str:
    el = element.find(path, ns)
    return (el.text or "").strip() if el is not None else ""


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
