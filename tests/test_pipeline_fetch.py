"""TDD tests for src/pipeline/fetch.py.

Tests specify the interface; implementation must make them pass.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from src.fetchers import FetchedItem


def _make_item(id_: str = "item-1", source_type: str = "rss") -> FetchedItem:
    return FetchedItem(
        id=id_,
        title="Test Title",
        url=f"https://example.com/{id_}",
        content="Some content about LLMs.",
        source_name="Test Source",
        source_type=source_type,
        source_class="practitioner",
        author="Alice",
        published=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        has_code=False,
        evidence_type="analysis",
    )


# ── fetch_all ───────────────────────────────────────────────────────────────


class TestFetchAll:
    """fetch_all(cfg, already_processed) → list[FetchedItem]"""

    def test_returns_list(self):
        """fetch_all returns a list (possibly empty) of FetchedItem."""
        from src.config import Config
        from src.pipeline.fetch import fetch_all

        cfg = Config()  # empty sources list → no fetchers
        result = fetch_all(cfg, already_processed=set())
        assert isinstance(result, list)

    def test_deduplication_excludes_known_ids(self):
        """Items whose id is in already_processed are excluded."""
        from src.config import Config
        from src.pipeline.fetch import fetch_all

        item = _make_item("known-id")
        cfg = Config()  # empty sources list

        # Patch _safe_fetch to return an item; it should still be excluded
        with patch("src.pipeline.fetch._safe_fetch") as mock_fetch:
            mock_fetch.return_value = [item]
            result = fetch_all(cfg, already_processed={"known-id"})

        # All items returned by fetch_all must not be in already_processed
        assert all(i.id not in {"known-id"} for i in result)

    def test_all_returned_items_are_fetched_items(self):
        """Every element returned by fetch_all is a FetchedItem."""
        from src.config import Config
        from src.pipeline.fetch import fetch_all

        cfg = Config()  # empty sources list → no fetchers
        result = fetch_all(cfg, already_processed=set())
        assert all(isinstance(i, FetchedItem) for i in result)

    def _fetch_all_with_items(self, items, max_age_days=7):
        """Helper: run fetch_all with a fake fetcher that returns the given items."""
        from src.config import Config
        from src.pipeline.fetch import fetch_all

        fake_fetcher = MagicMock()
        fake_fetcher.fetch.return_value = items
        cfg = Config()
        with patch("src.pipeline.fetch._build_fetchers", return_value=[("fake", fake_fetcher)]):
            return fetch_all(cfg, already_processed=set(), max_age_days=max_age_days)

    def test_age_filter_drops_old_items(self):
        """Items published more than max_age_days ago are excluded."""
        old_item = FetchedItem(
            id="old-1",
            title="Old",
            url="https://example.com/old",
            content="",
            source_name="S",
            source_type="rss",
            source_class="practitioner",
            author="",
            has_code=False,
            evidence_type="unknown",
            published=datetime(2020, 1, 1, tzinfo=UTC),
        )
        result = self._fetch_all_with_items([old_item], max_age_days=7)
        assert all(i.id != "old-1" for i in result)

    def test_age_filter_keeps_recent_items(self):
        """Items published within max_age_days are included."""
        recent = _make_item("recent-1")  # published 2026-05-02, within 365 days
        result = self._fetch_all_with_items([recent], max_age_days=365)
        assert any(i.id == "recent-1" for i in result)

    def test_age_filter_handles_naive_published_datetime(self):
        """Age filter must not raise TypeError when item.published is timezone-naive."""
        naive_item = FetchedItem(
            id="naive-1",
            title="Naive dt",
            url="https://example.com/naive",
            content="",
            source_name="S",
            source_type="rss",
            source_class="practitioner",
            author="",
            has_code=False,
            evidence_type="unknown",
            published=datetime(2026, 5, 2, 9, 0),  # no tzinfo — naive
        )
        # Must not raise TypeError: can't compare offset-naive and offset-aware datetimes
        result = self._fetch_all_with_items([naive_item], max_age_days=7)
        assert isinstance(result, list)


# ── write_raw_jsonl ─────────────────────────────────────────────────────────


class TestWriteRawJsonl:
    """write_raw_jsonl(items, path) writes one JSON line per FetchedItem."""

    def test_writes_one_line_per_item(self, tmp_path):
        from src.pipeline.fetch import write_raw_jsonl

        items = [_make_item("a"), _make_item("b")]
        out = tmp_path / "raw.jsonl"
        write_raw_jsonl(items, out)
        lines = out.read_text().splitlines()
        assert len(lines) == 2

    def test_each_line_is_valid_json(self, tmp_path):
        from src.pipeline.fetch import write_raw_jsonl

        items = [_make_item("x")]
        out = tmp_path / "raw.jsonl"
        write_raw_jsonl(items, out)
        for line in out.read_text().splitlines():
            d = json.loads(line)
            assert "id" in d
            assert "title" in d
            assert "url" in d

    def test_roundtrip_via_from_dict(self, tmp_path):
        from src.pipeline.fetch import write_raw_jsonl

        original = _make_item("rt-1")
        out = tmp_path / "raw.jsonl"
        write_raw_jsonl([original], out)
        line = out.read_text().splitlines()[0]
        restored = FetchedItem.from_dict(json.loads(line))
        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.source_class == original.source_class

    def test_creates_parent_directories(self, tmp_path):
        from src.pipeline.fetch import write_raw_jsonl

        out = tmp_path / "deep" / "nested" / "raw.jsonl"
        write_raw_jsonl([_make_item("d")], out)
        assert out.exists()

    def test_empty_list_writes_empty_file(self, tmp_path):
        from src.pipeline.fetch import write_raw_jsonl

        out = tmp_path / "empty.jsonl"
        write_raw_jsonl([], out)
        assert out.exists()
        assert out.read_text().strip() == ""


# ── read_raw_jsonl ──────────────────────────────────────────────────────────


class TestReadRawJsonl:
    """read_raw_jsonl(path) → list[FetchedItem] — inverse of write_raw_jsonl."""

    def test_reads_items_written_by_write(self, tmp_path):
        from src.pipeline.fetch import read_raw_jsonl, write_raw_jsonl

        items = [_make_item("r1"), _make_item("r2")]
        path = tmp_path / "raw.jsonl"
        write_raw_jsonl(items, path)
        result = read_raw_jsonl(path)
        assert len(result) == 2
        assert {i.id for i in result} == {"r1", "r2"}

    def test_returns_empty_list_for_missing_file(self, tmp_path):
        from src.pipeline.fetch import read_raw_jsonl

        result = read_raw_jsonl(tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_returns_empty_list_for_empty_file(self, tmp_path):
        from src.pipeline.fetch import read_raw_jsonl

        path = tmp_path / "empty.jsonl"
        path.write_text("")
        assert read_raw_jsonl(path) == []

    def test_skips_malformed_lines(self, tmp_path):
        from src.pipeline.fetch import read_raw_jsonl

        path = tmp_path / "mixed.jsonl"
        good = json.dumps(_make_item("g1").to_dict())
        path.write_text(f"{good}\nnot-json\n")
        result = read_raw_jsonl(path)
        assert len(result) == 1
        assert result[0].id == "g1"


class TestMergeAndWriteRaw:
    def test_preserves_existing_items_when_no_new_items(self, tmp_path):
        from src.pipeline.fetch import _merge_and_write_raw, read_raw_jsonl, write_raw_jsonl

        path = tmp_path / "raw.jsonl"
        existing = [_make_item("existing-1"), _make_item("existing-2")]
        write_raw_jsonl(existing, path)

        merged = _merge_and_write_raw(path, [])
        reloaded = read_raw_jsonl(path)

        assert [item.id for item in merged] == ["existing-1", "existing-2"]
        assert [item.id for item in reloaded] == ["existing-1", "existing-2"]

    def test_appends_new_unique_items_without_duplicates(self, tmp_path):
        from src.pipeline.fetch import _merge_and_write_raw, read_raw_jsonl, write_raw_jsonl

        path = tmp_path / "raw.jsonl"
        write_raw_jsonl([_make_item("existing-1")], path)

        merged = _merge_and_write_raw(path, [_make_item("existing-1"), _make_item("new-1")])
        reloaded = read_raw_jsonl(path)

        assert [item.id for item in merged] == ["existing-1", "new-1"]
        assert [item.id for item in reloaded] == ["existing-1", "new-1"]
