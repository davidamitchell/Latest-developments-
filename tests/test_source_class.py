"""Tests for source class assignment across all fetchers (Epic 11, slice 11.5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.config import (
    BlogsConfig,
    HackerNewsConfig,
    RSSFeed,
    SubstackConfig,
    SubstackPublication,
    YouTubeChannel,
    YouTubeConfig,
)
from src.fetchers.hackernews import HackerNewsFetcher
from src.fetchers.rss import RSSFetcher
from src.fetchers.substack import SubstackFetcher
from src.fetchers.youtube import YouTubeFetcher

# ---------------------------------------------------------------------------
# YouTube fetcher → practitioner
# ---------------------------------------------------------------------------

_YT_SEARCH_RESPONSE = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "Test Video",
                "publishedAt": "2026-01-15T10:00:00Z",
                "channelTitle": "Test Channel",
            },
        }
    ]
}


def test_youtube_source_class_is_practitioner():
    cfg = YouTubeConfig(
        enabled=True,
        channels=[YouTubeChannel(name="Test Channel", channel_id="UC_test")],
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = _YT_SEARCH_RESPONSE

    # Create fetcher inside the patch so _api_key is populated from the mock env
    with patch("src.fetchers.youtube.os.environ.get", return_value="fake-key"):
        fetcher = YouTubeFetcher(config=cfg)
        with (
            patch("src.fetchers.youtube.httpx.get", return_value=mock_response),
            patch.object(fetcher._transcript_api, "fetch", return_value=[]),
        ):
            items = fetcher.fetch(already_processed=set())

    assert items, "Expected at least one item from YouTube fetcher"
    assert all(i.source_class == "practitioner" for i in items), (
        f"Expected all 'practitioner', got {[i.source_class for i in items]}"
    )


# ---------------------------------------------------------------------------
# Hacker News fetcher → practitioner
# ---------------------------------------------------------------------------

_HN_STORY = {
    "objectID": "99999",
    "title": "Show HN: New LLM benchmark",
    "url": "https://example.com/hn-story",
    "points": 250,
    "created_at": "2026-01-15T10:00:00Z",
    "story_text": None,
    "num_comments": 5,
}


def test_hackernews_source_class_is_practitioner():
    cfg = HackerNewsConfig(
        enabled=True,
        keywords=["LLM"],
        min_score=100,
        max_stories=5,
    )
    fetcher = HackerNewsFetcher(config=cfg)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"hits": [_HN_STORY]}

    with patch("src.fetchers.hackernews.httpx.get", return_value=mock_response):
        items = fetcher.fetch(already_processed=set())

    assert items, "Expected at least one item from HN fetcher"
    assert all(i.source_class == "practitioner" for i in items), (
        f"Expected all 'practitioner', got {[i.source_class for i in items]}"
    )


# ---------------------------------------------------------------------------
# Substack fetcher → media
# ---------------------------------------------------------------------------

_SUBSTACK_POSTS = [
    {
        "id": 1234567,
        "title": "The future of AI agents",
        "canonical_url": "https://testnewsletter.substack.com/p/ai-agents",
        "slug": "ai-agents",
        "description": "A deep dive into autonomous systems.",
        "post_date": "2026-01-15T10:00:00Z",
        "body_text": "Full body content here.",
    }
]


def test_substack_source_class_is_media():
    cfg = SubstackConfig(
        enabled=True,
        publications=[SubstackPublication(name="Test Newsletter", slug="testnewsletter")],
    )
    fetcher = SubstackFetcher(config=cfg)

    with patch("src.fetchers.substack._fetch_json", return_value=_SUBSTACK_POSTS):
        items = fetcher.fetch(already_processed=set())

    assert items, "Expected at least one item from Substack fetcher"
    assert all(i.source_class == "media" for i in items), (
        f"Expected all 'media', got {[i.source_class for i in items]}"
    )


# ---------------------------------------------------------------------------
# RSS fetcher → configurable per-feed source_class
# ---------------------------------------------------------------------------

_RSS_FEED_XML_BYTES = b"""\
<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Operator Blog</title>
    <item>
      <title>New model released</title>
      <link>https://example.com/release</link>
      <description>Details about the release.</description>
      <pubDate>Mon, 15 Jan 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


def test_rss_source_class_operator():
    """RSS feed inherits source_class from its config."""
    cfg = BlogsConfig(
        enabled=True,
        rss=[
            RSSFeed(
                name="Operator Blog",
                url="https://example.com/feed",
                source_class="operator",
            )
        ],
    )
    fetcher = RSSFetcher(config=cfg)

    with patch("src.fetchers.rss._fetch_url", return_value=_RSS_FEED_XML_BYTES):
        items = fetcher.fetch(already_processed=set())

    assert items, "Expected at least one item from RSS fetcher"
    assert all(i.source_class == "operator" for i in items), (
        f"Expected all 'operator', got {[i.source_class for i in items]}"
    )


def test_rss_source_class_practitioner_default():
    """RSS feed defaults to 'practitioner' when source_class not specified."""
    cfg = BlogsConfig(
        enabled=True,
        rss=[
            RSSFeed(
                name="Some Blog",
                url="https://example.com/feed",
            )
        ],
    )
    fetcher = RSSFetcher(config=cfg)

    with patch("src.fetchers.rss._fetch_url", return_value=_RSS_FEED_XML_BYTES):
        items = fetcher.fetch(already_processed=set())

    assert items, "Expected at least one item from RSS fetcher"
    assert all(i.source_class == "practitioner" for i in items), (
        f"Expected all 'practitioner', got {[i.source_class for i in items]}"
    )


def test_rss_source_class_media():
    cfg = BlogsConfig(
        enabled=True,
        rss=[
            RSSFeed(
                name="Tech News",
                url="https://example.com/feed",
                source_class="media",
            )
        ],
    )
    fetcher = RSSFetcher(config=cfg)

    with patch("src.fetchers.rss._fetch_url", return_value=_RSS_FEED_XML_BYTES):
        items = fetcher.fetch(already_processed=set())

    assert items
    assert all(i.source_class == "media" for i in items)


# ---------------------------------------------------------------------------
# arXiv fetcher → primary
# ---------------------------------------------------------------------------

_ARXIV_RSS = """\
<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>cs.AI updates on arXiv.org</title>
    <item>
      <title>A New LLM Architecture</title>
      <link>https://arxiv.org/abs/2501.99999</link>
      <description>Abstract: This paper proposes a novel architecture.</description>
      <pubDate>Tue, 29 Apr 2026 00:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


def test_arxiv_source_class_is_primary():
    from src.fetchers.arxiv import ArxivFetcher

    fetcher = ArxivFetcher(categories=["cs.AI"], max_papers=5)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = _ARXIV_RSS
    mock_response.status_code = 200

    # arXiv fetcher uses httpx.get directly (no _fetch_url wrapper)
    with patch("httpx.get", return_value=mock_response):
        items = fetcher.fetch(already_processed=set())

    assert items, "Expected at least one item from arXiv fetcher"
    assert all(i.source_class == "primary" for i in items), (
        f"Expected all 'primary', got {[i.source_class for i in items]}"
    )


# ---------------------------------------------------------------------------
# Hugging Face fetcher → primary
# ---------------------------------------------------------------------------

_HF_MODEL = {
    "id": "org/model-name",
    "modelId": "org/model-name",
    "pipeline_tag": "text-generation",
    "downloads": 500,
    "lastModified": "2026-01-15T10:00:00Z",
    "cardData": {"model_type": "llm"},
}


def test_huggingface_source_class_is_primary():
    from src.fetchers.huggingface import HuggingFaceFetcher

    fetcher = HuggingFaceFetcher(max_models=10, min_downloads=100)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [_HF_MODEL]

    with patch("src.fetchers.huggingface.httpx.get", return_value=mock_response):
        items = fetcher.fetch(already_processed=set())

    assert items, "Expected at least one item from HuggingFace fetcher"
    assert all(i.source_class == "primary" for i in items), (
        f"Expected all 'primary', got {[i.source_class for i in items]}"
    )
