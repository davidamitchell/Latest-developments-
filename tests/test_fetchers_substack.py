"""Tests for src/fetchers/substack.py."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.config import SubstackConfig, SubstackPublication
from src.fetchers.substack import (
    SubstackFetcher,
    _fetch_json,
    _fetch_xml,
    _parse_api_date,
    _parse_api_posts,
    _PermanentHTTPError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(publications: list[dict] | None = None, enabled: bool = True) -> SubstackConfig:
    pubs = [SubstackPublication(name=p["name"], slug=p["slug"]) for p in (publications or [])]
    return SubstackConfig(enabled=enabled, publications=pubs)


def _api_post(
    title: str = "Test Post",
    slug: str = "test-post",
    canonical_url: str = "https://example.substack.com/p/test-post",
    body_text: str = "Post body text",
    post_date: str = "2026-02-22T10:00:00.000Z",
) -> dict:
    return {
        "id": 1,
        "title": title,
        "slug": slug,
        "canonical_url": canonical_url,
        "body_text": body_text,
        "description": "Post subtitle",
        "post_date": post_date,
    }


def _rss_xml_bytes(
    title: str = "RSS Post", link: str = "https://example.substack.com/p/rss-post"
) -> bytes:
    return f"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Newsletter</title>
    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>RSS description</description>
      <pubDate>Sat, 22 Feb 2026 07:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>""".encode()


# ---------------------------------------------------------------------------
# SubstackFetcher.fetch — top-level behaviour
# ---------------------------------------------------------------------------


class TestSubstackFetcher:
    def test_returns_empty_when_disabled(self) -> None:
        cfg = _make_config(publications=[{"name": "Test", "slug": "test"}], enabled=False)
        assert SubstackFetcher(cfg).fetch(set()) == []

    def test_returns_empty_when_no_publications(self) -> None:
        cfg = _make_config(publications=[])
        assert SubstackFetcher(cfg).fetch(set()) == []

    def test_fetches_new_item_from_json_api(self) -> None:
        cfg = _make_config(publications=[{"name": "Test Newsletter", "slug": "testnewsletter"}])
        posts = [_api_post()]

        with patch("src.fetchers.substack._fetch_json", return_value=posts):
            items = SubstackFetcher(cfg).fetch(set())

        assert len(items) == 1
        assert items[0].title == "Test Post"
        assert items[0].url == "https://example.substack.com/p/test-post"
        assert items[0].source_name == "Test Newsletter"
        assert items[0].content == "Post body text"

    def test_skips_already_processed_url(self) -> None:
        cfg = _make_config(publications=[{"name": "Test", "slug": "test"}])
        posts = [_api_post(canonical_url="https://example.substack.com/p/test-post")]

        with patch("src.fetchers.substack._fetch_json", return_value=posts):
            items = SubstackFetcher(cfg).fetch({"https://example.substack.com/p/test-post"})

        assert items == []

    def test_deduplicates_by_normalised_url(self) -> None:
        """URL stored with trailing slash must match feed URL without it."""
        cfg = _make_config(publications=[{"name": "Test", "slug": "test"}])
        posts = [_api_post(canonical_url="https://example.substack.com/p/test-post")]

        with patch("src.fetchers.substack._fetch_json", return_value=posts):
            items = SubstackFetcher(cfg).fetch({"https://example.substack.com/p/test-post/"})

        assert items == []

    def test_falls_back_to_rss_when_json_api_returns_403(self) -> None:
        cfg = _make_config(publications=[{"name": "Test", "slug": "test"}])
        rss = _rss_xml_bytes()

        def fake_fetch_json(url: str) -> list[dict]:
            raise _PermanentHTTPError("HTTP 403 fetching JSON API")

        with (
            patch("src.fetchers.substack._fetch_json", side_effect=fake_fetch_json),
            patch("src.fetchers.substack._fetch_xml", return_value=rss),
        ):
            items = SubstackFetcher(cfg).fetch(set())

        assert len(items) == 1
        assert items[0].title == "RSS Post"
        assert items[0].url == "https://example.substack.com/p/rss-post"

    def test_continues_after_publication_failure(self) -> None:
        cfg = _make_config(
            publications=[
                {"name": "Bad", "slug": "bad"},
                {"name": "Good", "slug": "good"},
            ]
        )
        good_posts = [_api_post(title="Good Post", canonical_url="https://good.substack.com/p/1")]

        def fake_fetch_json(url: str) -> list[dict]:
            if "bad" in url:
                raise OSError("network error")
            return good_posts

        with patch("src.fetchers.substack._fetch_json", side_effect=fake_fetch_json):
            items = SubstackFetcher(cfg).fetch(set())

        assert len(items) == 1
        assert items[0].source_name == "Good"

    def test_content_truncated_to_max_chars(self) -> None:
        cfg = _make_config(publications=[{"name": "Test", "slug": "test"}])
        posts = [_api_post(body_text="x" * 20_000)]

        with patch("src.fetchers.substack._fetch_json", return_value=posts):
            items = SubstackFetcher(cfg).fetch(set())

        assert len(items[0].content) == 12_000

    def test_published_date_parsed(self) -> None:
        cfg = _make_config(publications=[{"name": "Test", "slug": "test"}])
        posts = [_api_post(post_date="2026-02-22T10:00:00.000Z")]

        with patch("src.fetchers.substack._fetch_json", return_value=posts):
            items = SubstackFetcher(cfg).fetch(set())

        assert items[0].published is not None
        assert items[0].published.year == 2026
        assert items[0].published.month == 2

    def test_falls_back_to_description_when_no_body_text(self) -> None:
        cfg = _make_config(publications=[{"name": "Test", "slug": "test"}])
        post = _api_post()
        post["body_text"] = ""
        post["description"] = "Only a description"

        with patch("src.fetchers.substack._fetch_json", return_value=[post]):
            items = SubstackFetcher(cfg).fetch(set())

        assert items[0].content == "Only a description"

    def test_constructs_url_from_slug_when_no_canonical_url(self) -> None:
        cfg = _make_config(publications=[{"name": "Test", "slug": "myslug"}])
        post = _api_post(slug="my-post", canonical_url="")

        with patch("src.fetchers.substack._fetch_json", return_value=[post]):
            items = SubstackFetcher(cfg).fetch(set())

        assert items[0].url == "https://myslug.substack.com/p/my-post"

    def test_multiple_publications_aggregated(self) -> None:
        cfg = _make_config(
            publications=[
                {"name": "Pub A", "slug": "puba"},
                {"name": "Pub B", "slug": "pubb"},
            ]
        )
        posts_a = [_api_post(title="Post A", canonical_url="https://puba.substack.com/p/a")]
        posts_b = [_api_post(title="Post B", canonical_url="https://pubb.substack.com/p/b")]

        def fake_fetch_json(url: str) -> list[dict]:
            return posts_a if "puba" in url else posts_b

        with patch("src.fetchers.substack._fetch_json", side_effect=fake_fetch_json):
            items = SubstackFetcher(cfg).fetch(set())

        assert len(items) == 2
        assert {i.title for i in items} == {"Post A", "Post B"}


# ---------------------------------------------------------------------------
# _parse_api_posts — unit tests
# ---------------------------------------------------------------------------


class TestParseApiPosts:
    def test_basic_post(self) -> None:
        posts = [_api_post()]
        entries = _parse_api_posts(posts, "https://example.substack.com")
        assert len(entries) == 1
        assert entries[0]["url"] == "https://example.substack.com/p/test-post"
        assert entries[0]["title"] == "Test Post"
        assert entries[0]["content"] == "Post body text"

    def test_skips_post_with_no_url_and_no_slug(self) -> None:
        posts = [{"id": 1, "title": "No URL", "slug": "", "canonical_url": ""}]
        entries = _parse_api_posts(posts, "https://example.substack.com")
        assert entries == []

    def test_uses_canonical_url_over_slug(self) -> None:
        post = _api_post(canonical_url="https://custom.example.com/p/override", slug="test")
        entries = _parse_api_posts([post], "https://example.substack.com")
        assert entries[0]["url"] == "https://custom.example.com/p/override"

    def test_falls_back_to_description_when_no_body_text(self) -> None:
        post = _api_post()
        post["body_text"] = ""
        post["description"] = "Fallback description"
        entries = _parse_api_posts([post], "https://example.substack.com")
        assert entries[0]["content"] == "Fallback description"


# ---------------------------------------------------------------------------
# _parse_api_date — unit tests
# ---------------------------------------------------------------------------


class TestParseApiDate:
    def test_parses_substack_timestamp(self) -> None:
        dt = _parse_api_date("2026-02-22T10:00:00.000Z")
        assert dt == datetime(2026, 2, 22, 10, 0, 0)

    def test_parses_iso_without_milliseconds(self) -> None:
        dt = _parse_api_date("2026-02-22T10:00:00Z")
        assert dt == datetime(2026, 2, 22, 10, 0, 0)

    def test_returns_none_for_none_input(self) -> None:
        assert _parse_api_date(None) is None

    def test_returns_none_for_invalid_input(self) -> None:
        assert _parse_api_date("not-a-date") is None


# ---------------------------------------------------------------------------
# _fetch_json — HTTP behaviour
# ---------------------------------------------------------------------------


class TestFetchJson:
    def test_returns_parsed_json_list(self) -> None:
        posts = [_api_post()]
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = posts

        with patch("src.fetchers.substack.httpx.get", return_value=resp):
            result = _fetch_json("https://example.substack.com/api/v1/archive")

        assert result == posts

    def test_raises_permanent_error_on_403(self) -> None:
        resp = MagicMock()
        resp.status_code = 403

        with (
            patch("src.fetchers.substack.httpx.get", return_value=resp),
            pytest.raises(_PermanentHTTPError),
        ):
            _fetch_json("https://example.substack.com/api/v1/archive")

    def test_does_not_raise_permanent_error_on_429(self) -> None:
        """429 is rate limiting — should be retriable, not permanent."""
        import httpx

        resp = MagicMock()
        resp.status_code = 429
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=resp
        )

        with patch("src.fetchers.substack.httpx.get", return_value=resp):
            try:
                _fetch_json("https://example.substack.com/api/v1/archive")
            except _PermanentHTTPError:
                raise AssertionError("429 should NOT raise _PermanentHTTPError") from None
            except httpx.HTTPStatusError:
                pass  # correct — propagates for retry logic

    def test_raises_value_error_when_response_is_not_list(self) -> None:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"not": "a list"}

        with (
            patch("src.fetchers.substack.httpx.get", return_value=resp),
            pytest.raises(ValueError, match="Expected JSON array"),
        ):
            _fetch_json("https://example.substack.com/api/v1/archive")


# ---------------------------------------------------------------------------
# _fetch_xml — HTTP behaviour
# ---------------------------------------------------------------------------


class TestFetchXml:
    def test_returns_bytes(self) -> None:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.content = b"<rss/>"

        with patch("src.fetchers.substack.httpx.get", return_value=resp):
            result = _fetch_xml("https://example.substack.com/feed")

        assert result == b"<rss/>"

    def test_raises_permanent_error_on_404(self) -> None:
        resp = MagicMock()
        resp.status_code = 404

        with (
            patch("src.fetchers.substack.httpx.get", return_value=resp),
            pytest.raises(_PermanentHTTPError),
        ):
            _fetch_xml("https://example.substack.com/feed")
