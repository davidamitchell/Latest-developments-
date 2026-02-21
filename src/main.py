"""Pipeline entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.config import load_config
from src.logger import setup_logging
from src.state import load_state, save_state

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

    processed = load_state()
    new_items: list = []

    # Fetchers are registered here as each Epic 1–5 slice is completed.
    # e.g.:
    #   from src.fetchers.youtube import YouTubeFetcher
    #   new_items += YouTubeFetcher(cfg.youtube).fetch(processed)

    if not new_items:
        logger.info("No new items across all sources")
        if not cfg.email.send_if_empty:
            return 0

    logger.info("Fetched %d new items", len(new_items))

    for item in new_items:
        logger.info("  [%s] %s — %s", item.source_name, item.title, item.url)

    if not args.dry_run:
        save_state(processed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
