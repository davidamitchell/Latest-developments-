"""Tests for src/fetchers/youtube.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from src.config import YouTubeChannel, YouTubeConfig
from src.fetchers.youtube import YouTubeFetcher, _parse_date
from src.retry import with_backoff


def _make_config(channels: list[YouTubeChannel] | None = None) -> YouTubeConfig:
    return YouTubeConfig(
        enabled=True,
        max_videos_per_channel=5,
        channels=channels
        or [YouTubeChannel(name="Test Channel", channel_id="UCtest123", max_videos=5)],
    )


def _search_response(*video_ids: str, descriptions: dict[str, str] | None = None) -> dict:
    """Build a minimal YouTube Data API search.list response for testing."""
    desc_map = descriptions or {}
    items = []
    for vid in video_ids:
        items.append(
            {
                "id": {"videoId": vid},
                "snippet": {
                    "title": f"{vid} title",
                    "description": desc_map.get(vid, ""),
                    "publishedAt": "2026-02-21T07:00:00+00:00",
                },
            }
        )
    return {"items": items}


def _with_api_key() -> patch:
    return patch.dict("os.environ", {"YOUTUBE_API_KEY": "test-key"})


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
            _with_api_key(),
            patch("src.fetchers.youtube._fetch_json", return_value=_search_response("vid1")),
            patch.object(fetcher._api, "fetch") as mock_api,
        ):
            items = fetcher.fetch(already_processed={"vid1"})

        assert items == []
        mock_api.assert_not_called()

    def test_fetches_new_video(self) -> None:
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with (
            _with_api_key(),
            patch("src.fetchers.youtube._fetch_json", return_value=_search_response("vid1")),
            patch.object(fetcher._api, "fetch", return_value=_mock_transcript("transcript text")),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 1
        assert items[0].id == "vid1"
        assert items[0].content == "transcript text"
        assert items[0].source_name == "Test Channel"
        assert items[0].url == "https://www.youtube.com/watch?v=vid1"

    def test_fetch_uses_backoff(self) -> None:
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with (
            _with_api_key(),
            patch("src.fetchers.youtube.httpx.get") as mock_get,
            patch.object(fetcher._api, "fetch", return_value=_mock_transcript("transcript text")),
            patch("src.fetchers.youtube.with_backoff", wraps=with_backoff) as mock_backoff,
        ):
            response = MagicMock()
            response.raise_for_status.return_value = None
            response.json.return_value = _search_response("vid1")
            mock_get.return_value = response
            items = fetcher.fetch(set())

        assert len(items) == 1
        mock_backoff.assert_called_once()
        assert mock_backoff.call_args[1]["label"] == "YouTube channel Test Channel"

    def test_respects_max_videos(self) -> None:
        cfg = _make_config([YouTubeChannel(name="Ch", channel_id="UCtest", max_videos=2)])
        fetcher = YouTubeFetcher(cfg)
        response = _search_response("v1", "v2", "v3", "v4", "v5")

        with (
            _with_api_key(),
            patch("src.fetchers.youtube._fetch_json", return_value=response),
            patch.object(fetcher._api, "fetch", return_value=_mock_transcript()),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 2

    def test_includes_item_when_transcript_unavailable(self) -> None:
        """Item is still emitted when transcript fails; content falls back to description."""
        from youtube_transcript_api import NoTranscriptFound

        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with (
            _with_api_key(),
            patch("src.fetchers.youtube._fetch_json", return_value=_search_response("v1", "v2")),
            patch.object(fetcher._api, "fetch") as mock_api,
        ):
            mock_api.side_effect = [
                NoTranscriptFound("v1", [], MagicMock()),
                _mock_transcript("second"),
            ]
            items = fetcher.fetch(set())

        # Both items returned; v1 has no description in the test feed so content is ""
        assert len(items) == 2
        assert items[0].id == "v1"
        assert items[0].content == ""
        assert items[1].id == "v2"
        assert items[1].content == "second"

    def test_uses_description_when_transcript_blocked(self) -> None:
        """Cloud IP blocks transcript → item appears with feed description as content."""
        from youtube_transcript_api import NoTranscriptFound

        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        response = _search_response("vid1", descriptions={"vid1": "Deep dive into LLM fine-tuning"})

        with (
            _with_api_key(),
            patch("src.fetchers.youtube._fetch_json", return_value=response),
            patch.object(
                fetcher._api,
                "fetch",
                side_effect=NoTranscriptFound("vid1", [], MagicMock()),
            ),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 1
        assert items[0].id == "vid1"
        assert "LLM fine-tuning" in items[0].content

    def test_channel_error_does_not_abort_other_channels(self) -> None:
        channels = [
            YouTubeChannel(name="Good", channel_id="UCgood", max_videos=5),
            YouTubeChannel(name="Bad", channel_id="UCbad", max_videos=5),
        ]
        cfg = _make_config(channels)
        fetcher = YouTubeFetcher(cfg)

        def get_side_effect(url: str, params: dict[str, str], timeout: int) -> MagicMock:
            if params["channelId"] == "UCgood":
                response = MagicMock()
                response.raise_for_status.return_value = None
                response.json.return_value = _search_response("vid1")
                return response
            raise httpx.HTTPError("DNS failure")

        with (
            _with_api_key(),
            patch("src.fetchers.youtube.httpx.get", side_effect=get_side_effect),
            patch("src.retry.time.sleep", return_value=None),
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
            _with_api_key(),
            patch("src.fetchers.youtube._fetch_json", return_value=_search_response("vid1")),
            patch.object(fetcher._api, "fetch", return_value=[snippet]),
        ):
            items = fetcher.fetch(set())

        assert len(items[0].content) == _MAX_CONTENT_CHARS

    def test_empty_feed_returns_empty(self) -> None:
        empty_response = {"items": []}
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with (
            _with_api_key(),
            patch("src.fetchers.youtube._fetch_json", return_value=empty_response),
        ):
            items = fetcher.fetch(set())

        assert items == []

    def test_missing_api_key_logs_error(self, caplog) -> None:
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)

        with caplog.at_level("ERROR"):
            items = fetcher.fetch(set())

        assert items == []
        assert "YOUTUBE_API_KEY" in caplog.text


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
