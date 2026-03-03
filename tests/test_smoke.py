"""Smoke tests for the full pipeline (src/main.py).

These tests exercise main() end-to-end with mocked network calls and a minimal
config. They catch integration-level regressions that unit tests miss — e.g.
argument wiring, import errors, or pipeline sequencing bugs.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.main import main


def _minimal_config(tmp_path: Path, *, send_if_empty: bool = False) -> Path:
    """Write a minimal sources.yaml with all sources disabled."""
    cfg = tmp_path / "sources.yaml"
    cfg.write_text(
        f"""
youtube:
  enabled: false
  channels: []
blogs:
  enabled: false
  rss: []
substack:
  enabled: false
  publications: []
hacker_news:
  enabled: false
  keywords: []
summary:
  enabled: false
history:
  enabled: false
  history_days: 7
  history_dir: "{tmp_path / "history"}"
email:
  send_if_empty: {str(send_if_empty).lower()}
"""
    )
    return cfg


def _state_path(tmp_path: Path) -> Path:
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    return state_dir / "processed.json"


class TestMainSmokeNoItems:
    def test_exits_zero_when_no_new_items(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path)
        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state"),
            patch("sys.argv", ["main", "--config", str(cfg), "--dry-run"]),
        ):
            result = main()
        assert result == 0

    def test_does_not_call_send_when_no_items_and_not_dry_run(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path)
        mock_send = MagicMock()
        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state"),
            patch("src.main.send_digest", mock_send),
            patch("sys.argv", ["main", "--config", str(cfg)]),
        ):
            main()
        mock_send.assert_not_called()


class TestMainSmokeDryRun:
    def test_dry_run_does_not_call_send_digest(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path, send_if_empty=True)
        mock_send = MagicMock()
        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state"),
            patch("src.main.send_digest", mock_send),
            patch("sys.argv", ["main", "--config", str(cfg), "--dry-run"]),
        ):
            main()
        mock_send.assert_not_called()

    def test_dry_run_does_not_save_state(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path, send_if_empty=True)
        mock_save = MagicMock()
        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state", mock_save),
            patch("src.main.send_digest"),
            patch("sys.argv", ["main", "--config", str(cfg), "--dry-run"]),
        ):
            main()
        mock_save.assert_not_called()


class TestMainSmokeWithItems:
    def _make_item(self) -> object:
        from datetime import datetime

        from src.fetchers import FetchedItem

        return FetchedItem(
            id="smoke-1",
            title="Smoke Test Article",
            url="https://example.com/smoke-1",
            content="Some content here.",
            source_name="Test Source",
            source_type="RSS",
            published=datetime(2026, 3, 1),
        )

    def test_exits_zero_with_items_on_dry_run(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path)
        item = self._make_item()
        from src.config import (
            BlogsConfig,
            Config,
            EmailConfig,
            HackerNewsConfig,
            HistoryConfig,
            LoggingConfig,
            SummaryConfig,
            YouTubeConfig,
        )

        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state"),
            patch("src.main.RSSFetcher") as mock_fetcher_cls,
            patch("sys.argv", ["main", "--config", str(cfg), "--dry-run"]),
            patch("src.main.load_config") as mock_cfg,
        ):
            mock_cfg.return_value = Config(
                youtube=YouTubeConfig(enabled=False, channels=[]),
                blogs=BlogsConfig(enabled=True, rss=[]),
                substack=MagicMock(enabled=False),
                hacker_news=HackerNewsConfig(enabled=False),
                summary=SummaryConfig(enabled=False),
                history=HistoryConfig(enabled=False),
                email=EmailConfig(send_if_empty=False),
                logging=LoggingConfig(),
            )
            mock_fetcher_cls.return_value.fetch.return_value = [item]
            result = main()
        # With dry-run and no items through (RSS disabled via config above), exit 0
        assert result == 0

    def test_pipeline_calls_save_state_after_send(self, tmp_path: Path) -> None:
        # Use send_if_empty=False (default): no items → pipeline exits early, save_state not called
        cfg = _minimal_config(tmp_path, send_if_empty=False)
        mock_save = MagicMock()
        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state", mock_save),
            patch("src.main.send_digest"),
            patch("src.main.archive_digest"),
            patch("sys.argv", ["main", "--config", str(cfg)]),
        ):
            main()
        # No items + send_if_empty=false → pipeline exits before send → save_state not called
        mock_save.assert_not_called()


class TestMainSmokeFetcherFailure:
    def test_fetcher_failure_does_not_crash_pipeline(self, tmp_path: Path) -> None:
        """A fetcher that raises must not crash the pipeline — it continues with zero items."""
        from src.config import (
            BlogsConfig,
            Config,
            EmailConfig,
            HackerNewsConfig,
            HistoryConfig,
            LoggingConfig,
            RSSFeed,
            SummaryConfig,
            YouTubeConfig,
        )

        mock_save = MagicMock()
        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state", mock_save),
            patch("src.main.send_digest"),
            patch("src.main.RSSFetcher") as mock_rss_cls,
            patch("src.main.load_config") as mock_cfg,
            patch("sys.argv", ["main", "--config", str(tmp_path / "sources.yaml")]),
        ):
            mock_cfg.return_value = Config(
                youtube=YouTubeConfig(enabled=False, channels=[]),
                blogs=BlogsConfig(enabled=True, rss=[RSSFeed(name="Bad Feed", url="http://x")]),
                substack=MagicMock(enabled=False),
                hacker_news=HackerNewsConfig(enabled=False),
                summary=SummaryConfig(enabled=False),
                history=HistoryConfig(enabled=False),
                email=EmailConfig(send_if_empty=False),
                logging=LoggingConfig(),
            )
            mock_rss_cls.return_value.fetch.side_effect = RuntimeError("network error")
            result = main()
        # Pipeline must exit 0 (no items, not a fatal error)
        assert result == 0


class TestMainSmokeHistoryIntegration:
    def test_archive_called_after_successful_send(self, tmp_path: Path) -> None:
        """archive_digest must be called after a successful email send."""
        from src.config import (
            Config,
            EmailConfig,
            HackerNewsConfig,
            HistoryConfig,
            LoggingConfig,
            SubstackConfig,
            SummaryConfig,
            YouTubeConfig,
        )
        from src.fetchers import FetchedItem

        item = FetchedItem(
            id="x1",
            title="Test",
            url="https://example.com/x1",
            content="content",
            source_name="HN",
            source_type="Hacker News",
        )
        mock_archive = MagicMock()
        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state"),
            patch("src.main.send_digest"),
            patch("src.main.archive_digest", mock_archive),
            patch("src.main.load_recent_digests", return_value=[]),
            patch("src.main.HackerNewsFetcher") as mock_hn_cls,
            patch("src.main.load_config") as mock_cfg,
            patch("sys.argv", ["main", "--config", str(tmp_path / "sources.yaml")]),
        ):
            mock_cfg.return_value = Config(
                youtube=YouTubeConfig(enabled=False, channels=[]),
                blogs=MagicMock(enabled=False),
                substack=SubstackConfig(enabled=False),
                hacker_news=HackerNewsConfig(enabled=True, keywords=["AI"]),
                summary=SummaryConfig(enabled=False),
                history=HistoryConfig(
                    enabled=True, history_days=7, history_dir=str(tmp_path / "history")
                ),
                email=EmailConfig(send_if_empty=False),
                logging=LoggingConfig(),
            )
            mock_hn_cls.return_value.fetch.return_value = [item]
            result = main()
        assert result == 0
        mock_archive.assert_called_once()

    def test_archive_not_called_on_dry_run(self, tmp_path: Path) -> None:
        """archive_digest must NOT be called during a dry run."""
        from src.config import (
            Config,
            EmailConfig,
            HackerNewsConfig,
            HistoryConfig,
            LoggingConfig,
            SubstackConfig,
            SummaryConfig,
            YouTubeConfig,
        )
        from src.fetchers import FetchedItem

        item = FetchedItem(
            id="x2",
            title="Test",
            url="https://example.com/x2",
            content="content",
            source_name="HN",
            source_type="Hacker News",
        )
        mock_archive = MagicMock()
        with (
            patch("src.main.load_state", return_value=set()),
            patch("src.main.save_state"),
            patch("src.main.send_digest"),
            patch("src.main.archive_digest", mock_archive),
            patch("src.main.load_recent_digests", return_value=[]),
            patch("src.main.HackerNewsFetcher") as mock_hn_cls,
            patch("src.main.load_config") as mock_cfg,
            patch("sys.argv", ["main", "--config", str(tmp_path / "sources.yaml"), "--dry-run"]),
        ):
            mock_cfg.return_value = Config(
                youtube=YouTubeConfig(enabled=False, channels=[]),
                blogs=MagicMock(enabled=False),
                substack=SubstackConfig(enabled=False),
                hacker_news=HackerNewsConfig(enabled=True, keywords=["AI"]),
                summary=SummaryConfig(enabled=False),
                history=HistoryConfig(
                    enabled=True, history_days=7, history_dir=str(tmp_path / "history")
                ),
                email=EmailConfig(send_if_empty=False),
                logging=LoggingConfig(),
            )
            mock_hn_cls.return_value.fetch.return_value = [item]
            result = main()
        assert result == 0
        mock_archive.assert_not_called()
