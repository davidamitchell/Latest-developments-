"""Tests for HuggingFaceFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.fetchers.huggingface import HuggingFaceFetcher

_SAMPLE_MODELS = [
    {
        "modelId": "mistralai/Mistral-7B-v0.3",
        "pipeline_tag": "text-generation",
        "downloads": 500_000,
        "likes": 1200,
        "lastModified": "2026-04-28T12:00:00Z",
        "tags": ["transformers", "pytorch", "mistral"],
        "cardData": {"model_summary": "A 7B parameter base model."},
    },
    {
        "modelId": "google/gemma-2b",
        "pipeline_tag": "text-generation",
        "downloads": 300_000,
        "likes": 800,
        "lastModified": "2026-04-27T10:00:00Z",
        "tags": ["transformers", "pytorch"],
        "cardData": {},
    },
    {
        "modelId": "openai/clip-vit-base",  # non-text task — should be filtered
        "pipeline_tag": "zero-shot-image-classification",
        "downloads": 1_000_000,
        "likes": 2000,
        "lastModified": "2026-04-25T08:00:00Z",
        "tags": ["clip"],
        "cardData": {},
    },
    {
        "modelId": "tiny/low-downloads",
        "pipeline_tag": "text-generation",
        "downloads": 5,  # below min_downloads threshold
        "likes": 1,
        "lastModified": "2026-04-26T00:00:00Z",
        "tags": [],
        "cardData": {},
    },
]


def _mock_response(data):
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


class TestHuggingFaceFetcher:
    def test_basic_fetch_returns_relevant_items(self):
        fetcher = HuggingFaceFetcher(max_models=50, min_downloads=100)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_MODELS)):
            items = fetcher.fetch(already_processed=set())

        # Only mistral and gemma pass task + downloads filter
        assert len(items) == 2
        model_ids = [i.id for i in items]
        assert "hf:mistralai/Mistral-7B-v0.3" in model_ids
        assert "hf:google/gemma-2b" in model_ids

    def test_irrelevant_pipeline_filtered(self):
        fetcher = HuggingFaceFetcher(max_models=50, min_downloads=0)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_MODELS)):
            items = fetcher.fetch(already_processed=set())

        ids = [i.id for i in items]
        assert "hf:openai/clip-vit-base" not in ids

    def test_low_downloads_filtered(self):
        fetcher = HuggingFaceFetcher(max_models=50, min_downloads=100)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_MODELS)):
            items = fetcher.fetch(already_processed=set())

        ids = [i.id for i in items]
        assert "hf:tiny/low-downloads" not in ids

    def test_source_class_is_primary(self):
        fetcher = HuggingFaceFetcher(max_models=10, min_downloads=0)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_MODELS[:1])):
            items = fetcher.fetch(already_processed=set())

        assert items[0].source_class == "primary"
        assert items[0].source_name == "Hugging Face"

    def test_deduplication(self):
        already = {"https://huggingface.co/mistralai/Mistral-7B-v0.3"}
        fetcher = HuggingFaceFetcher(max_models=50, min_downloads=0)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_MODELS)):
            items = fetcher.fetch(already_processed=already)

        ids = [i.id for i in items]
        assert "hf:mistralai/Mistral-7B-v0.3" not in ids

    def test_max_models_limit(self):
        fetcher = HuggingFaceFetcher(max_models=1, min_downloads=0)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_MODELS)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1

    def test_network_failure_returns_empty(self):
        fetcher = HuggingFaceFetcher(max_models=50, min_downloads=0)
        with patch("httpx.get", side_effect=ConnectionError("down")):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_bad_api_response_returns_empty(self):
        fetcher = HuggingFaceFetcher(max_models=50, min_downloads=0)
        with patch("httpx.get", return_value=_mock_response({"error": "bad"})):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_published_date_parsed(self):
        fetcher = HuggingFaceFetcher(max_models=10, min_downloads=0)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_MODELS[:1])):
            items = fetcher.fetch(already_processed=set())

        assert items[0].published is not None
        assert items[0].published.year == 2026
