"""Tests for src/state.py."""

from __future__ import annotations

from pathlib import Path

from src.state import load_state, save_state


def test_load_state_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "state" / "processed.json"
    assert load_state(path) == set()


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state" / "processed.json"
    ids = {"https://example.com/a", "https://example.com/b", "video-id-123"}
    save_state(ids, path)
    assert load_state(path) == ids


def test_save_creates_parent_dir(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "nested" / "processed.json"
    save_state({"x"}, path)
    assert path.exists()


def test_load_empty_processed_list(tmp_path: Path) -> None:
    import json

    path = tmp_path / "processed.json"
    path.write_text(json.dumps({"processed": []}))
    assert load_state(path) == set()
