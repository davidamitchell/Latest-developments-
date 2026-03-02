"""Tests for src/history.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.history import archive_digest, history_date_from_path, load_recent_digests


class TestArchiveDigest:
    def test_creates_file_with_date_name(self, tmp_path: Path) -> None:
        archive_digest(date(2026, 3, 1), "digest text", history_dir=tmp_path)
        expected = tmp_path / "2026-03-01.txt"
        assert expected.exists()

    def test_file_content_matches_text(self, tmp_path: Path) -> None:
        text = "Daily AI Digest — 01 Mar 2026\n====\n\nSome content."
        archive_digest(date(2026, 3, 1), text, history_dir=tmp_path)
        assert (tmp_path / "2026-03-01.txt").read_text() == text

    def test_creates_directory_when_missing(self, tmp_path: Path) -> None:
        history_dir = tmp_path / "subdir" / "history"
        assert not history_dir.exists()
        archive_digest(date(2026, 3, 1), "text", history_dir=history_dir)
        assert history_dir.exists()
        assert (history_dir / "2026-03-01.txt").exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        archive_digest(date(2026, 3, 1), "first version", history_dir=tmp_path)
        archive_digest(date(2026, 3, 1), "second version", history_dir=tmp_path)
        content = (tmp_path / "2026-03-01.txt").read_text()
        assert content == "second version"

    def test_multiple_dates_create_separate_files(self, tmp_path: Path) -> None:
        archive_digest(date(2026, 3, 1), "day one", history_dir=tmp_path)
        archive_digest(date(2026, 3, 2), "day two", history_dir=tmp_path)
        assert (tmp_path / "2026-03-01.txt").exists()
        assert (tmp_path / "2026-03-02.txt").exists()


class TestLoadRecentDigests:
    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        result = load_recent_digests(7, history_dir=missing)
        assert result == []

    def test_returns_empty_when_dir_has_no_txt_files(self, tmp_path: Path) -> None:
        (tmp_path / "notes.md").write_text("not a digest")
        result = load_recent_digests(7, history_dir=tmp_path)
        assert result == []

    def test_returns_most_recent_first(self, tmp_path: Path) -> None:
        (tmp_path / "2026-03-01.txt").write_text("day one")
        (tmp_path / "2026-03-02.txt").write_text("day two")
        (tmp_path / "2026-03-03.txt").write_text("day three")
        result = load_recent_digests(3, history_dir=tmp_path)
        assert result[0] == "day three"
        assert result[1] == "day two"
        assert result[2] == "day one"

    def test_respects_n_limit(self, tmp_path: Path) -> None:
        for i in range(1, 8):
            (tmp_path / f"2026-03-0{i}.txt").write_text(f"day {i}")
        result = load_recent_digests(3, history_dir=tmp_path)
        assert len(result) == 3

    def test_returns_all_when_fewer_than_n(self, tmp_path: Path) -> None:
        (tmp_path / "2026-03-01.txt").write_text("only one")
        result = load_recent_digests(7, history_dir=tmp_path)
        assert len(result) == 1
        assert result[0] == "only one"

    def test_ignores_non_txt_files(self, tmp_path: Path) -> None:
        (tmp_path / "2026-03-01.txt").write_text("valid")
        (tmp_path / "2026-03-01.md").write_text("not a digest")
        result = load_recent_digests(7, history_dir=tmp_path)
        assert len(result) == 1
        assert result[0] == "valid"

    def test_returns_correct_content(self, tmp_path: Path) -> None:
        text = "Daily AI Digest — 01 Mar 2026\n====\n\nContent here."
        (tmp_path / "2026-03-01.txt").write_text(text)
        result = load_recent_digests(1, history_dir=tmp_path)
        assert result[0] == text

    def test_zero_n_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "2026-03-01.txt").write_text("content")
        result = load_recent_digests(0, history_dir=tmp_path)
        assert result == []


class TestHistoryDateFromPath:
    def test_valid_date_filename(self) -> None:
        p = Path("history/2026-03-01.txt")
        result = history_date_from_path(p)
        assert result == date(2026, 3, 1)

    def test_invalid_filename_returns_none(self) -> None:
        p = Path("history/notes.txt")
        result = history_date_from_path(p)
        assert result is None

    def test_non_date_stem_returns_none(self) -> None:
        p = Path("history/readme.md")
        result = history_date_from_path(p)
        assert result is None
