"""Exponential backoff for transient network errors."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _retry_after_delay(exc: Exception, base_delay: float, attempt: int) -> float:
    """Return the delay to sleep before the next attempt.

    If the exception carries an HTTP response with a Retry-After header (RFC
    6585 — required on 429, common on 503) that value is used.  Otherwise falls
    back to exponential backoff.

    httpx raises HTTPStatusError on 4xx/5xx; the exception carries the full
    response object (including headers) in its .response attribute.
    """
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            header = response.headers.get("Retry-After") or response.headers.get("retry-after")
            if header:
                return max(0.0, float(header))
        except Exception:
            pass
    return base_delay * (2 ** (attempt - 1))


def with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    label: str = "",
    no_retry: tuple[type[Exception], ...] = (),
) -> T:
    """Call fn(), retrying on transient errors with exponential backoff.

    Exceptions listed in no_retry propagate immediately without retry.
    If the exception carries an HTTP Retry-After header the server-specified
    delay is used instead of the exponential fallback.
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
            delay = _retry_after_delay(e, base_delay, attempt)
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
