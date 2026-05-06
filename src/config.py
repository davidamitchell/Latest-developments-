"""Load and validate config/sources.yaml (ADR-0018).

Public API:
  SourceEntry   — one entry in the flat sources list; type discriminator + options dict
  DigestConfig  — email digest settings; references only ProcessedItem fields
  HistoryConfig — shared digest-archive settings
  LoggingConfig — shared logging settings
  Config        — top-level container: sources + digest + history + logging
  load_config() — parse sources.yaml → Config

Internal helpers kept for fetcher adapters (not part of the Config public API):
  BlogsConfig, RSSFeed, YouTubeConfig, YouTubeChannel,
  SubstackConfig, SubstackPublication, HackerNewsConfig
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Public Config dataclasses ─────────────────────────────────────────────────

@dataclass
class SourceEntry:
    """One entry in the flat sources list."""
    type: str                        # rss | youtube | substack | hackernews | arxiv | ...
    name: str
    source_class: str                # primary | operator | practitioner | media | market
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class DigestConfig:
    """Email digest settings.

    Completely independent of the sources list. All filter predicates
    reference ProcessedItem field names only — not source names or types.
    """
    subject: str = "Daily AI Digest — {date}"
    send_if_empty: bool = False
    # ProcessedItem-field predicates
    min_credibility: float = 0.0
    max_hype_risk: float = 1.0
    exclude_marketing: bool = False
    # Gemini generation settings
    model: str = "gemini-2.5-flash"
    max_tokens: int = 2000
    max_items_per_source: int = 5
    prompt: str = ""


@dataclass
class HistoryConfig:
    enabled: bool = True
    history_days: int = 7
    history_dir: str = "history"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_file: str | None = None


@dataclass
class PipelineConfig:
    """Processing pipeline settings.

    gemini_rpm controls the rate limiter in src/pipeline/run.py.
    enrich_max_output_tokens controls the Gemini token budget per enrichment call.
    Both can be adjusted in config/sources.yaml under the 'pipeline' section
    without touching production code.
    """
    gemini_rpm: int = 5
    enrich_max_output_tokens: int = 500


@dataclass
class Config:
    sources: list[SourceEntry] = field(default_factory=list)
    digest: DigestConfig = field(default_factory=DigestConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)


# ── Internal fetcher-adapter helpers ─────────────────────────────────────────
# Used exclusively by src/pipeline/fetch.py to construct fetcher instances
# from SourceEntry objects. NOT part of the Config public API.

@dataclass
class RSSFeed:
    name: str
    url: str
    fallback_url: str | None = None
    source_class: str = "practitioner"


@dataclass
class BlogsConfig:
    enabled: bool = True
    rss: list[RSSFeed] = field(default_factory=list)


@dataclass
class YouTubeChannel:
    name: str
    channel_id: str
    max_videos: int = 5


@dataclass
class YouTubeConfig:
    enabled: bool = True
    max_videos_per_channel: int = 5
    channels: list[YouTubeChannel] = field(default_factory=list)


@dataclass
class SubstackPublication:
    name: str
    slug: str


@dataclass
class SubstackConfig:
    enabled: bool = True
    publications: list[SubstackPublication] = field(default_factory=list)


@dataclass
class HackerNewsConfig:
    enabled: bool = True
    min_score: int = 100
    keywords: list[str] = field(default_factory=list)
    max_stories: int = 10


# ── Loader ────────────────────────────────────────────────────────────────────

_COMMON_KEYS = {"type", "name", "source_class", "enabled"}


def _entry_options(raw: dict) -> dict[str, Any]:
    """Extract type-specific options by stripping the common SourceEntry keys."""
    return {k: v for k, v in raw.items() if k not in _COMMON_KEYS}


def _yaml_list(value: list | None) -> list:
    return value if isinstance(value, list) else []


def load_config(path: Path = Path("config/sources.yaml")) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open() as f:
        raw: dict = yaml.safe_load(f) or {}

    # sources — flat list
    sources: list[SourceEntry] = []
    for entry_raw in _yaml_list(raw.get("sources")):
        sources.append(
            SourceEntry(
                type=entry_raw["type"],
                name=entry_raw["name"],
                source_class=entry_raw.get("source_class", "practitioner"),
                enabled=entry_raw.get("enabled", True),
                options=_entry_options(entry_raw),
            )
        )

    # digest — independent section
    d = raw.get("digest", {}) or {}
    digest = DigestConfig(
        subject=d.get("subject", "Daily AI Digest — {date}"),
        send_if_empty=d.get("send_if_empty", False),
        min_credibility=d.get("min_credibility", 0.0),
        max_hype_risk=d.get("max_hype_risk", 1.0),
        exclude_marketing=d.get("exclude_marketing", False),
        model=d.get("model", "gemini-2.5-flash"),
        max_tokens=d.get("max_tokens", 2000),
        max_items_per_source=d.get("max_items_per_source", 5),
        prompt=d.get("prompt", ""),
    )

    # history + logging — shared global sections
    hi = raw.get("history", {}) or {}
    history = HistoryConfig(
        enabled=hi.get("enabled", True),
        history_days=hi.get("history_days", 7),
        history_dir=hi.get("history_dir", "history"),
    )

    lg = raw.get("logging", {}) or {}
    logging_cfg = LoggingConfig(
        level=lg.get("level", "INFO"),
        log_file=lg.get("log_file"),
    )

    pl = raw.get("pipeline") or {}
    pipeline = PipelineConfig(
        gemini_rpm=pl.get("gemini_rpm", 5),
        enrich_max_output_tokens=pl.get("enrich_max_output_tokens", 500),
    )

    return Config(sources=sources, digest=digest, history=history, logging=logging_cfg, pipeline=pipeline)


def require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Required environment variable {key!r} is not set")
    return value
