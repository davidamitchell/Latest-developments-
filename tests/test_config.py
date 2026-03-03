"""Tests for src/config.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import load_config


def test_load_minimal_config(config_path: Path) -> None:
    cfg = load_config(config_path)
    assert cfg.youtube.enabled is False
    assert cfg.blogs.enabled is False
    assert cfg.hacker_news.enabled is False


def test_load_youtube_channels(tmp_path: Path) -> None:
    p = tmp_path / "sources.yaml"
    p.write_text(
        """
youtube:
  max_videos_per_channel: 3
  channels:
    - name: Test Channel
      channel_id: UCabc123
"""
    )
    cfg = load_config(p)
    assert len(cfg.youtube.channels) == 1
    assert cfg.youtube.channels[0].channel_id == "UCabc123"
    assert cfg.youtube.channels[0].max_videos == 3


def test_channel_max_videos_override(tmp_path: Path) -> None:
    p = tmp_path / "sources.yaml"
    p.write_text(
        """
youtube:
  max_videos_per_channel: 5
  channels:
    - name: Test
      channel_id: UCabc
      max_videos: 2
"""
    )
    cfg = load_config(p)
    assert cfg.youtube.channels[0].max_videos == 2


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")


def test_default_model(config_path: Path) -> None:
    cfg = load_config(config_path)
    assert "gemini" in cfg.summary.model


# Regression tests: YAML list key present but all items commented out → null → None
# These would have raised TypeError before the _yaml_list() fix was applied.


def test_null_rss_list_does_not_raise(tmp_path: Path) -> None:
    """blogs.rss: null (all items commented out) must not raise TypeError."""
    p = tmp_path / "sources.yaml"
    p.write_text("blogs:\n  enabled: true\n  rss:\n")
    cfg = load_config(p)
    assert cfg.blogs.rss == []


def test_null_youtube_channels_does_not_raise(tmp_path: Path) -> None:
    """youtube.channels: null must not raise TypeError."""
    p = tmp_path / "sources.yaml"
    p.write_text("youtube:\n  enabled: true\n  channels:\n")
    cfg = load_config(p)
    assert cfg.youtube.channels == []


def test_null_substack_publications_does_not_raise(tmp_path: Path) -> None:
    """substack.publications: null must not raise TypeError."""
    p = tmp_path / "sources.yaml"
    p.write_text("substack:\n  enabled: true\n  publications:\n")
    cfg = load_config(p)
    assert cfg.substack.publications == []


def test_null_hacker_news_keywords_does_not_raise(tmp_path: Path) -> None:
    """hacker_news.keywords: null must not raise TypeError."""
    p = tmp_path / "sources.yaml"
    p.write_text("hacker_news:\n  enabled: true\n  keywords:\n")
    cfg = load_config(p)
    assert cfg.hacker_news.keywords == []


def test_history_config_defaults(config_path: Path) -> None:
    cfg = load_config(config_path)
    assert cfg.history.enabled is True
    assert cfg.history.history_days == 7
    assert cfg.history.history_dir == "history"


def test_history_config_custom_values(tmp_path: Path) -> None:
    p = tmp_path / "sources.yaml"
    p.write_text(
        """
history:
  enabled: false
  history_days: 14
  history_dir: "digests"
"""
    )
    cfg = load_config(p)
    assert cfg.history.enabled is False
    assert cfg.history.history_days == 14
    assert cfg.history.history_dir == "digests"
