"""Tests for src/fetchers/youtube.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.config import YouTubeChannel, YouTubeConfig
from src.fetchers.youtube import YouTubeFetcher, _is_short, _parse_date


def _make_config(channels: list[YouTubeChannel] | None = None) -> YouTubeConfig:
    return YouTubeConfig(
        enabled=True,
        max_videos_per_channel=5,
        channels=channels
        or [YouTubeChannel(name="Test Channel", channel_id="UCtest123", max_videos=5)],
    )


def _make_search_results(
    *video_ids: str,
    descriptions: dict[str, str] | None = None,
    titles: dict[str, str] | None = None,
) -> list[dict]:
    """Build a minimal YouTube Data API search response for testing."""
    desc_map = descriptions or {}
    title_map = titles or {}
    return [
        {
            "id": {"videoId": vid},
            "snippet": {
                "title": title_map.get(vid, f"{vid} title"),
                "description": desc_map.get(vid, ""),
                "publishedAt": "2026-02-21T07:00:00Z",
            },
        }
        for vid in video_ids
    ]


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

    def test_missing_api_key_raises(self) -> None:
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = ""
        with pytest.raises(RuntimeError, match="YOUTUBE_API_KEY"):
            fetcher.fetch(set())

    def test_already_processed_skipped(self) -> None:
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"

        with (
            patch.object(fetcher, "_search_channel", return_value=_make_search_results("vid1")),
            patch.object(fetcher._transcript_api, "fetch") as mock_transcript,
        ):
            items = fetcher.fetch(already_processed={"vid1"})

        assert items == []
        mock_transcript.assert_not_called()

    def test_fetches_new_video(self) -> None:
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"

        with (
            patch.object(fetcher, "_search_channel", return_value=_make_search_results("vid1")),
            patch.object(
                fetcher._transcript_api, "fetch", return_value=_mock_transcript("transcript text")
            ),
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
        fetcher._api_key = "test-key"

        with (
            patch.object(fetcher, "_search_channel", return_value=_make_search_results("v1", "v2")),
            patch.object(fetcher._transcript_api, "fetch", return_value=_mock_transcript()),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 2

    def test_search_channel_called_with_max_videos(self) -> None:
        """max_videos is forwarded to the API as maxResults."""
        cfg = _make_config([YouTubeChannel(name="Ch", channel_id="UCtest", max_videos=3)])
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"

        with patch.object(fetcher, "_search_channel", return_value=[]) as mock_search:
            fetcher.fetch(set())

        mock_search.assert_called_once_with("UCtest", 3)

    def test_includes_item_when_transcript_unavailable(self) -> None:
        """Item is still emitted when transcript fails; content falls back to description."""
        from youtube_transcript_api import NoTranscriptFound

        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"

        with (
            patch.object(
                fetcher,
                "_search_channel",
                return_value=_make_search_results("v1", "v2"),
            ),
            patch.object(fetcher._transcript_api, "fetch") as mock_transcript,
        ):
            mock_transcript.side_effect = [
                NoTranscriptFound("v1", [], MagicMock()),
                _mock_transcript("second"),
            ]
            items = fetcher.fetch(set())

        # Both items returned; v1 has no description in the test data so content is ""
        assert len(items) == 2
        assert items[0].id == "v1"
        assert items[0].content == ""
        assert items[1].id == "v2"
        assert items[1].content == "second"

    def test_uses_description_when_transcript_blocked(self) -> None:
        """Cloud IP blocks transcript → item appears with API description as content."""
        from youtube_transcript_api import NoTranscriptFound

        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"
        feed = _make_search_results("vid1", descriptions={"vid1": "Deep dive into LLM fine-tuning"})

        with (
            patch.object(fetcher, "_search_channel", return_value=feed),
            patch.object(
                fetcher._transcript_api,
                "fetch",
                side_effect=NoTranscriptFound("vid1", [], MagicMock()),
            ),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 1
        assert items[0].id == "vid1"
        assert "LLM fine-tuning" in items[0].content

    def test_channel_error_propagates(self) -> None:
        """Channel errors propagate out of fetch() so they are captured in source_errors."""
        channels = [
            YouTubeChannel(name="Good", channel_id="UCgood", max_videos=5),
            YouTubeChannel(name="Bad", channel_id="UCbad", max_videos=5),
        ]
        cfg = _make_config(channels)
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"

        def search_side(channel_id: str, max_results: int) -> list[dict]:
            if "UCgood" in channel_id:
                return _make_search_results("vid1")
            raise ConnectionError("API unreachable")

        # with_backoff retries the ConnectionError 3 times then wraps it in RuntimeError
        with (
            patch.object(fetcher, "_search_channel", side_effect=search_side),
            patch.object(fetcher._transcript_api, "fetch", return_value=_mock_transcript()),
            pytest.raises(RuntimeError),
        ):
            fetcher.fetch(set())

    def test_empty_channel_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Wrong channel ID (empty API response) logs a warning instead of raising."""
        import logging

        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"

        with (
            patch.object(fetcher, "_search_channel", return_value=[]),
            caplog.at_level(logging.WARNING),
        ):
            items = fetcher.fetch(set())

        assert items == []
        assert any("No videos returned" in r.message for r in caplog.records)

    def test_content_truncated_at_limit(self) -> None:
        from src.fetchers.youtube import _MAX_CONTENT_CHARS

        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"
        snippet = MagicMock()
        snippet.text = "x " * 10_000

        with (
            patch.object(fetcher, "_search_channel", return_value=_make_search_results("vid1")),
            patch.object(fetcher._transcript_api, "fetch", return_value=[snippet]),
        ):
            items = fetcher.fetch(set())

        assert len(items[0].content) == _MAX_CONTENT_CHARS

    def test_skips_youtube_shorts(self) -> None:
        """Videos with #Shorts in the title should be filtered out."""
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"
        feed = _make_search_results(
            "short1",
            "regular1",
            titles={"short1": "Cool clip #Shorts", "regular1": "Deep dive into LLMs"},
        )

        with (
            patch.object(fetcher, "_search_channel", return_value=feed),
            patch.object(fetcher._transcript_api, "fetch", return_value=_mock_transcript()),
        ):
            items = fetcher.fetch(set())

        assert len(items) == 1
        assert items[0].id == "regular1"

    def test_skips_shorts_case_insensitive(self) -> None:
        """#short and #SHORTS should both be filtered."""
        cfg = _make_config()
        fetcher = YouTubeFetcher(cfg)
        fetcher._api_key = "test-key"
        feed = _make_search_results(
            "s1",
            "s2",
            titles={"s1": "My #short video", "s2": "Analysis #SHORTS test"},
        )

        with (
            patch.object(fetcher, "_search_channel", return_value=feed),
            patch.object(fetcher._transcript_api, "fetch", return_value=_mock_transcript()),
        ):
            items = fetcher.fetch(set())

        assert items == []


class TestYouTubeFetcherProxyConfig:
    """Tests for proxy configuration support in YouTubeFetcher.

    YouTube blocks transcript requests from cloud/datacenter IPs (GitHub Actions).
    The youtube-transcript-api library supports proxy configuration via
    WebshareProxyConfig (residential proxy service) or GenericProxyConfig
    (arbitrary HTTP/HTTPS proxy URL).  These tests verify that YouTubeFetcher
    reads the relevant env vars and wires them into the transcript API.
    """

    def test_no_proxy_when_no_env_vars_set(self) -> None:
        """Default: no proxy config when proxy env vars are absent."""
        cfg = _make_config()
        with patch.dict("os.environ", {}, clear=False):
            # Ensure proxy vars are absent
            import os

            os.environ.pop("WEBSHARE_PROXY_USERNAME", None)
            os.environ.pop("WEBSHARE_PROXY_PASSWORD", None)
            os.environ.pop("YOUTUBE_PROXY_URL", None)
            fetcher = YouTubeFetcher(cfg)
        assert fetcher._transcript_api._fetcher._proxy_config is None

    def test_webshare_proxy_used_when_env_vars_set(self) -> None:
        """When WEBSHARE_PROXY_USERNAME and WEBSHARE_PROXY_PASSWORD are set,
        YouTubeTranscriptApi is initialised with a WebshareProxyConfig."""
        from youtube_transcript_api.proxies import WebshareProxyConfig

        cfg = _make_config()
        with patch.dict(
            "os.environ",
            {"WEBSHARE_PROXY_USERNAME": "user123", "WEBSHARE_PROXY_PASSWORD": "pass456"},
        ):
            fetcher = YouTubeFetcher(cfg)

        proxy = fetcher._transcript_api._fetcher._proxy_config
        assert isinstance(proxy, WebshareProxyConfig)

    def test_generic_proxy_used_when_youtube_proxy_url_set(self) -> None:
        """When YOUTUBE_PROXY_URL is set, YouTubeTranscriptApi is initialised
        with a GenericProxyConfig using that URL for both http and https."""
        from youtube_transcript_api.proxies import GenericProxyConfig

        cfg = _make_config()
        with patch.dict(
            "os.environ",
            {"YOUTUBE_PROXY_URL": "http://myproxy.example.com:8080"},
        ):
            fetcher = YouTubeFetcher(cfg)

        proxy = fetcher._transcript_api._fetcher._proxy_config
        assert isinstance(proxy, GenericProxyConfig)

    def test_webshare_takes_precedence_over_generic_proxy(self) -> None:
        """When both WEBSHARE_* and YOUTUBE_PROXY_URL are set, Webshare wins."""
        from youtube_transcript_api.proxies import WebshareProxyConfig

        cfg = _make_config()
        with patch.dict(
            "os.environ",
            {
                "WEBSHARE_PROXY_USERNAME": "user",
                "WEBSHARE_PROXY_PASSWORD": "pass",
                "YOUTUBE_PROXY_URL": "http://other.example.com:8080",
            },
        ):
            fetcher = YouTubeFetcher(cfg)

        proxy = fetcher._transcript_api._fetcher._proxy_config
        assert isinstance(proxy, WebshareProxyConfig)

    def test_only_webshare_username_no_password_no_proxy(self) -> None:
        """Partial Webshare credentials (username only) do not create a proxy."""
        import os

        cfg = _make_config()
        os.environ.pop("WEBSHARE_PROXY_PASSWORD", None)
        os.environ.pop("YOUTUBE_PROXY_URL", None)
        with patch.dict("os.environ", {"WEBSHARE_PROXY_USERNAME": "user"}, clear=False):
            fetcher = YouTubeFetcher(cfg)

        assert fetcher._transcript_api._fetcher._proxy_config is None

    def test_only_webshare_password_no_username_no_proxy(self) -> None:
        """Partial Webshare credentials (password only) do not create a proxy."""
        import os

        cfg = _make_config()
        os.environ.pop("WEBSHARE_PROXY_USERNAME", None)
        os.environ.pop("YOUTUBE_PROXY_URL", None)
        with patch.dict("os.environ", {"WEBSHARE_PROXY_PASSWORD": "pass"}, clear=False):
            fetcher = YouTubeFetcher(cfg)

        assert fetcher._transcript_api._fetcher._proxy_config is None

    def test_partial_webshare_with_proxy_url_uses_generic(self) -> None:
        """Partial Webshare credentials (username only) + YOUTUBE_PROXY_URL → falls through to
        GenericProxyConfig, not Webshare."""
        import os

        from youtube_transcript_api.proxies import GenericProxyConfig

        cfg = _make_config()
        os.environ.pop("WEBSHARE_PROXY_PASSWORD", None)
        with patch.dict(
            "os.environ",
            {
                "WEBSHARE_PROXY_USERNAME": "user",
                "YOUTUBE_PROXY_URL": "http://myproxy.example.com:8080",
            },
            clear=False,
        ):
            fetcher = YouTubeFetcher(cfg)

        proxy = fetcher._transcript_api._fetcher._proxy_config
        assert isinstance(proxy, GenericProxyConfig)


class TestDailyDigestWorkflowProxyEnvVars:
    """Verify the daily-digest workflow wires all proxy env vars.

    YouTube transcript proxy support only works in CI if the workflow
    injects the secrets as environment variables into the pipeline step.
    A missing env var means the feature is silently disabled even when
    secrets are configured.
    """

    def test_workflow_passes_webshare_proxy_username(self) -> None:
        """WEBSHARE_PROXY_USERNAME must be injected from secrets into the digest step."""
        import yaml

        workflow_path = (
            __import__("pathlib").Path(__file__).parent.parent
            / ".github"
            / "workflows"
            / "daily-digest.yml"
        )
        workflow = yaml.safe_load(workflow_path.read_text())
        env = workflow["jobs"]["digest"]["steps"][3]["env"]  # "Run digest pipeline" step
        assert "WEBSHARE_PROXY_USERNAME" in env, (
            "WEBSHARE_PROXY_USERNAME must be passed to the digest step; "
            "without it, transcript proxy support is silently disabled in CI"
        )

    def test_workflow_passes_webshare_proxy_password(self) -> None:
        """WEBSHARE_PROXY_PASSWORD must be injected from secrets into the digest step."""
        import yaml

        workflow_path = (
            __import__("pathlib").Path(__file__).parent.parent
            / ".github"
            / "workflows"
            / "daily-digest.yml"
        )
        workflow = yaml.safe_load(workflow_path.read_text())
        env = workflow["jobs"]["digest"]["steps"][3]["env"]
        assert "WEBSHARE_PROXY_PASSWORD" in env, (
            "WEBSHARE_PROXY_PASSWORD must be passed to the digest step; "
            "without it, transcript proxy support is silently disabled in CI"
        )

    def test_workflow_passes_youtube_proxy_url(self) -> None:
        """YOUTUBE_PROXY_URL must be injected from secrets into the digest step."""
        import yaml

        workflow_path = (
            __import__("pathlib").Path(__file__).parent.parent
            / ".github"
            / "workflows"
            / "daily-digest.yml"
        )
        workflow = yaml.safe_load(workflow_path.read_text())
        env = workflow["jobs"]["digest"]["steps"][3]["env"]
        assert "YOUTUBE_PROXY_URL" in env, (
            "YOUTUBE_PROXY_URL must be passed to the digest step; "
            "without it, generic proxy support is silently disabled in CI"
        )


class TestIsShort:
    def test_shorts_hashtag_detected(self) -> None:
        assert _is_short("My video #Shorts") is True

    def test_short_hashtag_detected(self) -> None:
        assert _is_short("Quick tip #short") is True

    def test_uppercase_shorts_detected(self) -> None:
        assert _is_short("Cool #SHORTS clip") is True

    def test_regular_title_not_detected(self) -> None:
        assert _is_short("Deep dive into LLM fine-tuning") is False

    def test_word_shorts_without_hash_not_detected(self) -> None:
        """'shorts' without the # is not a YouTube Shorts hashtag."""
        assert _is_short("Best shorts for summer") is False


class TestParseDate:
    def test_returns_none_for_empty_string(self) -> None:
        assert _parse_date("") is None

    def test_parses_iso_format(self) -> None:
        result = _parse_date("2026-02-21T07:00:00+00:00")
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 21

    def test_parses_youtube_api_format(self) -> None:
        """YouTube Data API returns dates with Z suffix — Python 3.11+ handles this."""
        result = _parse_date("2026-02-21T07:00:00Z")
        assert result is not None
        assert result.year == 2026

    def test_returns_none_for_invalid_format(self) -> None:
        assert _parse_date("not-a-date") is None
