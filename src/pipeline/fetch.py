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
from datetime import UTC, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]
    load_dotenv()
except ImportError:
    pass

from src.config import Config, load_config
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


def _build_fetchers(cfg: Config) -> list[tuple[str, object]]:
    """Return (name, fetcher_instance) pairs for every enabled source."""
    pairs: list[tuple[str, object]] = []

    if cfg.youtube.enabled:
        pairs.append(("YouTube", YouTubeFetcher(cfg.youtube)))

    if cfg.blogs.enabled:
        pairs.append(("RSS/Blogs", RSSFetcher(cfg.blogs)))

    if cfg.substack.enabled:
        pairs.append(("Substack", SubstackFetcher(cfg.substack)))

    if cfg.hacker_news.enabled:
        pairs.append(("Hacker News", HackerNewsFetcher(cfg.hacker_news)))

    if cfg.trends.arxiv.enabled:
        pairs.append(("arXiv", ArxivFetcher(cfg.trends.arxiv)))

    if cfg.trends.huggingface.enabled:
        pairs.append(("HuggingFace", HuggingFaceFetcher(cfg.trends.huggingface)))

    if cfg.trends.paperswithcode.enabled:
        pairs.append(("PapersWithCode", PapersWithCodeFetcher(cfg.trends.paperswithcode)))

    if cfg.trends.operator_sources.enabled:
        pairs.append(("OperatorChangelog", OperatorChangelogFetcher(cfg.trends.operator_sources)))

    if cfg.trends.replicate.enabled:
        pairs.append(("Replicate", ReplicateFetcher(cfg.trends.replicate)))

    if cfg.trends.openreview.enabled:
        pairs.append(("OpenReview", OpenReviewFetcher(cfg.trends.openreview)))

    if cfg.trends.openrouter.enabled:
        pairs.append(("OpenRouter", OpenRouterFetcher(cfg.trends.openrouter)))

    return pairs


def fetch_all(cfg: Config, already_processed: set[str]) -> list[FetchedItem]:
    """Fetch from all enabled sources; deduplicate against already_processed.

    Each fetcher receives already_processed for its own internal dedup.
    fetch_all additionally deduplicates across fetchers and against the state.
    """
    fetchers = _build_fetchers(cfg)
    seen = set(already_processed)
    result: list[FetchedItem] = []

    for name, fetcher in fetchers:
        items = _safe_fetch(name, fetcher, already_processed)
        for item in items:
            if item.id not in seen:
                seen.add(item.id)
                result.append(item)

    logger.info("Total new items after deduplication: %d", len(result))
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
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = load_config(Path(args.config))
    setup_logging(debug=args.debug, log_file=cfg.logging.log_file)

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
