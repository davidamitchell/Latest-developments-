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
    assert "haiku" in cfg.summary.model
