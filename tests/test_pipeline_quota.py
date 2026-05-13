"""Tests for shared Gemini quota/model-not-found detection helpers."""

from __future__ import annotations

import pytest

from src.pipeline._quota import is_model_not_found_error


def test_model_not_found_detected_from_code_attribute() -> None:
    class FakeError(Exception):
        code = 404

    assert is_model_not_found_error(FakeError("not found")) is True


def test_model_not_found_detected_from_status_code_attribute() -> None:
    class FakeError(Exception):
        status_code = 404

    assert is_model_not_found_error(FakeError("not found")) is True


@pytest.mark.parametrize(
    "message",
    [
        "models/gemini-3-flash is not found for API version v1beta",
        "error status is NOT_FOUND for model deployment",
        """{"error":{"code":404,"message":"model not available"}}""",
        """{'error': {'code': 404, 'message': 'model unavailable'}}""",
    ],
)
def test_model_not_found_detected_from_supported_text_patterns(message: str) -> None:
    assert is_model_not_found_error(Exception(message)) is True


def test_quota_error_is_not_detected_as_model_not_found() -> None:
    exc = Exception("429 RESOURCE_EXHAUSTED quota exceeded for metric generate_content_requests")
    exc.code = 429  # type: ignore[attr-defined]
    assert is_model_not_found_error(exc) is False


def test_generic_transport_error_is_not_detected_as_model_not_found() -> None:
    assert is_model_not_found_error(Exception("connection reset by peer")) is False


def test_text_not_found_without_model_hint_is_not_detected() -> None:
    assert is_model_not_found_error(Exception("resource not_found in cache layer")) is False
