"""Load and validate sources.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


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
class RSSFeed:
    name: str
    url: str
    fallback_url: str | None = None


@dataclass
class BlogsConfig:
    enabled: bool = True
    rss: list[RSSFeed] = field(default_factory=list)


@dataclass
class SubstackPublication:
    name: str
    slug: str  # e.g. "natesnewsletter" for natesnewsletter.substack.com


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


@dataclass
class SummaryConfig:
    enabled: bool = True  # False → skip AI; produce a plain link-list digest instead
    model: str = "gemini-2.5-flash"
    max_tokens: int = 2000
    max_items_per_source: int = 5
    prompt: str = ""


@dataclass
class EmailConfig:
    subject: str = "Daily AI Digest — {date}"
    send_if_empty: bool = False


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_file: str | None = None


@dataclass
class Config:
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    blogs: BlogsConfig = field(default_factory=BlogsConfig)
    substack: SubstackConfig = field(default_factory=SubstackConfig)
    hacker_news: HackerNewsConfig = field(default_factory=HackerNewsConfig)
    summary: SummaryConfig = field(default_factory=SummaryConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Required environment variable {key!r} is not set")
    return value


def load_config(path: Path = Path("config/sources.yaml")) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open() as f:
        raw: dict = yaml.safe_load(f) or {}

    yt = raw.get("youtube", {})
    default_max = yt.get("max_videos_per_channel", 5)
    youtube = YouTubeConfig(
        enabled=yt.get("enabled", True),
        max_videos_per_channel=default_max,
        channels=[
            YouTubeChannel(
                name=ch["name"],
                channel_id=ch["channel_id"],
                max_videos=ch.get("max_videos", default_max),
            )
            for ch in (yt.get("channels") or [])
        ],
    )

    bl = raw.get("blogs", {})
    blogs = BlogsConfig(
        enabled=bl.get("enabled", True),
        rss=[
            RSSFeed(name=f["name"], url=f["url"], fallback_url=f.get("fallback_url"))
            for f in (bl.get("rss") or [])
        ],
    )

    ss = raw.get("substack", {})
    substack = SubstackConfig(
        enabled=ss.get("enabled", True),
        publications=[
            SubstackPublication(name=p["name"], slug=p["slug"]) for p in (ss.get("publications") or [])
        ],
    )

    hn = raw.get("hacker_news", {})
    hacker_news = HackerNewsConfig(
        enabled=hn.get("enabled", True),
        min_score=hn.get("min_score", 100),
        keywords=hn.get("keywords") or [],
        max_stories=hn.get("max_stories", 10),
    )

    sm = raw.get("summary", {})
    summary = SummaryConfig(
        model=sm.get("model", "gemini-2.0-flash"),
        max_tokens=sm.get("max_tokens", 2000),
        max_items_per_source=sm.get("max_items_per_source", 5),
        prompt=sm.get("prompt", ""),
    )

    em = raw.get("email", {})
    email = EmailConfig(
        subject=em.get("subject", "Daily AI Digest — {date}"),
        send_if_empty=em.get("send_if_empty", False),
    )

    lg = raw.get("logging", {})
    logging_cfg = LoggingConfig(
        level=lg.get("level", "INFO"),
        log_file=lg.get("log_file"),
    )

    return Config(
        youtube=youtube,
        blogs=blogs,
        substack=substack,
        hacker_news=hacker_news,
        summary=summary,
        email=email,
        logging=logging_cfg,
    )
