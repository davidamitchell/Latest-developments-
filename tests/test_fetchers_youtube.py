"""Tests for src/fetchers/youtube.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.config import YouTubeChannel, YouTubeConfig
from src.fetchers.youtube import YouTubeFetcher, _parse_date


def _make_config(channels: list[YouTubeChannel] | None = None) -> YouTubeConfig:
    return YouTubeConfig(
        enabled=True,
        max_videos_per_channel=5,
        channels=channels
        or [YouTubeChannel(name="Test Channel", channel_id="UCtest123", max_videos=5)],
    )


def _atom_feed(*video_ids: str) -> bytes:
    """Build a minimal YouTube Atom feed for testing."""
    entries = ""
    for vid in video_ids:
        entries += f"""
  <entry xmlns:yt="http://www.youtube.com/xml/schemas/2015">
    <yt:videoId>{vid}</yt:videoId>
    <title>{vid} title</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v={vid}"/>
    <published>2026-02-21T07:00:00+00:00</published>
  </entry>"""

    return f"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <title>Test Channel</title>{entries}
</feed>""".encode()


def _mock_transcript(text: str = "Hello world transcript") -> list[MagicMock]:
    snippet = MagicMock()
    snippet.text = text
    return [snippet]


class TestYouTubeFetcher:
    def test_disabled_returns_empty(self) -> None:
        cfg = YouTubeConfig(enabled=False, channels=[])
        assert YouTubeFetcher(cfg).fetch(set()) == []

    def test_no_channels_returns_empty(self) -> None:
        cfg = YouTubeConfig(enabled=True, channels=[])
        assert YouTubeFetcher(cfg).fetch(set()) == []

    def test_already_processed_skipped(self) -> None:
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with (
            patch("src.fetchers.youtube._fetch_url", return_value=_atom_feed("vid1")),
            patch.object(fetcher._api, "fetch") as mock_api,
        ):
            items = fetcher.fetch(already_processed={"vid1"})

        assert items == []
        mock_api.assert_not_called()

    def test_fetches_new_video(self) -> None:
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with (
            patch("src.fetchers.youtube._fetch_url", return_value=_atom_feed("vid1")),
            patch.object(fetcher._api, "fetch", return_value=_mock_transcript("transcript text")),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 1
        assert items[0].id == "vid1"
        assert items[0].content == "transcript text"
        assert items[0].source_name == "Test Channel"
        assert items[0].url == "https://www.youtube.com/watch?v=vid1"

    def test_respects_max_videos(self) -> None:
        cfg = _make_config([YouTubeChannel(name="Ch", channel_id="UCtest", max_videos=2)])
        fetcher = YouTubeFetcher(cfg)
        feed = _atom_feed("v1", "v2", "v3", "v4", "v5")

        with (
            patch("src.fetchers.youtube._fetch_url", return_value=feed),
            patch.object(fetcher._api, "fetch", return_value=_mock_transcript()),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 2

    def test_skips_video_without_transcript(self) -> None:
        from youtube_transcript_api import NoTranscriptFound

        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with (
            patch("src.fetchers.youtube._fetch_url", return_value=_atom_feed("v1", "v2")),
            patch.object(fetcher._api, "fetch") as mock_api,
        ):
            mock_api.side_effect = [
                NoTranscriptFound("v1", [], MagicMock()),
                _mock_transcript("second"),
            ]
            items = fetcher.fetch(set())

        assert len(items) == 1
        assert items[0].id == "v2"

    def test_channel_error_does_not_abort_other_channels(self) -> None:
        channels = [
            YouTubeChannel(name="Good", channel_id="UCgood", max_videos=5),
            YouTubeChannel(name="Bad", channel_id="UCbad", max_videos=5),
        ]
        cfg = _make_config(channels)
        fetcher = YouTubeFetcher(cfg)

        def fetch_url_side(url: str) -> bytes:
            if "UCgood" in url:
                return _atom_feed("vid1")
            raise ConnectionError("DNS failure")

        with (
            patch("src.fetchers.youtube._fetch_url", side_effect=fetch_url_side),
            patch.object(fetcher._api, "fetch", return_value=_mock_transcript()),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 1
        assert items[0].source_name == "Good"

    def test_content_truncated_at_limit(self) -> None:
        from src.fetchers.youtube import _MAX_CONTENT_CHARS

        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        snippet = MagicMock()
        snippet.text = "x " * 10_000

        with (
            patch("src.fetchers.youtube._fetch_url", return_value=_atom_feed("vid1")),
            patch.object(fetcher._api, "fetch", return_value=[snippet]),
        ):
            items = fetcher.fetch(set())

        assert len(items[0].content) == _MAX_CONTENT_CHARS

    def test_empty_feed_returns_empty(self) -> None:
        empty_feed = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Ch</title></feed>"""
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with patch("src.fetchers.youtube._fetch_url", return_value=empty_feed):
            items = fetcher.fetch(set())

        assert items == []


class TestParseDate:
    def test_returns_none_for_empty_string(self) -> None:
        assert _parse_date("") is None

    def test_parses_iso_format(self) -> None:
        result = _parse_date("2026-02-21T07:00:00+00:00")
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 21

    def test_returns_none_for_invalid_format(self) -> None:
        assert _parse_date("not-a-date") is None
