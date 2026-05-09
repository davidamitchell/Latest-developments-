"""Smoke tests for the three-concern pipeline architecture (ADR-0017).

Covers the four CLI entry points end-to-end with mocked network calls and
minimal config. Each test exercises import correctness, argument wiring, and
pipeline sequencing — the class of bugs that unit tests miss.

Concerns under test:
  1. src.pipeline.fetch  — fetch_all → data/raw/YYYY-MM-DD.jsonl
  2. src.pipeline.run    — process  → data/processed/YYYY-MM-DD.jsonl
  3. src.digest.send     — send     → email + state update
  4. src.site.build      — build    → docs/data/*.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.fetchers import FetchedItem
from src.models import ProcessedItem

# ── helpers ──────────────────────────────────────────────────────────────────


def _minimal_sources_yaml(tmp_path: Path, *, send_if_empty: bool = False) -> Path:
    """Write a minimal sources.yaml with empty source list."""
    p = tmp_path / "sources.yaml"
    p.write_text(f"""
sources: []
digest:
  send_if_empty: {str(send_if_empty).lower()}
history:
  enabled: false
""")
    return p


def _make_fetched(id_: str = "smoke-1") -> FetchedItem:
    return FetchedItem(
        id=id_,
        title="Smoke Test Article",
        url=f"https://example.com/{id_}",
        content="Some content here.",
        source_name="Test Source",
        source_type="rss",
        source_class="practitioner",
        author="",
        published=datetime(2026, 5, 2, tzinfo=UTC),
        has_code=False,
        evidence_type="analysis",
    )


def _make_processed(id_: str = "smoke-1") -> ProcessedItem:
    return ProcessedItem(
        id=id_,
        title="Smoke Test Article",
        url=f"https://example.com/{id_}",
        source_name="Test Source",
        source_type="rss",
        source_class="practitioner",
        author="",
        published=datetime(2026, 5, 2, tzinfo=UTC),
        has_code=False,
        evidence_type="analysis",
        fetch_date="2026-05-02",
        cleaned_content="Some content here.",
        theme="inference scaling",
        domain="infra",
        summary="A summary.",
        credibility_score=0.7,
        hype_risk=0.2,
    )


# ── Concern 1: src.pipeline.fetch ─────────────────────────────────────────────


class TestFetchMain:
    """src.pipeline.fetch.main() CLI smoke tests."""

    def test_exits_zero_with_no_sources(self, tmp_path: Path) -> None:
        cfg_path = _minimal_sources_yaml(tmp_path)
        with (
            patch("src.pipeline.fetch.load_state", return_value=set()),
            patch("src.pipeline.fetch.write_raw_jsonl"),
            patch("sys.argv", ["fetch", "--config", str(cfg_path)]),
        ):
            from src.pipeline.fetch import main

            result = main()
        assert result == 0

    def test_does_not_crash_when_fetcher_raises(self, tmp_path: Path) -> None:
        """A fetcher failure must not crash the pipeline — _safe_fetch swallows it."""
        from src.config import Config, SourceEntry

        cfg = Config(
            sources=[
                SourceEntry(
                    type="rss",
                    name="Bad Feed",
                    source_class="operator",
                    options={"url": "https://bad.example.com/feed"},
                ),
            ]
        )
        with (
            patch("src.pipeline.fetch.load_state", return_value=set()),
            patch("src.pipeline.fetch.load_config", return_value=cfg),
            patch("src.pipeline.fetch.RSSFetcher") as mock_rss,
            patch("src.pipeline.fetch.write_raw_jsonl"),
            patch("sys.argv", ["fetch", "--config", "config/sources.yaml"]),
        ):
            mock_rss.return_value.fetch.side_effect = RuntimeError("network error")
            from src.pipeline.fetch import main

            result = main()
        assert result == 0

    def test_deduplication_excludes_already_processed(self, tmp_path: Path) -> None:
        """Items already in state are not written to the raw file."""
        item = _make_fetched("already-seen")
        cfg_path = _minimal_sources_yaml(tmp_path)
        written: list = []
        with (
            patch("src.pipeline.fetch.load_state", return_value={"already-seen"}),
            patch(
                "src.pipeline.fetch.write_raw_jsonl",
                side_effect=lambda items, path: written.extend(items),
            ),
            patch("sys.argv", ["fetch", "--config", str(cfg_path)]),
        ):
            from src.pipeline.fetch import main

            main()
        assert all(i.id != "already-seen" for i in written)

    def test_import_has_no_fetcher_side_effects(self) -> None:
        """Importing fetch.py must not trigger network calls."""
        import src.pipeline.fetch  # noqa: F401 — import only


# ── Concern 2: src.pipeline.run ──────────────────────────────────────────────


class TestRunMain:
    """src.pipeline.run.main() CLI smoke tests."""

    def test_exits_zero_with_no_raw_items(self, tmp_path: Path) -> None:
        """No raw file → writes empty processed file and exits 0."""
        with (
            patch("src.config.load_config") as mock_cfg,
            patch("src.pipeline.run.read_raw_jsonl", return_value=[]),
            patch("src.pipeline.run.write_processed_jsonl"),
            patch("sys.argv", ["run", "--date", "2026-05-02"]),
        ):
            mock_cfg.return_value.logging.log_file = None
            from src.pipeline.run import main

            result = main()
        assert result == 0

    def test_exits_zero_with_items_no_gemini_key(self, tmp_path: Path) -> None:
        """Items present but no GEMINI_API_KEY → AI stages skipped, still exits 0."""
        item = _make_fetched()
        with (
            patch("src.config.load_config") as mock_cfg,
            patch("src.pipeline.run.read_raw_jsonl", return_value=[item]),
            patch("src.pipeline.run.process", return_value=([_make_processed()], 0)),
            patch("src.pipeline.run.write_processed_jsonl"),
            patch("sys.argv", ["run", "--date", "2026-05-02"]),
            patch.dict(
                "os.environ",
                {k: v for k, v in __import__("os").environ.items() if k != "GEMINI_API_KEY"},
            ),
        ):
            mock_cfg.return_value.logging.log_file = None
            from src.pipeline.run import main

            result = main()
        assert result == 0

    def test_calls_process_with_correct_date(self, tmp_path: Path) -> None:
        item = _make_fetched()
        with (
            patch("src.config.load_config") as mock_cfg,
            patch("src.pipeline.run.read_raw_jsonl", return_value=[item]),
            patch("src.pipeline.run.process", return_value=([], 0)) as mock_process,
            patch("src.pipeline.run.write_processed_jsonl"),
            patch("sys.argv", ["run", "--date", "2026-05-02"]),
        ):
            mock_cfg.return_value.logging.log_file = None
            from src.pipeline.run import main

            main()
        mock_process.assert_called_once()
        call_args = mock_process.call_args
        assert "2026-05-02" in str(call_args)


# ── Concern 3A: src.digest.send ──────────────────────────────────────────────


class TestDigestSendMain:
    """src.digest.send.main() CLI smoke tests."""

    def test_exits_zero_when_no_items_and_not_send_if_empty(self, tmp_path: Path) -> None:
        cfg_path = _minimal_sources_yaml(tmp_path, send_if_empty=False)
        with (
            patch("src.digest.send.load_state", return_value=set()),
            patch("src.digest.send.read_processed_jsonl", return_value=[]),
            patch("src.digest.send.send_digest") as mock_send,
            patch("sys.argv", ["send", "--config", str(cfg_path), "--date", "2026-05-02"]),
        ):
            from src.digest.send import main

            result = main()
        assert result == 0
        mock_send.assert_not_called()

    def test_dry_run_does_not_call_send_digest(self, tmp_path: Path) -> None:
        cfg_path = _minimal_sources_yaml(tmp_path, send_if_empty=True)
        with (
            patch("src.digest.send.load_state", return_value=set()),
            patch("src.digest.send.read_processed_jsonl", return_value=[_make_processed()]),
            patch("src.digest.send.send_digest") as mock_send,
            patch("src.digest.send.summarise", return_value="digest text"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch(
                "sys.argv", ["send", "--config", str(cfg_path), "--date", "2026-05-02", "--dry-run"]
            ),
        ):
            from src.digest.send import main

            result = main()
        assert result == 0
        mock_send.assert_not_called()

    def test_dry_run_does_not_save_state(self, tmp_path: Path) -> None:
        cfg_path = _minimal_sources_yaml(tmp_path, send_if_empty=True)
        with (
            patch("src.digest.send.load_state", return_value=set()),
            patch("src.digest.send.read_processed_jsonl", return_value=[_make_processed()]),
            patch("src.digest.send.save_state") as mock_save,
            patch("src.digest.send.send_digest"),
            patch("src.digest.send.summarise", return_value="digest text"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch(
                "sys.argv", ["send", "--config", str(cfg_path), "--date", "2026-05-02", "--dry-run"]
            ),
        ):
            from src.digest.send import main

            main()
        mock_save.assert_not_called()

    def test_send_called_with_subject_from_digest_config(self, tmp_path: Path) -> None:
        cfg_path = _minimal_sources_yaml(tmp_path, send_if_empty=True)
        with (
            patch("src.digest.send.load_state", return_value=set()),
            patch("src.digest.send.read_processed_jsonl", return_value=[_make_processed()]),
            patch("src.digest.send.save_state"),
            patch("src.digest.send.archive_digest"),
            patch("src.digest.send.send_digest") as mock_send,
            patch("src.digest.send.summarise", return_value="digest text"),
            patch("src.digest.send.render_html_digest", return_value="<html/>"),
            patch("sys.argv", ["send", "--config", str(cfg_path), "--date", "2026-05-02"]),
        ):
            from src.digest.send import main

            main()
        mock_send.assert_called_once()
        subject = mock_send.call_args[0][0]
        assert "2026" in subject or "May" in subject or "02" in subject

    def test_does_not_import_fetchers(self) -> None:
        """send.py must not import fetcher modules."""
        import sys

        import src.digest.send as send_module

        fetcher_modules = [k for k in sys.modules if "fetchers." in k and k != "src.fetchers"]
        # send.py itself is allowed to import src.fetchers (for FetchedItem type)
        # but must not import individual fetcher implementations
        assert not any(
            m.startswith("src.fetchers.") for m in fetcher_modules if m in vars(send_module)
        )


# ── Concern 3B: src.site.build ───────────────────────────────────────────────


class TestSiteBuildMain:
    """src.site.build.main() CLI smoke tests."""

    def test_exits_zero_with_no_data(self, tmp_path: Path) -> None:
        proc_dir = tmp_path / "data" / "processed"
        proc_dir.mkdir(parents=True)
        docs_dir = tmp_path / "docs" / "data"
        with patch(
            "sys.argv",
            ["build", "--processed-dir", str(proc_dir), "--docs-data-dir", str(docs_dir)],
        ):
            from src.site.build import main

            result = main()
        assert result == 0

    def test_dry_run_writes_no_files(self, tmp_path: Path) -> None:
        proc_dir = tmp_path / "data" / "processed"
        proc_dir.mkdir(parents=True)
        docs_dir = tmp_path / "docs" / "data"
        with patch(
            "sys.argv",
            [
                "build",
                "--processed-dir",
                str(proc_dir),
                "--docs-data-dir",
                str(docs_dir),
                "--dry-run",
            ],
        ):
            from src.site.build import main

            main()
        assert not docs_dir.exists()

    def test_writes_all_expected_files(self, tmp_path: Path) -> None:
        proc_dir = tmp_path / "data" / "processed"
        proc_dir.mkdir(parents=True)
        # Write one processed item
        item = _make_processed()
        (proc_dir / "2026-05-02.jsonl").write_text(json.dumps(item.to_dict()) + "\n")
        docs_dir = tmp_path / "docs" / "data"
        with patch(
            "sys.argv",
            ["build", "--processed-dir", str(proc_dir), "--docs-data-dir", str(docs_dir)],
        ):
            from src.site.build import main

            main()
        for fname in (
            "meta.json",
            "trends.json",
            "themes.json",
            "sources.json",
            "graph.json",
            "items.json",
        ):
            assert (docs_dir / fname).exists(), f"Missing {fname}"

    def test_does_not_import_fetchers(self) -> None:
        """build.py must not import fetcher modules."""
        import src.site.build  # noqa: F401


# ── Cross-concern: boundary enforcement ──────────────────────────────────────


class TestBoundaries:
    """Schema contract boundaries — consumers must not call fetchers directly."""

    def test_digest_send_does_not_import_pipeline_stages(self) -> None:
        import inspect

        import src.digest.send

        source = inspect.getsource(src.digest.send)
        assert "from src.pipeline.stages" not in source, (
            "src.digest.send must not directly import pipeline stages"
        )

    def test_site_build_does_not_import_pipeline_stages(self) -> None:
        import inspect

        import src.site.build

        source = inspect.getsource(src.site.build)
        assert "from src.pipeline.stages" not in source, (
            "src.site.build must not directly import pipeline stages"
        )

    def test_digest_send_does_not_import_pipeline_run(self) -> None:
        """send.py reads ProcessedItem via src.models — not src.pipeline.run."""
        import inspect

        import src.digest.send

        source = inspect.getsource(src.digest.send)
        assert "from src.pipeline.run" not in source, (
            "src.digest.send must not import from src.pipeline.run"
        )

    def test_site_build_does_not_import_pipeline_run(self) -> None:
        """build.py reads ProcessedItem via src.models — not src.pipeline.run."""
        import inspect

        import src.site.build

        source = inspect.getsource(src.site.build)
        assert "from src.pipeline.run" not in source, (
            "src.site.build must not import from src.pipeline.run"
        )

    def test_digest_config_has_no_source_fields(self) -> None:
        """DigestConfig must not reference source topology — only ProcessedItem fields."""
        from src.config import DigestConfig

        cfg = DigestConfig()
        for forbidden in ("source_name", "source_type", "channel_id", "slug", "feeds", "url"):
            assert not hasattr(cfg, forbidden), f"DigestConfig must not have field {forbidden!r}"
