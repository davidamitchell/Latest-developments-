"""Fetch entrypoint — Concern 1: FETCHING.

CLI: python -m src.pipeline.fetch

Loads all enabled sources from config, instantiates fetchers, collects
FetchedItem[] deduplicated against state/processed.json, and writes
data/raw/YYYY-MM-DD.jsonl (one JSON line per FetchedItem).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]
    load_dotenv()
except ImportError:
    pass

from src.config import (
    BlogsConfig,
    Config,
    HackerNewsConfig,
    RSSFeed,
    SourceEntry,
    SubstackConfig,
    SubstackPublication,
    YouTubeChannel,
    YouTubeConfig,
    load_config,
)
from src.fetchers import FetchedItem
from src.fetchers.arxiv import ArxivFetcher
from src.fetchers.hackernews import HackerNewsFetcher
from src.fetchers.huggingface import HuggingFaceFetcher
from src.fetchers.openreview import OpenReviewFetcher
from src.fetchers.openrouter import OpenRouterFetcher
from src.fetchers.operator_changelog import OperatorChangelogFetcher
from src.fetchers.paperswithcode import PapersWithCodeFetcher
from src.fetchers.replicate import ReplicateFetcher
from src.fetchers.rss import RSSFetcher
from src.fetchers.substack import SubstackFetcher
from src.fetchers.youtube import YouTubeFetcher
from src.logger import setup_logging
from src.state import load_state

logger = logging.getLogger(__name__)

_RAW_DIR = Path("data/raw")


def _safe_fetch(name: str, fetcher, already_processed: set[str]) -> list[FetchedItem]:
    """Call fetcher.fetch(), returning [] and logging on any exception."""
    try:
        items = fetcher.fetch(already_processed)
        logger.info("%s: %d item(s) fetched", name, len(items))
        return items
    except Exception as exc:
        logger.error("Fetcher %r failed: %s", name, exc)
        return []


# ── Singleton fetcher registry (OCP) ─────────────────────────────────────────
# Adding a new singleton source type means adding one entry here — no existing
# code changes required.  Each factory receives the SourceEntry and returns a
# (name, fetcher_instance) pair.

_SINGLETON_FACTORIES: dict[str, Callable[[SourceEntry], tuple[str, object]]] = {
    "hackernews": lambda e: (
        e.name,
        HackerNewsFetcher(HackerNewsConfig(
            min_score=e.options.get("min_score", 100),
            keywords=e.options.get("keywords", []),
            max_stories=e.options.get("max_stories", 10),
        )),
    ),
    "arxiv": lambda e: (
        e.name,
        ArxivFetcher(
            categories=e.options.get("categories", ["cs.AI", "cs.LG", "cs.CL"]),
            max_papers=e.options.get("max_papers", 30),
        ),
    ),
    "huggingface": lambda e: (
        e.name,
        HuggingFaceFetcher(
            max_models=e.options.get("max_models", 50),
            min_downloads=e.options.get("min_downloads", 100),
        ),
    ),
    "paperswithcode": lambda e: (
        e.name,
        PapersWithCodeFetcher(
            page_size=e.options.get("page_size", 20),
            min_stars=e.options.get("min_stars", 0),
        ),
    ),
    "operator_changelog": lambda e: (
        e.name,
        OperatorChangelogFetcher(
            feeds=e.options.get("feeds", []),
            source_class=e.source_class,
        ),
    ),
    "replicate": lambda e: (
        e.name,
        ReplicateFetcher(limit=e.options.get("limit", 20)),
    ),
    "openreview": lambda e: (
        e.name,
        OpenReviewFetcher(
            venues=e.options.get("venues", []),
            limit=e.options.get("limit", 25),
        ),
    ),
    "openrouter": lambda e: (
        e.name,
        OpenRouterFetcher(limit=e.options.get("limit", 100)),
    ),
}

# Types handled by multi-source aggregation above — not passed to the registry.
_AGGREGATE_TYPES: frozenset[str] = frozenset({"rss", "youtube", "substack"})


def _build_fetchers(cfg: Config) -> list[tuple[str, object]]:
    """Return (name, fetcher_instance) pairs for every enabled source.

    Translates the flat cfg.sources list into fetcher instances.
    Multi-entry types (rss, youtube, substack) are aggregated into a single
    fetcher. Singleton types delegate to _SINGLETON_FACTORIES so that adding
    a new type requires no changes to this function.
    """
    pairs: list[tuple[str, object]] = []
    enabled = [e for e in cfg.sources if e.enabled]

    # ── Aggregate multi-source types ──────────────────────────────────────────

    rss_entries = [e for e in enabled if e.type == "rss"]
    if rss_entries:
        blogs_cfg = BlogsConfig(
            rss=[
                RSSFeed(
                    name=e.name,
                    url=e.options["url"],
                    source_class=e.source_class,
                )
                for e in rss_entries
            ]
        )
        pairs.append(("RSS/Blogs", RSSFetcher(blogs_cfg)))

    yt_entries = [e for e in enabled if e.type == "youtube"]
    if yt_entries:
        # max_videos_per_channel on YouTubeConfig is the global fallback when a
        # channel entry does not specify max_videos explicitly.
        yt_default = YouTubeConfig()
        yt_cfg = YouTubeConfig(
            channels=[
                YouTubeChannel(
                    name=e.name,
                    channel_id=e.options["channel_id"],
                    max_videos=e.options.get("max_videos", yt_default.max_videos_per_channel),
                )
                for e in yt_entries
            ]
        )
        pairs.append(("YouTube", YouTubeFetcher(yt_cfg)))

    ss_entries = [e for e in enabled if e.type == "substack"]
    if ss_entries:
        ss_cfg = SubstackConfig(
            publications=[
                SubstackPublication(name=e.name, slug=e.options["slug"])
                for e in ss_entries
            ]
        )
        pairs.append(("Substack", SubstackFetcher(ss_cfg)))

    # ── Singleton types — dispatch via registry (OCP) ─────────────────────────

    for entry in enabled:
        if entry.type in _AGGREGATE_TYPES:
            continue
        factory = _SINGLETON_FACTORIES.get(entry.type)
        if factory is not None:
            pairs.append(factory(entry))
        else:
            logger.warning("Unknown source type %r in entry %r — skipping", entry.type, entry.name)

    return pairs


_DEFAULT_MAX_AGE_DAYS = 7


def _age_cutoff(max_age_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=max_age_days)


def fetch_all(
    cfg: Config,
    already_processed: set[str],
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
) -> list[FetchedItem]:
    """Fetch from all enabled sources; deduplicate and apply age filter.

    Items published more than max_age_days ago are dropped.  This prevents
    a backlog of historical content from flooding the digest on the first run
    after a new source is added or the pipeline is restarted.
    """
    fetchers = _build_fetchers(cfg)
    seen = set(already_processed)
    result: list[FetchedItem] = []
    cutoff = _age_cutoff(max_age_days)
    too_old = 0

    for name, fetcher in fetchers:
        items = _safe_fetch(name, fetcher, already_processed)
        for item in items:
            if item.id in seen:
                continue
            if item.published:
                pub = item.published if item.published.tzinfo is not None else item.published.replace(tzinfo=UTC)
                if pub < cutoff:
                    too_old += 1
                    continue
            seen.add(item.id)
            result.append(item)

    if too_old:
        logger.info("Dropped %d item(s) older than %d days", too_old, max_age_days)
    logger.info("Total new items after deduplication and age filter: %d", len(result))
    return result


def write_raw_jsonl(items: list[FetchedItem], path: Path) -> None:
    """Write items to path as JSONL (one JSON line per FetchedItem)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    logger.info("Wrote %d raw item(s) to %s", len(items), path)


def read_raw_jsonl(path: Path) -> list[FetchedItem]:
    """Read JSONL file produced by write_raw_jsonl; return [] if file missing."""
    if not path.exists():
        logger.debug("Raw file not found: %s", path)
        return []
    items: list[FetchedItem] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(FetchedItem.from_dict(json.loads(line)))
            except Exception as exc:
                logger.warning("Skipping malformed line %d in %s: %s", lineno, path, exc)
    return items


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch all sources → data/raw/YYYY-MM-DD.jsonl")
    p.add_argument("--config", default="config/sources.yaml", help="Path to sources.yaml")
    p.add_argument("--date", default=None, help="Override fetch date (YYYY-MM-DD)")
    p.add_argument("--max-videos", type=int, default=None,
                   help="Override max_videos for all YouTube sources (useful for catch-up runs)")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = load_config(Path(args.config))
    setup_logging(debug=args.debug, log_file=cfg.logging.log_file)

    if args.max_videos is not None:
        for entry in cfg.sources:
            if entry.type == "youtube":
                entry.options = {**entry.options, "max_videos": args.max_videos}
        logger.info("--max-videos override: YouTube sources capped at %d", args.max_videos)

    today = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    out_path = _RAW_DIR / f"{today}.jsonl"

    logger.info("Fetch run for %s — output: %s", today, out_path)

    already_processed = load_state()
    items = fetch_all(cfg, already_processed)

    write_raw_jsonl(items, out_path)
    logger.info("Fetch complete — %d new item(s) written to %s", len(items), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
