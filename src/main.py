"""Pipeline entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv()
except ImportError:
    pass  # dotenv not installed; env vars must be set externally (CI injects them)

from src.config import load_config
from src.emailer import send_digest
from src.fetchers import FetchedItem
from src.fetchers.youtube import YouTubeFetcher
from src.logger import setup_logging
from src.state import load_state, save_state
from src.summariser import summarise

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate and send the daily AI digest.")
    p.add_argument("--debug", action="store_true", help="Structured JSON logging to stdout")
    p.add_argument("--dry-run", action="store_true", help="Skip email; print digest to stdout")
    p.add_argument("--config", default="config/sources.yaml", help="Path to sources.yaml")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = load_config(Path(args.config))
    setup_logging(debug=args.debug, log_file=cfg.logging.log_file)

    logger.info("Starting digest pipeline (dry_run=%s)", args.dry_run)

    if cfg.summary.enabled and not os.environ.get("GEMINI_API_KEY"):
        logger.warning(
            "GEMINI_API_KEY is not set — falling back to plain link digest"
            " (set summary.enabled: false in sources.yaml to silence this warning)"
        )
        cfg.summary.enabled = False

    processed = load_state()
    new_items: list[FetchedItem] = []

    if cfg.youtube.enabled:
        new_items += YouTubeFetcher(cfg.youtube).fetch(processed)

    # Remaining fetchers added in Epics 4 and 5:
    #   new_items += RSSFetcher(cfg.blogs).fetch(processed)
    #   new_items += HackerNewsFetcher(cfg.hacker_news).fetch(processed)

    if not new_items:
        logger.info("No new items across all sources")
        if not cfg.email.send_if_empty:
            return 0

    logger.info("Fetched %d new item(s) total", len(new_items))
    for item in new_items:
        logger.info("  [%s] %s", item.source_name, item.title)

    today = datetime.now(UTC).date()
    digest = summarise(new_items, cfg.summary, today)

    subject = cfg.email.subject.format(date=today.strftime("%d %b %Y"))

    if args.dry_run:
        print(f"\nSubject: {subject}\n\n{digest}")
    else:
        send_digest(subject, digest)
        # Mark all fetched items as processed only after a successful send.
        for item in new_items:
            processed.add(item.id)
        save_state(processed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
