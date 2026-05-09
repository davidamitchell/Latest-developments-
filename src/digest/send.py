"""Email digest entrypoint — Concern 3A: EMAIL DIGEST.

CLI: python -m src.digest.send

Reads data/processed/YYYY-MM-DD.jsonl (ProcessedItem records), filters items
already sent via state/processed.json, formats and sends the HTML digest via
src.emailer, archives the plain-text digest to history/, and updates state.

This module must not import any fetcher or pipeline stage. It depends only on
Schema Contract B (ProcessedItem) and the existing summariser/emailer/state modules.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv()
except ImportError:
    pass

from src.config import Config, load_config
from src.emailer import send_digest
from src.fetchers import FetchedItem
from src.history import archive_digest, load_recent_digests
from src.logger import setup_logging
from src.models import ProcessedItem, read_processed_jsonl
from src.state import load_state, save_state
from src.summariser import render_html_digest, summarise

logger = logging.getLogger(__name__)

_PROCESSED_DIR = Path("data/processed")
_HISTORY_DIR = Path("history")
_STATE_FILE = Path("state/processed.json")


def select_items(items: list[ProcessedItem], already_sent: set[str]) -> list[ProcessedItem]:
    """Return items whose id is not in already_sent."""
    return [item for item in items if item.id not in already_sent]


def items_to_fetched(items: list[ProcessedItem]) -> list[FetchedItem]:
    """Convert ProcessedItem list to FetchedItem list for the summariser.

    Uses cleaned_content as the content field. All other fields are carried
    over directly. The summariser is source-type-agnostic and only needs the
    fields present on FetchedItem.
    """
    result: list[FetchedItem] = []
    for item in items:
        result.append(
            FetchedItem(
                id=item.id,
                title=item.title,
                url=item.url,
                content=item.cleaned_content or item.summary or item.title,
                source_name=item.source_name,
                source_type=item.source_type,
                source_class=item.source_class,
                author=item.author,
                published=item.published,
                has_code=item.has_code,
                evidence_type=item.evidence_type,
            )
        )
    return result


def build_digest(
    items: list[ProcessedItem],
    cfg: Config,
    today: date,
    history: list[str],
) -> tuple[str, str]:
    """Return (plain_text_digest, html_digest) for the given items.

    Returns ("", "") when items is empty.
    """
    if not items:
        return "", ""

    fetched = items_to_fetched(items)
    plain = summarise(fetched, cfg.digest, today, history=history or None)
    html = render_html_digest(fetched, plain, today)
    return plain, html


def run(
    items: list[ProcessedItem],
    cfg: Config,
    today: date,
    dry_run: bool,
    history_dir: Path,
    state_path: Path,
    already_sent: set[str],
) -> int:
    """Core digest flow: select → build → send → archive → update state.

    Returns 0 on success.
    """
    new_items = select_items(items, already_sent)
    logger.info("%d new item(s) selected for digest (total: %d)", len(new_items), len(items))

    if not new_items and not cfg.digest.send_if_empty:
        logger.info("No new items and send_if_empty is false — skipping digest")
        return 0

    history: list[str] = []
    if cfg.history.enabled:
        history = load_recent_digests(cfg.history.history_days, history_dir)
        if history:
            logger.info("Loaded %d historical digest(s) for trend context", len(history))

    plain, html = build_digest(new_items, cfg, today, history)

    if not plain and not cfg.digest.send_if_empty:
        logger.info("Empty digest and send_if_empty is false — skipping send")
        return 0

    subject = cfg.digest.subject.format(date=today.strftime("%d %b %Y"))

    if dry_run:
        logger.info("[dry-run] Subject: %s", subject)
        logger.info("[dry-run] Digest:\n%s", plain)
        return 0

    send_digest(subject, plain, html_body=html)
    logger.info("Digest sent — subject: %s", subject)

    # Update state — mark all sent items as processed
    new_ids = {item.id for item in new_items}
    updated = already_sent | new_ids
    save_state(updated, state_path)
    logger.info("State updated — %d total processed IDs", len(updated))

    # Archive plain-text digest for future history context
    archive_digest(today, plain, history_dir)

    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Send email digest from data/processed/")
    p.add_argument("--date", default=None, help="Override fetch date (YYYY-MM-DD)")
    p.add_argument("--dry-run", action="store_true", help="Skip email; log digest to stdout")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--config", default="config/sources.yaml")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = load_config(Path(args.config))
    setup_logging(debug=args.debug, log_file=cfg.logging.log_file)

    today_str = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    processed_path = _PROCESSED_DIR / f"{today_str}.jsonl"

    logger.info(
        "Digest run for %s — input: %s (dry_run=%s)", today_str, processed_path, args.dry_run
    )

    items = read_processed_jsonl(processed_path)
    if not items:
        logger.info("No processed items for %s", today_str)
        if not cfg.digest.send_if_empty:
            return 0

    already_sent = load_state(_STATE_FILE)

    return run(
        items=items,
        cfg=cfg,
        today=today,
        dry_run=args.dry_run,
        history_dir=Path(cfg.history.history_dir),
        state_path=_STATE_FILE,
        already_sent=already_sent,
    )


if __name__ == "__main__":
    sys.exit(main())
