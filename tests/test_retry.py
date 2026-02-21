"""Tests for src/retry.py."""

from __future__ import annotations

import pytest

from src.retry import with_backoff


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
