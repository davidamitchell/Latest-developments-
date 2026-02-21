"""Logging setup for debug and normal modes."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(debug: bool = False, log_file: str | None = None) -> None:
    """Configure root logger. Call once at startup."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    stdout = logging.StreamHandler(sys.stdout)
    if debug:
        stdout.setFormatter(_JSONFormatter())
    else:
        stdout.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
        )
    root.addHandler(stdout)

    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"))
        root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
