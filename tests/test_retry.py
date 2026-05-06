"""Tests for src/retry.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.retry import _retry_after_delay, with_backoff


def test_success_on_first_attempt() -> None:
    calls = 0

    def fn() -> int:
        nonlocal calls
        calls += 1
        return 42

    assert with_backoff(fn, base_delay=0) == 42
    assert calls == 1


def test_retries_on_transient_error() -> None:
    calls = 0

    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("transient")
        return "ok"

    result = with_backoff(fn, max_attempts=3, base_delay=0)
    assert result == "ok"
    assert calls == 3


def test_raises_after_max_attempts() -> None:
    def fn() -> None:
        raise OSError("always fails")

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        with_backoff(fn, max_attempts=3, base_delay=0)


def test_no_retry_exceptions_propagate_immediately() -> None:
    calls = 0

    def fn() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        with_backoff(fn, max_attempts=3, base_delay=0, no_retry=(ValueError,))

    assert calls == 1  # did not retry


def test_label_in_error_message() -> None:
    def fn() -> None:
        raise OSError("boom")

    with pytest.raises(RuntimeError, match="fetch-op"):
        with_backoff(fn, max_attempts=1, base_delay=0, label="fetch-op")


# ── _retry_after_delay ───────────────────────────────────────────────────────

def test_retry_after_delay_falls_back_to_exponential() -> None:
    exc = RuntimeError("no header")
    assert _retry_after_delay(exc, base_delay=2.0, attempt=1) == 2.0
    assert _retry_after_delay(exc, base_delay=2.0, attempt=2) == 4.0
    assert _retry_after_delay(exc, base_delay=2.0, attempt=3) == 8.0


def test_retry_after_delay_reads_header_from_response() -> None:
    response = MagicMock()
    response.headers.get.side_effect = lambda k, default=None: "60" if k == "Retry-After" else default
    exc = RuntimeError("429")
    exc.response = response  # type: ignore[attr-defined]
    assert _retry_after_delay(exc, base_delay=1.0, attempt=1) == 60.0


def test_retry_after_delay_ignores_non_numeric_header() -> None:
    response = MagicMock()
    response.headers.get.side_effect = lambda k, default=None: (
        "Wed, 21 Oct 2026 07:28:00 GMT" if k == "Retry-After" else default
    )
    exc = RuntimeError("429")
    exc.response = response  # type: ignore[attr-defined]
    # Non-numeric (HTTP-date) Retry-After falls back to exponential
    assert _retry_after_delay(exc, base_delay=1.0, attempt=1) == 1.0


def test_with_backoff_uses_retry_after_header() -> None:
    """with_backoff() sleeps for the Retry-After value when the response provides it."""
    response = MagicMock()
    response.headers.get.side_effect = lambda k, default=None: "30" if k == "Retry-After" else default

    exc = OSError("rate limited")
    exc.response = response  # type: ignore[attr-defined]

    calls = 0

    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise exc
        return "ok"

    with patch("src.retry.time.sleep") as mock_sleep:
        result = with_backoff(fn, max_attempts=2, base_delay=99.0)

    assert result == "ok"
    mock_sleep.assert_called_once_with(30.0)
