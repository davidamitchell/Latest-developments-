"""Tests for OpenRouterFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.fetchers.openrouter import OpenRouterFetcher

_SAMPLE_MODELS = [
    {
        "id": "openai/gpt-4o",
        "name": "GPT-4o",
        "description": "OpenAI's flagship multimodal model.",
        "pricing": {"prompt": "0.000005", "completion": "0.000015", "request": "0"},
        "context_length": 128000,
        "architecture": {"tokenizer": "GPT"},
    },
    {
        "id": "anthropic/claude-3-5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "description": "Anthropic's latest capable model.",
        "pricing": {"prompt": "0.000003", "completion": "0.000015", "request": "0"},
        "context_length": 200000,
        "architecture": {"tokenizer": "Claude"},
    },
    {
        "id": "meta-llama/llama-3-70b-instruct",
        "name": "Llama 3 70B Instruct",
        "description": "Meta's open LLM.",
        "pricing": {"prompt": "0.0000009", "completion": "0.0000009", "request": "0"},
        "context_length": 8192,
    },
]


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


class TestOpenRouterFetcher:
    def test_happy_path_returns_items(self):
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": _SAMPLE_MODELS}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 3

    def test_source_class_is_market(self):
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": _SAMPLE_MODELS[:1]}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].source_class == "market"

    def test_evidence_type_is_pricing(self):
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": _SAMPLE_MODELS[:1]}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].evidence_type == "pricing"

    def test_source_name_is_openrouter(self):
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": _SAMPLE_MODELS[:1]}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].source_name == "OpenRouter"

    def test_content_includes_pricing_info(self):
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": _SAMPLE_MODELS[:1]}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        content = items[0].content
        assert "Pricing:" in content
        assert "context" in content.lower()

    def test_limit_respected(self):
        fetcher = OpenRouterFetcher(limit=2)
        payload = {"data": _SAMPLE_MODELS}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 2

    def test_http_error_returns_empty(self):
        fetcher = OpenRouterFetcher(limit=100)
        with patch("httpx.get", side_effect=ConnectionError("unreachable")):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_unexpected_format_returns_empty(self):
        fetcher = OpenRouterFetcher(limit=100)
        with patch("httpx.get", return_value=_mock_response([])):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_url_uses_model_id(self):
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": _SAMPLE_MODELS[:1]}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert "openai/gpt-4o" in items[0].url

    def test_model_without_pricing_does_not_crash(self):
        model_no_pricing = {
            "id": "some/model",
            "name": "Some Model",
            "pricing": {},
            "context_length": 4096,
        }
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": [model_no_pricing]}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1

    def test_model_missing_id_skipped(self):
        bad_model = {"name": "No ID Model", "pricing": {"prompt": "0.001", "completion": "0.002"}}
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": [bad_model, *_SAMPLE_MODELS[:1]]}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1

    def test_dedup_key_includes_date(self):
        """Same model on the same date should not be re-fetched."""
        fetcher = OpenRouterFetcher(limit=100)
        payload = {"data": _SAMPLE_MODELS[:1]}

        with patch("httpx.get", return_value=_mock_response(payload)):
            items_first = fetcher.fetch(already_processed=set())

        # Re-run with the dedup key from first fetch
        already = {items_first[0].id}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items_second = fetcher.fetch(already_processed=already)

        assert items_second == []
