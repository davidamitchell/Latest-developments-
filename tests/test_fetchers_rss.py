"""Tests for src/fetchers/rss.py."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.config import BlogsConfig, RSSFeed
from src.fetchers.rss import (
    RSSFetcher,
    _PermanentHTTPError,
    _fetch_url,
    _normalise_url,
    _parse_atom_date,
    _parse_entries,
    _parse_rfc2822_date,
)

# ---------------------------------------------------------------------------
# Helpers: minimal valid feed XML
# ---------------------------------------------------------------------------

_RSS_TEMPLATE = """\
<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    {items}
  </channel>
</rss>"""

_RSS_ITEM = """\
<item>
  <title>{title}</title>
  <link>{link}</link>
  <description>{description}</description>
  <pubDate>Sat, 22 Feb 2026 07:00:00 GMT</pubDate>
</item>"""

_ATOM_TEMPLATE = """\
<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Blog</title>
  {entries}
</feed>"""

_ATOM_ENTRY = """\
<entry xmlns="http://www.w3.org/2005/Atom">
  <title>{title}</title>
  <link rel="alternate" href="{link}" />
  <summary>{summary}</summary>
  <published>2026-02-22T07:00:00</published>
</entry>"""


def _rss_xml(*items: dict) -> bytes:
    rendered = "".join(
        _RSS_ITEM.format(
            title=i.get("title", "Post"),
            link=i.get("link", "https://example.com/post"),
            description=i.get("description", ""),
        )
        for i in items
    )
    return _RSS_TEMPLATE.format(items=rendered).encode()


def _atom_xml(*entries: dict) -> bytes:
    rendered = "".join(
        _ATOM_ENTRY.format(
            title=e.get("title", "Post"),
            link=e.get("link", "https://example.com/post"),
            summary=e.get("summary", ""),
        )
        for e in entries
    )
    return _ATOM_TEMPLATE.format(entries=rendered).encode()


def _make_config(feeds: list[dict] | None = None, enabled: bool = True) -> BlogsConfig:
    rss = [RSSFeed(name=f["name"], url=f["url"]) for f in (feeds or [])]
    return BlogsConfig(enabled=enabled, rss=rss)


# ---------------------------------------------------------------------------
# RSSFetcher.fetch
# ---------------------------------------------------------------------------

class TestRSSFetcher:
    def test_returns_empty_when_disabled(self) -> None:
        cfg = _make_config(feeds=[{"name": "Blog", "url": "https://example.com/feed"}], enabled=False)
        assert RSSFetcher(cfg).fetch(set()) == []

    def test_returns_empty_when_no_feeds_configured(self) -> None:
        cfg = _make_config(feeds=[])
        assert RSSFetcher(cfg).fetch(set()) == []

    def test_fetches_new_rss_item(self) -> None:
        cfg = _make_config(feeds=[{"name": "Blog", "url": "https://example.com/feed"}])
        xml = _rss_xml({"title": "Test Post", "link": "https://example.com/1"})

        with patch("src.fetchers.rss._fetch_url", return_value=xml):
            items = RSSFetcher(cfg).fetch(set())

        assert len(items) == 1
        assert items[0].title == "Test Post"
        assert items[0].url == "https://example.com/1"
        assert items[0].source_name == "Blog"

    def test_fetches_new_atom_item(self) -> None:
        cfg = _make_config(feeds=[{"name": "Blog", "url": "https://example.com/feed"}])
        xml = _atom_xml({"title": "Atom Post", "link": "https://example.com/atom-1"})

        with patch("src.fetchers.rss._fetch_url", return_value=xml):
            items = RSSFetcher(cfg).fetch(set())

        assert len(items) == 1
        assert items[0].title == "Atom Post"
        assert items[0].url == "https://example.com/atom-1"

    def test_skips_already_processed_url(self) -> None:
        cfg = _make_config(feeds=[{"name": "Blog", "url": "https://example.com/feed"}])
        xml = _rss_xml({"title": "Old Post", "link": "https://example.com/1"})

        with patch("src.fetchers.rss._fetch_url", return_value=xml):
            items = RSSFetcher(cfg).fetch({"https://example.com/1"})

        assert items == []

    def test_deduplicates_by_normalised_url(self) -> None:
        """URL stored with trailing slash matches feed URL without it."""
        cfg = _make_config(feeds=[{"name": "Blog", "url": "https://example.com/feed"}])
        xml = _rss_xml({"link": "https://example.com/1"})

        with patch("src.fetchers.rss._fetch_url", return_value=xml):
            items = RSSFetcher(cfg).fetch({"https://example.com/1/"})

        assert items == []

    def test_continues_after_feed_failure(self) -> None:
        cfg = _make_config(feeds=[
            {"name": "Bad", "url": "https://bad.example.com/feed"},
            {"name": "Good", "url": "https://good.example.com/feed"},
        ])
        good_xml = _rss_xml({"title": "Good Post", "link": "https://good.example.com/1"})

        def fake_fetch(url: str) -> bytes:
            if "bad" in url:
                raise OSError("network error")
            return good_xml

        with patch("src.fetchers.rss._fetch_url", side_effect=fake_fetch):
            items = RSSFetcher(cfg).fetch(set())

        assert len(items) == 1
        assert items[0].source_name == "Good"

    def test_content_truncated_to_max_chars(self) -> None:
        cfg = _make_config(feeds=[{"name": "Blog", "url": "https://example.com/feed"}])
        xml = _rss_xml({"description": "x" * 20_000, "link": "https://example.com/1"})

        with patch("src.fetchers.rss._fetch_url", return_value=xml):
            items = RSSFetcher(cfg).fetch(set())

        assert len(items[0].content) == 12_000

    def test_multiple_feeds_aggregated(self) -> None:
        cfg = _make_config(feeds=[
            {"name": "Feed A", "url": "https://a.example.com/feed"},
            {"name": "Feed B", "url": "https://b.example.com/feed"},
        ])
        xml_a = _rss_xml({"title": "A1", "link": "https://a.example.com/1"})
        xml_b = _rss_xml({"title": "B1", "link": "https://b.example.com/1"})

        def fake_fetch(url: str) -> bytes:
            return xml_a if "a.example" in url else xml_b

        with patch("src.fetchers.rss._fetch_url", side_effect=fake_fetch):
            items = RSSFetcher(cfg).fetch(set())

        assert len(items) == 2
        assert {i.title for i in items} == {"A1", "B1"}

    def test_published_date_parsed(self) -> None:
        cfg = _make_config(feeds=[{"name": "Blog", "url": "https://example.com/feed"}])
        xml = _rss_xml({"link": "https://example.com/1"})

        with patch("src.fetchers.rss._fetch_url", return_value=xml):
            items = RSSFetcher(cfg).fetch(set())

        assert items[0].published is not None
        assert items[0].published.year == 2026


# ---------------------------------------------------------------------------
# _parse_entries — unit tests for both feed formats
# ---------------------------------------------------------------------------

class TestParseEntries:
    def test_rss_items(self) -> None:
        xml = _rss_xml(
            {"title": "Post 1", "link": "https://example.com/1"},
            {"title": "Post 2", "link": "https://example.com/2"},
        )
        root = ET.fromstring(xml)
        entries = _parse_entries(root)
        assert len(entries) == 2
        assert entries[0]["url"] == "https://example.com/1"
        assert entries[1]["title"] == "Post 2"

    def test_atom_entries(self) -> None:
        xml = _atom_xml(
            {"title": "Atom 1", "link": "https://example.com/a1"},
        )
        root = ET.fromstring(xml)
        entries = _parse_entries(root)
        assert len(entries) == 1
        assert entries[0]["url"] == "https://example.com/a1"
        assert entries[0]["title"] == "Atom 1"

    def test_unknown_format_returns_empty(self) -> None:
        root = ET.fromstring("<unknown><data/></unknown>")
        assert _parse_entries(root) == []


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------

class TestNormaliseUrl:
    def test_strips_trailing_slash(self) -> None:
        assert _normalise_url("https://example.com/post/") == "https://example.com/post"

    def test_strips_whitespace(self) -> None:
        assert _normalise_url("  https://example.com/post  ") == "https://example.com/post"

    def test_empty_string(self) -> None:
        assert _normalise_url("") == ""


class TestParseDates:
    def test_atom_date_iso_format(self) -> None:
        dt = _parse_atom_date("2026-02-22T07:00:00")
        assert dt == datetime(2026, 2, 22, 7, 0, 0)

    def test_atom_date_none_input(self) -> None:
        assert _parse_atom_date(None) is None

    def test_atom_date_invalid_returns_none(self) -> None:
        assert _parse_atom_date("not a date") is None

    def test_rfc2822_date_valid(self) -> None:
        dt = _parse_rfc2822_date("Sat, 22 Feb 2026 07:00:00 GMT")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 22

    def test_rfc2822_date_none_input(self) -> None:
        assert _parse_rfc2822_date(None) is None

    def test_rfc2822_date_invalid_returns_none(self) -> None:
        assert _parse_rfc2822_date("garbage") is None


# ---------------------------------------------------------------------------
# _fetch_url — User-Agent and permanent-error behaviour
# ---------------------------------------------------------------------------

class TestFetchUrl:
    def test_sends_browser_user_agent(self) -> None:
        """Cloudflare blocks bare httpx UA; confirm a browser UA is sent."""
        import httpx

        captured_headers: dict = {}

        def mock_get(url: str, **kwargs: object) -> MagicMock:
            captured_headers.update(kwargs.get("headers", {}))
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b"<rss/>"
            resp.raise_for_status.return_value = None
            return resp

        with patch("src.fetchers.rss.httpx.get", side_effect=mock_get):
            _fetch_url("https://example.com/feed")

        ua = captured_headers.get("User-Agent", "")
        assert "Mozilla" in ua, f"Expected browser UA, got: {ua!r}"

    def test_raises_permanent_error_on_403(self) -> None:
        """403 responses must raise _PermanentHTTPError, not a retriable exception."""
        import httpx

        resp = MagicMock()
        resp.status_code = 403
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=resp
        )

        with patch("src.fetchers.rss.httpx.get", return_value=resp):
            try:
                _fetch_url("https://example.com/feed")
                assert False, "Expected _PermanentHTTPError"
            except _PermanentHTTPError:
                pass  # correct

    def test_does_not_raise_permanent_error_on_429(self) -> None:
        """429 (rate limit) should be retriable — must NOT raise _PermanentHTTPError."""
        import httpx

        resp = MagicMock()
        resp.status_code = 429
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=resp
        )

        with patch("src.fetchers.rss.httpx.get", return_value=resp):
            try:
                _fetch_url("https://example.com/feed")
            except _PermanentHTTPError:
                assert False, "429 should NOT raise _PermanentHTTPError"
            except httpx.HTTPStatusError:
                pass  # correct — propagates for retry logic
