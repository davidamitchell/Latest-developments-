"""Tests for shared Gemini quota/model-not-found detection helpers."""

from __future__ import annotations

from src.pipeline._quota import is_model_not_found_error


def test_model_not_found_detected_from_code_attribute() -> None:
    class FakeError(Exception):
        code = 404

    assert is_model_not_found_error(FakeError("not found")) is True


def test_model_not_found_detected_from_error_text_without_code_attribute() -> None:
    msg = (
        "404 NOT_FOUND. {'error': {'code': 404, 'message': "
        "'models/gemini-3-flash is not found for API version v1beta', "
        "'status': 'NOT_FOUND'}}"
    )

    assert is_model_not_found_error(Exception(msg)) is True
