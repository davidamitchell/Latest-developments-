"""Read and write the deduplication state file."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = Path("state/processed.json")


def load_state(path: Path = STATE_FILE) -> set[str]:
    if not path.exists():
        logger.debug("No state file at %s — starting fresh", path)
        return set()
    with path.open() as f:
        data: dict = json.load(f)
    ids = set(data.get("processed", []))
    logger.debug("Loaded %d processed IDs", len(ids))
    return ids


def save_state(processed: set[str], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": datetime.now(UTC).isoformat(),
        "count": len(processed),
        "processed": sorted(processed),
    }
    with path.open("w") as f:
        json.dump(payload, f, indent=2)
    logger.debug("Saved %d processed IDs", len(processed))
