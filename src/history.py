"""Digest history archiving and retrieval.

Each successful digest run is archived as a plain-text file in ``history/``.
The summariser can load recent digests to provide trend context to Gemini.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_HISTORY_DIR = Path("history")


def archive_digest(today: date, text: str, history_dir: Path = _DEFAULT_HISTORY_DIR) -> None:
    """Write *text* to ``history/YYYY-MM-DD.txt``.

    Creates the directory if it does not already exist.  Any existing file for
    the same date is overwritten (idempotent re-runs are safe).
    """
    history_dir.mkdir(parents=True, exist_ok=True)
    dest = history_dir / f"{today.isoformat()}.txt"
    dest.write_text(text, encoding="utf-8")
    logger.info("Archived digest to %s", dest)


def load_recent_digests(n: int, history_dir: Path = _DEFAULT_HISTORY_DIR) -> list[str]:
    """Return the text of the *n* most recent archived digests, newest first.

    Returns an empty list when the history directory does not exist or contains
    no archive files.  Files that cannot be read are silently skipped.
    """
    if not history_dir.exists():
        return []

    files = sorted(
        history_dir.glob("*.txt"),
        # ISO-8601 date strings (YYYY-MM-DD) sort lexicographically in the same
        # order as chronologically, so sorting by stem gives newest-last order.
        key=lambda p: p.stem,
        reverse=True,
    )
    digests: list[str] = []
    for path in files[:n]:
        try:
            digests.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning("Could not read history file %s: %s", path, exc)
    return digests


def history_date_from_path(path: Path) -> date | None:
    """Parse the ISO-8601 date from a history file name, or return None."""
    try:
        return datetime.strptime(path.stem, "%Y-%m-%d").date()
    except ValueError:
        return None
