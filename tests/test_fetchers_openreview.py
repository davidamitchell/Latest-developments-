"""Tests for OpenReviewFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.fetchers.openreview import OpenReviewFetcher

_ICLR_NOTES = {
    "notes": [
        {
            "id": "abc123",
            "tcdate": 1700000000000,
            "content": {
                "title": {"value": "Scaling Laws for Neural Language Models"},
                "abstract": {
                    "value": "We study empirical scaling laws for language model performance."
                },
                "authors": {"value": ["Jared Kaplan", "Sam McCandlish"]},
            },
        },
        {
            "id": "def456",
            "tcdate": 1700100000000,
            "content": {
                "title": {"value": "Chain-of-Thought Prompting Elicits Reasoning"},
                "abstract": {
                    "value": "We explore how chain-of-thought prompting improves reasoning."
                },
                "authors": {"value": ["Jason Wei", "Xuezhi Wang"]},
            },
        },
    ],
    "count": 2,
}

_NEURIPS_NOTES = {
    "notes": [
        {
            "id": "ghi789",
            "tcdate": 1700200000000,
            "content": {
                "title": {"value": "Attention Is All You Need"},
                "abstract": {
                    "value": "We propose a new simple network architecture, the Transformer."
                },
                "authors": {"value": ["Ashish Vaswani"]},
            },
        },
    ],
    "count": 1,
}


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


class TestOpenReviewFetcher:
    def test_happy_path_returns_items(self):
        venue = "ICLR.cc/2025/Conference/-/Accepted"
        fetcher = OpenReviewFetcher(venues=[venue], limit=25)
        with patch("httpx.get", return_value=_mock_response(_ICLR_NOTES)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 2
        urls = [i.url for i in items]
        assert "https://openreview.net/forum?id=abc123" in urls
        assert "https://openreview.net/forum?id=def456" in urls

    def test_multi_venue_fetch(self):
        venues = [
            "ICLR.cc/2025/Conference/-/Accepted",
            "NeurIPS.cc/2025/Conference/-/Accepted",
        ]
        fetcher = OpenReviewFetcher(venues=venues, limit=25)
        with patch(
            "httpx.get",
            side_effect=[
                _mock_response(_ICLR_NOTES),
                _mock_response(_NEURIPS_NOTES),
            ],
        ):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 3

    def test_http_error_fallback(self):
        """A venue that fails should be skipped; others still return items."""
        venues = [
            "ICLR.cc/2025/Conference/-/Accepted",  # will fail
            "NeurIPS.cc/2025/Conference/-/Accepted",  # will succeed
        ]
        fetcher = OpenReviewFetcher(venues=venues, limit=25)

        def _side_effect(url, **kwargs):
            params = kwargs.get("params", {})
            if "ICLR" in str(params.get("invitation", "")):
                raise ConnectionError("network down")
            return _mock_response(_NEURIPS_NOTES)

        with patch("httpx.get", side_effect=_side_effect):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1
        assert "ghi789" in items[0].url

    def test_source_class_is_primary(self):
        venue = "ICLR.cc/2025/Conference/-/Accepted"
        fetcher = OpenReviewFetcher(venues=[venue], limit=25)
        with patch("httpx.get", return_value=_mock_response(_ICLR_NOTES)):
            items = fetcher.fetch(already_processed=set())

        assert all(i.source_class == "primary" for i in items), (
            f"Expected all 'primary', got {[i.source_class for i in items]}"
        )

    def test_evidence_type_is_experiment(self):
        venue = "ICLR.cc/2025/Conference/-/Accepted"
        fetcher = OpenReviewFetcher(venues=[venue], limit=25)
        with patch("httpx.get", return_value=_mock_response(_ICLR_NOTES)):
            items = fetcher.fetch(already_processed=set())

        assert all(i.evidence_type == "experiment" for i in items), (
            f"Expected all 'experiment', got {[i.evidence_type for i in items]}"
        )

    def test_empty_venues_list_returns_empty(self):
        fetcher = OpenReviewFetcher(venues=[], limit=25)
        items = fetcher.fetch(already_processed=set())
        assert items == []

    def test_deduplication(self):
        venue = "ICLR.cc/2025/Conference/-/Accepted"
        fetcher = OpenReviewFetcher(venues=[venue], limit=25)
        already = {"https://openreview.net/forum?id=abc123"}
        with patch("httpx.get", return_value=_mock_response(_ICLR_NOTES)):
            items = fetcher.fetch(already_processed=already)

        urls = [i.url for i in items]
        assert "https://openreview.net/forum?id=abc123" not in urls
        assert len(items) == 1

    def test_published_date_parsed(self):
        venue = "ICLR.cc/2025/Conference/-/Accepted"
        fetcher = OpenReviewFetcher(venues=[venue], limit=25)
        with patch("httpx.get", return_value=_mock_response(_ICLR_NOTES)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].published is not None

    def test_source_name(self):
        venue = "ICLR.cc/2025/Conference/-/Accepted"
        fetcher = OpenReviewFetcher(venues=[venue], limit=25)
        with patch("httpx.get", return_value=_mock_response(_ICLR_NOTES)):
            items = fetcher.fetch(already_processed=set())

        assert all(i.source_name == "OpenReview" for i in items)
