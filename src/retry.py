"""Exponential backoff for transient network errors."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    label: str = "",
    no_retry: tuple[type[Exception], ...] = (),
) -> T:
    """
    Call fn(), retrying on transient errors with exponential backoff.

    Exceptions listed in no_retry propagate immediately without retry.
    After max_attempts, raises RuntimeError wrapping the last exception.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except no_retry:
            raise
        except Exception as e:
            last_exc = e
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            prefix = f"{label}: " if label else ""
            logger.warning(
                "%sfailed (attempt %d/%d): %s — retry in %.0fs",
                prefix,
                attempt,
                max_attempts,
                e,
                delay,
            )
            time.sleep(delay)

    raise RuntimeError(f"{label or 'Operation'} failed after {max_attempts} attempts") from last_exc
