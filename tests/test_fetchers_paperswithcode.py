"""Tests for PapersWithCodeFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.fetchers.paperswithcode import PapersWithCodeFetcher

_SAMPLE_PAPERS = [
    {
        "title": "Attention Is All You Need",
        "url": "https://paperswithcode.com/paper/attention-is-all-you-need",
        "arxiv_id": "1706.03762",
        "stars": 5000,
        "repository_set": [{"url": "https://github.com/tensorflow/tensor2tensor"}],
        "paper": {
            "url_pdf": "https://arxiv.org/pdf/1706.03762v5.pdf",
            "title": "Attention Is All You Need",
            "abstract": "The dominant sequence transduction models ...",
            "published": "2017-06-12",
        },
    },
    {
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "url": "https://paperswithcode.com/paper/bert-pre-training-of-deep-bidirectional",
        "arxiv_id": "1810.04805",
        "stars": 3000,
        "repository_set": [{"url": "https://github.com/google-research/bert"}],
        "paper": {
            "url_pdf": "https://arxiv.org/pdf/1810.04805v2.pdf",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "abstract": "We introduce a new language representation model ...",
            "published": "2018-10-11",
        },
    },
    {
        "title": "Low-Stars Paper",
        "url": "https://paperswithcode.com/paper/low-stars",
        "arxiv_id": "2001.00001",
        "stars": 2,
        "repository_set": [],
        "paper": {
            "url_pdf": "",
            "title": "Low-Stars Paper",
            "abstract": "Not popular.",
            "published": "2020-01-01",
        },
    },
]


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


class TestPapersWithCodeFetcher:
    def test_happy_path_returns_items(self):
        fetcher = PapersWithCodeFetcher(page_size=20, min_stars=0)
        payload = {"results": _SAMPLE_PAPERS, "count": len(_SAMPLE_PAPERS)}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 3
        urls = [i.url for i in items]
        assert "https://paperswithcode.com/paper/attention-is-all-you-need" in urls

    def test_empty_response_returns_empty(self):
        fetcher = PapersWithCodeFetcher()
        with patch("httpx.get", return_value=_mock_response({"results": [], "count": 0})):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_http_error_returns_empty(self):
        fetcher = PapersWithCodeFetcher()
        with patch("httpx.get", side_effect=ConnectionError("unreachable")):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_min_stars_filters_low_star_papers(self):
        fetcher = PapersWithCodeFetcher(min_stars=100)
        payload = {"results": _SAMPLE_PAPERS, "count": len(_SAMPLE_PAPERS)}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        # Only the two papers with stars >= 100 should pass
        assert len(items) == 2
        for item in items:
            assert "low-stars" not in item.url

    def test_source_class_is_primary(self):
        fetcher = PapersWithCodeFetcher()
        payload = {"results": _SAMPLE_PAPERS[:1], "count": 1}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1
        assert items[0].source_class == "primary"

    def test_has_code_is_true(self):
        fetcher = PapersWithCodeFetcher()
        payload = {"results": _SAMPLE_PAPERS[:1], "count": 1}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1
        assert items[0].has_code is True

    def test_deduplication_skips_already_processed(self):
        fetcher = PapersWithCodeFetcher()
        already = {"https://paperswithcode.com/paper/attention-is-all-you-need"}
        payload = {"results": _SAMPLE_PAPERS, "count": len(_SAMPLE_PAPERS)}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=already)

        urls = [i.url for i in items]
        assert "https://paperswithcode.com/paper/attention-is-all-you-need" not in urls

    def test_published_date_parsed(self):
        fetcher = PapersWithCodeFetcher()
        payload = {"results": _SAMPLE_PAPERS[:1], "count": 1}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].published is not None
        assert items[0].published.year == 2017

    def test_source_name(self):
        fetcher = PapersWithCodeFetcher()
        payload = {"results": _SAMPLE_PAPERS[:1], "count": 1}
        with patch("httpx.get", return_value=_mock_response(payload)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].source_name == "Papers with Code"

    def test_unexpected_api_format_returns_empty(self):
        fetcher = PapersWithCodeFetcher()
        with patch("httpx.get", return_value=_mock_response([])):
            items = fetcher.fetch(already_processed=set())

        assert items == []
