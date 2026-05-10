"""TDD tests for src/pipeline/backfill.py — AI enrichment backfill."""

from __future__ import annotations

import dataclasses
import json
from unittest.mock import MagicMock, patch

import pytest

from src.models import ProcessedItem, write_processed_jsonl


def _make_processed(id_: str = "item-1", theme: str = "", summary: str = "") -> ProcessedItem:
    return ProcessedItem(
        id=id_,
        title="Test LLM Article",
        url=f"https://example.com/{id_}",
        source_name="Test Source",
        source_type="rss",
        source_class="practitioner",
        author="Alice",
        published=None,
        has_code=False,
        evidence_type="analysis",
        fetch_date="2026-05-09",
        cleaned_content="LLM inference research findings.",
        theme=theme,
        domain="unknown",
        summary=summary,
        concepts=[],
        actors=[],
        impact_vector="unknown",
        is_marketing=False,
        marketing_confidence=0.0,
        hype_risk=0.0,
        credibility_score=0.0,
    )


def _make_enrich_ok(theme: str = "inference scaling"):
    """Patch target for enrich() that succeeds without importing google.genai."""

    def _enrich(item, client, max_output_tokens=500):
        enriched = dataclasses.replace(
            item,
            theme=theme,
            domain="infra",
            concepts=["LLM", "inference"],
            actors=[],
            impact_vector="capability",
            summary="First sentence. Second sentence.",
            is_marketing=False,
            marketing_confidence=0.9,
        )
        return enriched, True

    return _enrich


def _make_enrich_fail():
    """Patch target for enrich() that returns ok=False."""

    def _enrich(item, client, max_output_tokens=500):
        return item, False

    return _enrich


def _make_429_error():
    """A fake ClientError with code=429 but no quota-metric details."""
    err = Exception("429 TooManyRequests")
    err.code = 429  # type: ignore[attr-defined]
    err.__module__ = "google.genai.errors"
    err.__class__ = type("ClientError", (Exception,), {"__module__": "google.genai.errors"})
    return err


# ── backfill_file ────────────────────────────────────────────────────────────


class TestBackfillFile:
    """backfill_file(path, client, ...) → (enriched, failed, stop)"""

    def test_unenriched_item_gets_theme(self, tmp_path):
        """Items with theme == '' are enriched and written back."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        item = _make_processed("a", theme="")
        write_processed_jsonl([item], path)

        with patch("src.pipeline.backfill.enrich", side_effect=_make_enrich_ok("inference scaling")):
            enriched, failed, stop = backfill_file(path, MagicMock(), _NullRateLimiter(), 500)

        assert enriched == 1
        assert failed == 0
        assert stop is False
        result = json.loads(path.read_text().strip())
        assert result["theme"] == "inference scaling"

    def test_enriched_item_is_not_re_processed(self, tmp_path):
        """Items that already have a theme are skipped without calling enrich."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        item = _make_processed("a", theme="existing theme")
        write_processed_jsonl([item], path)

        mock_enrich = MagicMock()
        with patch("src.pipeline.backfill.enrich", mock_enrich):
            enriched, failed, stop = backfill_file(path, MagicMock(), _NullRateLimiter(), 500)

        assert enriched == 0
        assert failed == 0
        assert stop is False
        mock_enrich.assert_not_called()
        result = json.loads(path.read_text().strip())
        assert result["theme"] == "existing theme"

    def test_mixed_file_enriches_only_unenriched(self, tmp_path):
        """Only items with theme == '' are enriched; others are preserved."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        items = [
            _make_processed("a", theme="existing"),
            _make_processed("b", theme=""),
            _make_processed("c", theme="also existing"),
        ]
        write_processed_jsonl(items, path)

        call_count = 0

        def _counting_enrich(item, client, max_output_tokens=500):
            nonlocal call_count
            call_count += 1
            return _make_enrich_ok("new theme")(item, client, max_output_tokens)

        with patch("src.pipeline.backfill.enrich", side_effect=_counting_enrich):
            enriched, failed, stop = backfill_file(path, MagicMock(), _NullRateLimiter(), 500)

        assert enriched == 1
        assert failed == 0
        assert call_count == 1
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        results = {json.loads(ln)["id"]: json.loads(ln)["theme"] for ln in lines}
        assert results["a"] == "existing"
        assert results["b"] == "new theme"
        assert results["c"] == "also existing"

    def test_empty_file_returns_zero(self, tmp_path):
        """An empty processed file returns (0, 0, False) without calling enrich."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        write_processed_jsonl([], path)

        mock_enrich = MagicMock()
        with patch("src.pipeline.backfill.enrich", mock_enrich):
            enriched, failed, stop = backfill_file(path, MagicMock(), _NullRateLimiter(), 500)

        assert enriched == 0
        assert failed == 0
        assert stop is False
        mock_enrich.assert_not_called()

    def test_failed_enrichment_counts_as_failed(self, tmp_path):
        """When enrich() returns ok=False, item stays unenriched and failed count increments."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        item = _make_processed("a", theme="")
        write_processed_jsonl([item], path)

        with (
            patch("src.pipeline.backfill.enrich", side_effect=_make_enrich_fail()),
            patch("src.retry.time.sleep"),
        ):
            enriched, failed, stop = backfill_file(path, MagicMock(), _NullRateLimiter(), 500)

        assert enriched == 0
        assert failed == 1
        assert stop is False
        result = json.loads(path.read_text().strip())
        assert result["theme"] == ""

    def test_quota_sentinel_stops_batch(self, tmp_path):
        """QuotaExhaustedEnrichError on item N stops all remaining items; stop=True."""
        from src.pipeline._quota import QuotaExhaustedEnrichError
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        items = [_make_processed(str(i), theme="") for i in range(3)]
        write_processed_jsonl(items, path)

        call_count = 0

        def _quota_on_first(item, client, max_output_tokens=500):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise QuotaExhaustedEnrichError
            return item, True

        with patch("src.pipeline.backfill.enrich", side_effect=_quota_on_first):
            enriched, failed, stop = backfill_file(path, MagicMock(), _NullRateLimiter(), 500)

        assert call_count == 1
        assert enriched == 0
        assert failed == 3
        assert stop is True

    def test_any_429_stops_batch(self, tmp_path):
        """A plain 429 ClientError (no quota-metric in details) stops the batch immediately."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        items = [_make_processed(str(i), theme="") for i in range(3)]
        write_processed_jsonl(items, path)

        call_count = 0

        class Fake429(Exception):
            code = 429

        def _429_on_first(item, client, max_output_tokens=500):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Fake429("rate limited")
            return item, True

        # Fake429 has __module__ = "builtins" so bypasses the google.genai isinstance check —
        # the is_rate_limited path must fire before the module check to catch it.
        with (
            patch("src.pipeline.backfill.enrich", side_effect=_429_on_first),
            patch("src.pipeline.backfill.is_rate_limited", return_value=True),
        ):
            enriched, failed, stop = backfill_file(path, MagicMock(), _NullRateLimiter(), 500)

        assert call_count == 1
        assert stop is True

    def test_budget_stops_after_n_items(self, tmp_path):
        """With budget=2, only 2 items are enriched even if more are available; stop=True."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        items = [_make_processed(str(i), theme="") for i in range(5)]
        write_processed_jsonl(items, path)

        call_count = 0

        def _count_calls(item, client, max_output_tokens=500):
            nonlocal call_count
            call_count += 1
            return _make_enrich_ok()(item, client, max_output_tokens)

        with patch("src.pipeline.backfill.enrich", side_effect=_count_calls):
            enriched, failed, stop = backfill_file(
                path, MagicMock(), _NullRateLimiter(), 500, budget=2
            )

        assert call_count == 2
        assert enriched == 2
        assert stop is True

    def test_programming_error_propagates(self, tmp_path):
        """Non-transport errors (e.g. AttributeError) are re-raised, not swallowed."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        write_processed_jsonl([_make_processed("a", theme="")], path)

        def _broken(item, client, max_output_tokens=500):
            raise AttributeError("unexpected None")

        with (
            pytest.raises(AttributeError, match="unexpected None"),
            patch("src.pipeline.backfill.enrich", side_effect=_broken),
        ):
            backfill_file(path, MagicMock(), _NullRateLimiter(), 500)

    def test_rate_limiter_called_per_unenriched_item(self, tmp_path):
        """Rate limiter .wait() is called once per item that needs enrichment."""
        from src.pipeline.backfill import backfill_file

        path = tmp_path / "2026-05-09.jsonl"
        items = [_make_processed("a", theme=""), _make_processed("b", theme="")]
        write_processed_jsonl(items, path)

        rate_limiter = MagicMock()
        with patch("src.pipeline.backfill.enrich", side_effect=_make_enrich_ok()):
            backfill_file(path, MagicMock(), rate_limiter, 500)

        assert rate_limiter.wait.call_count == 2


# ── backfill_all ─────────────────────────────────────────────────────────────


class TestBackfillAll:
    """backfill_all(processed_dir, client, ...) → (total_enriched, total_failed, files_updated)"""

    def test_scans_all_jsonl_files(self, tmp_path):
        """Processes every .jsonl file in the directory."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_all

        for date in ("2026-04-01", "2026-04-02"):
            p = tmp_path / f"{date}.jsonl"
            write_processed_jsonl([_make_processed(f"item-{date}", theme="")], p)

        with patch("src.pipeline.backfill.enrich", side_effect=_make_enrich_ok()):
            enriched, failed, files = backfill_all(tmp_path, MagicMock(), _NullRateLimiter(), 500)

        assert enriched == 2
        assert failed == 0
        assert files == 2

    def test_dry_run_does_not_write(self, tmp_path):
        """In dry_run mode, counts are reported but files are not modified."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_all

        path = tmp_path / "2026-05-09.jsonl"
        item = _make_processed("a", theme="")
        write_processed_jsonl([item], path)
        original = path.read_text()

        mock_enrich = MagicMock()
        with patch("src.pipeline.backfill.enrich", mock_enrich):
            enriched, failed, files = backfill_all(
                tmp_path, MagicMock(), _NullRateLimiter(), 500, dry_run=True
            )

        assert enriched == 1
        assert files == 1
        assert path.read_text() == original
        mock_enrich.assert_not_called()

    def test_files_with_no_unenriched_items_not_counted(self, tmp_path):
        """Files where all items are already enriched do not increment files_updated."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_all

        path = tmp_path / "2026-05-09.jsonl"
        write_processed_jsonl([_make_processed("a", theme="existing")], path)

        mock_enrich = MagicMock()
        with patch("src.pipeline.backfill.enrich", mock_enrich):
            enriched, failed, files = backfill_all(tmp_path, MagicMock(), _NullRateLimiter(), 500)

        assert enriched == 0
        assert files == 0
        mock_enrich.assert_not_called()

    def test_max_items_limits_total_enriched(self, tmp_path):
        """max_items=2 stops after enriching 2 items across all files."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_all

        for date in ("2026-04-01", "2026-04-02", "2026-04-03"):
            p = tmp_path / f"{date}.jsonl"
            write_processed_jsonl([_make_processed(f"item-{date}", theme="")], p)

        call_count = 0

        def _count(item, client, max_output_tokens=500):
            nonlocal call_count
            call_count += 1
            return _make_enrich_ok()(item, client, max_output_tokens)

        with patch("src.pipeline.backfill.enrich", side_effect=_count):
            enriched, failed, files = backfill_all(
                tmp_path, MagicMock(), _NullRateLimiter(), 500, max_items=2
            )

        assert call_count == 2
        assert enriched == 2

    def test_commit_progress_called_per_enriched_file(self, tmp_path):
        """When commit_progress=True, _git_commit_file is called once per file that gained enrichments."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_all

        for date in ("2026-04-01", "2026-04-02"):
            p = tmp_path / f"{date}.jsonl"
            write_processed_jsonl([_make_processed(f"item-{date}", theme="")], p)

        with (
            patch("src.pipeline.backfill.enrich", side_effect=_make_enrich_ok()),
            patch("src.pipeline.backfill._git_commit_file") as mock_commit,
        ):
            backfill_all(tmp_path, MagicMock(), _NullRateLimiter(), 500, commit_progress=True)

        assert mock_commit.call_count == 2

    def test_commit_progress_not_called_by_default(self, tmp_path):
        """_git_commit_file is not called unless commit_progress=True is explicitly passed."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_all

        path = tmp_path / "2026-04-01.jsonl"
        write_processed_jsonl([_make_processed("a", theme="")], path)

        with (
            patch("src.pipeline.backfill.enrich", side_effect=_make_enrich_ok()),
            patch("src.pipeline.backfill._git_commit_file") as mock_commit,
        ):
            backfill_all(tmp_path, MagicMock(), _NullRateLimiter(), 500)

        mock_commit.assert_not_called()

    def test_commit_progress_not_called_for_already_enriched_files(self, tmp_path):
        """_git_commit_file is not called for files where no items needed enrichment."""
        from src.pipeline.backfill import _NullRateLimiter, backfill_all

        path = tmp_path / "2026-04-01.jsonl"
        write_processed_jsonl([_make_processed("a", theme="existing")], path)

        with (
            patch("src.pipeline.backfill.enrich", MagicMock()),
            patch("src.pipeline.backfill._git_commit_file") as mock_commit,
        ):
            backfill_all(tmp_path, MagicMock(), _NullRateLimiter(), 500, commit_progress=True)

        mock_commit.assert_not_called()

    def test_quota_stop_halts_subsequent_files(self, tmp_path):
        """When quota is hit in file 1, file 2 is not touched."""
        from src.pipeline._quota import QuotaExhaustedEnrichError
        from src.pipeline.backfill import _NullRateLimiter, backfill_all

        for date in ("2026-04-01", "2026-04-02"):
            p = tmp_path / f"{date}.jsonl"
            write_processed_jsonl([_make_processed(f"item-{date}", theme="")], p)

        call_count = 0

        def _quota_always(item, client, max_output_tokens=500):
            nonlocal call_count
            call_count += 1
            raise QuotaExhaustedEnrichError

        with patch("src.pipeline.backfill.enrich", side_effect=_quota_always):
            enriched, failed, files = backfill_all(tmp_path, MagicMock(), _NullRateLimiter(), 500)

        assert call_count == 1
        assert enriched == 0
