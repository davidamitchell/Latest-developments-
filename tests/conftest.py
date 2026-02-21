"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    cfg = tmp_path / "sources.yaml"
    cfg.write_text(
        """
youtube:
  enabled: false
  channels: []
blogs:
  enabled: false
  rss: []
hacker_news:
  enabled: false
  keywords: []
"""
    )
    return cfg


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "processed.json"
