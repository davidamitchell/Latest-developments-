"""Tests for ArxivFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.fetchers.arxiv import ArxivFetcher

_SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>cs.AI updates on arXiv.org</title>
    <item>
      <title>Attention Is All You Need (Revisited)</title>
      <link>https://arxiv.org/abs/2501.00001</link>
      <description>We revisit the transformer architecture...</description>
      <pubDate>Tue, 29 Apr 2026 00:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Scaling Laws for Large Language Models</title>
      <link>https://arxiv.org/abs/2501.00002</link>
      <description>We study scaling behaviour across compute regimes...</description>
      <pubDate>Tue, 29 Apr 2026 00:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Already Seen Paper</title>
      <link>https://arxiv.org/abs/2501.00003</link>
      <description>This paper was already processed.</description>
      <pubDate>Mon, 28 Apr 2026 00:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

_EMPTY_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>cs.LG updates on arXiv.org</title>
  </channel>
</rss>
"""


def _mock_response(text: str, status_code: int = 200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


class TestArxivFetcher:
    def test_basic_fetch_returns_items(self):
        fetcher = ArxivFetcher(categories=["cs.AI"], max_papers=10)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 3
        assert items[0].title == "Attention Is All You Need (Revisited)"
        assert items[0].url == "https://arxiv.org/abs/2501.00001"
        assert items[0].source_class == "primary"
        assert items[0].source_name == "arXiv"
        assert items[0].source_type == "arXiv"

    def test_deduplication_skips_processed(self):
        already = {"https://arxiv.org/abs/2501.00003"}
        fetcher = ArxivFetcher(categories=["cs.AI"], max_papers=10)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
            items = fetcher.fetch(already_processed=already)

        urls = [i.url for i in items]
        assert "https://arxiv.org/abs/2501.00003" not in urls
        assert len(items) == 2

    def test_max_papers_limit(self):
        fetcher = ArxivFetcher(categories=["cs.AI"], max_papers=1)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1

    def test_empty_feed_returns_empty_list(self):
        fetcher = ArxivFetcher(categories=["cs.LG"], max_papers=10)
        with patch("httpx.get", return_value=_mock_response(_EMPTY_RSS)):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_multiple_categories_aggregated(self):
        fetcher = ArxivFetcher(categories=["cs.AI", "cs.LG"], max_papers=10)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
            items = fetcher.fetch(already_processed=set())

        # Two categories × 3 items each = 6
        assert len(items) == 6

    def test_network_failure_skips_category_gracefully(self):
        fetcher = ArxivFetcher(categories=["cs.AI", "cs.LG"], max_papers=10)

        def side_effect(url, **kwargs):
            if "cs.AI" in url:
                raise ConnectionError("network down")
            return _mock_response(_SAMPLE_RSS)

        with patch("httpx.get", side_effect=side_effect):
            items = fetcher.fetch(already_processed=set())

        # cs.AI failed → 0; cs.LG succeeded → 3
        assert len(items) == 3

    def test_malformed_xml_returns_empty(self):
        fetcher = ArxivFetcher(categories=["cs.AI"], max_papers=10)
        with patch("httpx.get", return_value=_mock_response("<not valid xml <<<")):
            items = fetcher.fetch(already_processed=set())

        assert items == []

    def test_item_id_prefixed_with_arxiv(self):
        fetcher = ArxivFetcher(categories=["cs.AI"], max_papers=10)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
            items = fetcher.fetch(already_processed=set())

        assert all(i.id.startswith("arxiv:") for i in items)

    def test_published_date_parsed(self):
        fetcher = ArxivFetcher(categories=["cs.AI"], max_papers=10)
        with patch("httpx.get", return_value=_mock_response(_SAMPLE_RSS)):
            items = fetcher.fetch(already_processed=set())

        assert items[0].published is not None
        assert items[0].published.year == 2026
