"""Exponential backoff for transient network errors."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
_RETRY_DELAY_PATTERN = re.compile(r"\s*(\d+)\s*s\s*")


def _server_retry_delay(exc: Exception) -> float | None:
    """Return server-instructed retry delay, if one is provided."""
    details = getattr(exc, "details", None)
    if isinstance(details, list):
        for entry in details:
            if not isinstance(entry, dict):
                continue
            if entry.get("@type") != "type.googleapis.com/google.rpc.RetryInfo":
                continue
            retry_delay = entry.get("retryDelay")
            if isinstance(retry_delay, str):
                match = _RETRY_DELAY_PATTERN.fullmatch(retry_delay)
                if match:
                    return float(match.group(1))
                logger.debug(
                    "Invalid Gemini RetryInfo.retryDelay value %r; using fallback", retry_delay
                )

    response = getattr(exc, "response", None)
    if response is not None:
        try:
            header = response.headers.get("Retry-After") or response.headers.get("retry-after")
            if header:
                return max(0.0, float(header))
        except Exception as exc:
            logger.debug("Could not parse Retry-After header: %s", exc)
    return None


def _retry_after_delay(
    exc: Exception,
    base_delay: float,
    attempt: int,
    *,
    server_delay: float | None = None,
) -> float:
    """Return the delay to sleep before the next attempt.

    If the exception is a Gemini ClientError containing structured RetryInfo
    details, that retryDelay value is used first.

    Otherwise, if the exception carries an HTTP response with a Retry-After
    header (RFC 6585 — required on 429, common on 503) that value is used.
    Falls back to exponential backoff when neither server hint is available.

    httpx raises HTTPStatusError on 4xx/5xx; the exception carries the full
    response object (including headers) in its .response attribute.
    """
    resolved_delay = server_delay if server_delay is not None else _server_retry_delay(exc)
    if resolved_delay is not None:
        return resolved_delay
    return base_delay * (2 ** (attempt - 1))


def _status_code(exc: Exception) -> int | None:
    """Best-effort extraction of HTTP status code from an exception."""
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_code = getattr(response, "status_code", None)
    return response_code if isinstance(response_code, int) else None


def _response_headers(exc: Exception) -> dict[str, str]:
    """Best-effort extraction of response headers from an exception."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(exc, "headers", None)
    if headers is None:
        return {}
    try:
        return {str(k): str(v) for k, v in headers.items()}
    except Exception:
        return {}


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
            instructed = _server_retry_delay(e)
            delay = _retry_after_delay(e, base_delay, attempt, server_delay=instructed)
            prefix = f"{label}: " if label else ""
            logger.warning(
                "%sfailed (attempt %d/%d): %s — retry in %.0fs",
                prefix,
                attempt,
                max_attempts,
                e,
                delay,
            )
            if _status_code(e) == 429:
                headers = _response_headers(e)
                logger.warning(
                    "%s429 retry timing: server instructed wait=%s; planned wait=%.3fs",
                    prefix,
                    f"{instructed:.3f}s" if instructed is not None else "none",
                    delay,
                )
                logger.warning("%s429 response headers: %s", prefix, headers)
                start = time.monotonic()
                time.sleep(delay)
                actual_wait = time.monotonic() - start
                logger.warning("%s429 retry timing: actual wait=%.3fs", prefix, actual_wait)
            else:
                time.sleep(delay)

    raise RuntimeError(f"{label or 'Operation'} failed after {max_attempts} attempts") from last_exc
