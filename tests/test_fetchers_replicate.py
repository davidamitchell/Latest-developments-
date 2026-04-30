"""Tests for ReplicateFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.fetchers.replicate import ReplicateFetcher

_SAMPLE_MODELS = [
    {
        "owner": "stability-ai",
        "name": "stable-diffusion",
        "url": "https://replicate.com/stability-ai/stable-diffusion",
        "description": "A latent text-to-image diffusion model.",
        "run_count": 1_000_000,
        "visibility": "public",
        "created_at": "2022-08-22T00:00:00Z",
    },
    {
        "owner": "meta",
        "name": "llama-2-70b-chat",
        "url": "https://replicate.com/meta/llama-2-70b-chat",
        "description": "Llama 2 70B chat model.",
        "run_count": 500_000,
        "visibility": "public",
        "created_at": "2023-07-18T00:00:00Z",
    },
    {
        "owner": "mistralai",
        "name": "mistral-7b-instruct-v0.2",
        "url": "https://replicate.com/mistralai/mistral-7b-instruct-v0.2",
        "description": "Mistral 7B instruct model.",
        "run_count": 300_000,
        "visibility": "public",
        "created_at": "2024-01-10T00:00:00Z",
    },
]


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


class TestReplicateFetcher:
    def test_happy_path_returns_items(self):
        fetcher = ReplicateFetcher(limit=20)
        payload = {"results": _SAMPLE_MODELS, "next": None}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 3
        urls = [i.url for i in items]
        assert "https://replicate.com/stability-ai/stable-diffusion" in urls

    def test_http_error_returns_empty(self):
        fetcher = ReplicateFetcher(limit=20)
        with patch("httpx.get", side_effect=ConnectionError("unreachable")):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_source_class_is_operator(self):
        fetcher = ReplicateFetcher(limit=20)
        payload = {"results": _SAMPLE_MODELS[:1], "next": None}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1
        assert items[0].source_class == "operator"

    def test_limit_respected(self):
        fetcher = ReplicateFetcher(limit=2)
        payload = {"results": _SAMPLE_MODELS, "next": None}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 2

    def test_deduplication(self):
        fetcher = ReplicateFetcher(limit=20)
        already = {"https://replicate.com/stability-ai/stable-diffusion"}
        payload = {"results": _SAMPLE_MODELS, "next": None}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=already)

        urls = [i.url for i in items]
        assert "https://replicate.com/stability-ai/stable-diffusion" not in urls

    def test_unexpected_format_returns_empty(self):
        fetcher = ReplicateFetcher(limit=20)
        with patch("httpx.get", return_value=_mock_response([])):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_published_date_parsed(self):
        fetcher = ReplicateFetcher(limit=20)
        payload = {"results": _SAMPLE_MODELS[:1], "next": None}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].published is not None
        assert items[0].published.year == 2022

    def test_source_name(self):
        fetcher = ReplicateFetcher(limit=20)
        payload = {"results": _SAMPLE_MODELS[:1], "next": None}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].source_name == "Replicate"
