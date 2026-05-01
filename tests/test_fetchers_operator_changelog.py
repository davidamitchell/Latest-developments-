"""Tests for OperatorChangelogFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.fetchers.operator_changelog import OperatorChangelogFetcher

_ANTHROPIC_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Anthropic Blog</title>
    <link>https://www.anthropic.com/news</link>
    <item>
      <title>Claude 3.5 Sonnet release</title>
      <link>https://www.anthropic.com/news/claude-3-5-sonnet</link>
      <description>Announcing Claude 3.5 Sonnet with improved capabilities.</description>
      <pubDate>Mon, 20 Jun 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Constitutional AI update</title>
      <link>https://www.anthropic.com/news/constitutional-ai-update</link>
      <description>How we improved Constitutional AI.</description>
      <pubDate>Fri, 15 Jun 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

_OPENAI_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>OpenAI Blog</title>
    <link>https://openai.com/blog</link>
    <item>
      <title>GPT-5 announcement</title>
      <link>https://openai.com/blog/gpt-5</link>
      <description>Introducing GPT-5 with improved reasoning.</description>
      <pubDate>Tue, 18 Jun 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


def _mock_bytes_response(content: bytes) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


def _mock_http_error(status_code: int = 500) -> MagicMock:
    from httpx import HTTPStatusError, Request, Response

    request = Request("GET", "https://example.com")
    response = MagicMock(spec=Response)
    response.status_code = status_code
    exc = HTTPStatusError("error", request=request, response=response)
    return exc


class TestOperatorChangelogFetcher:
    def test_happy_path_multiple_feeds(self):
        feeds = [
            "https://www.anthropic.com/rss.xml",
            "https://openai.com/blog/rss.xml",
        ]
        fetcher = OperatorChangelogFetcher(feeds=feeds)

        with patch(
            "src.fetchers.operator_changelog.httpx.get",
            side_effect=[
                _mock_bytes_response(_ANTHROPIC_RSS),
                _mock_bytes_response(_OPENAI_RSS),
            ],
        ):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 3
        urls = [i.url for i in items]
        assert "https://www.anthropic.com/news/claude-3-5-sonnet" in urls
        assert "https://openai.com/blog/gpt-5" in urls

    def test_per_feed_failure_continues(self):
        """A single failing feed must not abort the entire fetch."""
        feeds = [
            "https://www.anthropic.com/rss.xml",  # will fail
            "https://openai.com/blog/rss.xml",  # will succeed
        ]
        fetcher = OperatorChangelogFetcher(feeds=feeds)

        def _side_effect(url, **kwargs):
            if "anthropic" in url:
                raise ConnectionError("network down")
            return _mock_bytes_response(_OPENAI_RSS)

        with patch("src.fetchers.operator_changelog.httpx.get", side_effect=_side_effect):
            items = fetcher.fetch(already_processed=set())

        # Should still get OpenAI items
        assert len(items) == 1
        assert items[0].url == "https://openai.com/blog/gpt-5"

    def test_source_class_is_operator(self):
        feeds = ["https://www.anthropic.com/rss.xml"]
        fetcher = OperatorChangelogFetcher(feeds=feeds)

        with patch(
            "src.fetchers.operator_changelog.httpx.get",
            return_value=_mock_bytes_response(_ANTHROPIC_RSS),
        ):
            items = fetcher.fetch(already_processed=set())

        assert all(i.source_class == "operator" for i in items), (
            f"Expected all 'operator', got {[i.source_class for i in items]}"
        )

    def test_dedup_by_url_across_feeds(self):
        """The same URL appearing in two feeds should only produce one item."""
        duplicate_rss = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Duplicate post</title>
      <link>https://www.anthropic.com/news/claude-3-5-sonnet</link>
      <description>Duplicate.</description>
    </item>
  </channel>
</rss>"""

        feeds = [
            "https://www.anthropic.com/rss.xml",
            "https://mirror.example.com/anthropic.xml",
        ]
        fetcher = OperatorChangelogFetcher(feeds=feeds)

        with patch(
            "src.fetchers.operator_changelog.httpx.get",
            side_effect=[
                _mock_bytes_response(_ANTHROPIC_RSS),  # has /claude-3-5-sonnet
                _mock_bytes_response(duplicate_rss),  # also has /claude-3-5-sonnet
            ],
        ):
            items = fetcher.fetch(already_processed=set())

        urls = [i.url for i in items]
        assert urls.count("https://www.anthropic.com/news/claude-3-5-sonnet") == 1

    def test_empty_feeds_list_returns_empty(self):
        fetcher = OperatorChangelogFetcher(feeds=[])
        items = fetcher.fetch(already_processed=set())
        assert items == []

    def test_already_processed_skipped(self):
        feeds = ["https://www.anthropic.com/rss.xml"]
        fetcher = OperatorChangelogFetcher(feeds=feeds)
        already = {"https://www.anthropic.com/news/claude-3-5-sonnet"}

        with patch(
            "src.fetchers.operator_changelog.httpx.get",
            return_value=_mock_bytes_response(_ANTHROPIC_RSS),
        ):
            items = fetcher.fetch(already_processed=already)

        urls = [i.url for i in items]
        assert "https://www.anthropic.com/news/claude-3-5-sonnet" not in urls

    def test_custom_source_class(self):
        """source_class constructor parameter overrides the default 'operator'."""
        feeds = ["https://github.com/ollama/ollama/releases.atom"]
        fetcher = OperatorChangelogFetcher(feeds=feeds, source_class="practitioner")

        rss = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>v0.3.6</title>
      <link>https://github.com/ollama/ollama/releases/tag/v0.3.6</link>
      <description>Ollama release notes.</description>
    </item>
  </channel>
</rss>"""

        with patch(
            "src.fetchers.operator_changelog.httpx.get",
            return_value=_mock_bytes_response(rss),
        ):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1
        assert items[0].source_class == "practitioner"

    def test_pricing_keyword_sets_evidence_type(self):
        """Items mentioning pricing keywords should get evidence_type='pricing'."""
        feeds = ["https://openai.com/blog/rss.xml"]
        fetcher = OperatorChangelogFetcher(feeds=feeds)

        pricing_rss = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>New pricing for GPT-4o: $5 per million tokens</title>
      <link>https://openai.com/blog/new-pricing</link>
      <description>We are updating our pricing structure for GPT-4o.</description>
    </item>
  </channel>
</rss>"""

        with patch(
            "src.fetchers.operator_changelog.httpx.get",
            return_value=_mock_bytes_response(pricing_rss),
        ):
            items = fetcher.fetch(already_processed=set())

        assert len(items) == 1
        assert items[0].evidence_type == "pricing"

    def test_non_pricing_item_has_empty_evidence_type(self):
        """Items without pricing keywords should have evidence_type=''."""
        feeds = ["https://www.anthropic.com/rss.xml"]
        fetcher = OperatorChangelogFetcher(feeds=feeds)

        with patch(
            "src.fetchers.operator_changelog.httpx.get",
            return_value=_mock_bytes_response(_ANTHROPIC_RSS),
        ):
            items = fetcher.fetch(already_processed=set())

        assert all(i.evidence_type == "" for i in items)
