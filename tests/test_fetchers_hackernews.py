"""Tests for src/fetchers/hackernews.py."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from src.config import HackerNewsConfig
from src.fetchers.hackernews import HackerNewsFetcher, _parse_hn_date


def _make_config(**kwargs: object) -> HackerNewsConfig:
    defaults: dict = {
        "enabled": True,
        "min_score": 50,
        "keywords": ["LLM", "transformer"],
        "max_stories": 5,
    }
    defaults.update(kwargs)
    return HackerNewsConfig(**defaults)  # type: ignore[arg-type]


def _make_hit(
    story_id: str = "42",
    title: str = "GPT-5 with LLM features",
    url: str = "https://example.com/article",
    points: int = 200,
    num_comments: int = 50,
    created_at: str = "2026-02-21T07:00:00.000Z",
) -> dict:
    return {
        "objectID": story_id,
        "title": title,
        "url": url,
        "points": points,
        "num_comments": num_comments,
        "created_at": created_at,
    }


def _algolia_response(hits: list[dict]) -> dict:
    return {"hits": hits, "nbHits": len(hits), "page": 0}


class TestHackerNewsFetcher:
    def test_disabled_returns_empty(self) -> None:
        cfg = _make_config(enabled=False)
        assert HackerNewsFetcher(cfg).fetch(set()) == []

    def test_returns_fetched_items(self) -> None:
        cfg = _make_config()
        hit = _make_hit("42", title="GPT-5 with LLM features")

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([hit]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert len(items) == 1
        assert items[0].id == "42"
        assert items[0].title == "GPT-5 with LLM features"
        assert items[0].source_name == "Hacker News"
        # URL must point to the HN discussion page, not the external article
        assert items[0].url == "https://news.ycombinator.com/item?id=42"

    def test_skips_already_processed_story(self) -> None:
        cfg = _make_config()
        hit = _make_hit("99")

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([hit]),
        ):
            items = HackerNewsFetcher(cfg).fetch(already_processed={"99"})

        assert items == []

    def test_filters_by_keyword(self) -> None:
        cfg = _make_config(keywords=["LLM"])
        matching = _make_hit("1", title="New LLM benchmark released")
        non_matching = _make_hit("2", title="JavaScript framework update")

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([matching, non_matching]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert len(items) == 1
        assert items[0].id == "1"

    def test_keyword_match_is_case_insensitive(self) -> None:
        cfg = _make_config(keywords=["llm"])
        hit = _make_hit("1", title="Large LLM Discussion")

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([hit]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert len(items) == 1

    def test_keyword_match_on_url(self) -> None:
        cfg = _make_config(keywords=["transformer"])
        hit = _make_hit("1", title="New paper", url="https://arxiv.org/abs/transformer-study")

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([hit]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert len(items) == 1

    def test_respects_max_stories(self) -> None:
        cfg = _make_config(max_stories=2, keywords=["LLM"])
        hits = [_make_hit(str(i), title=f"LLM story {i}", points=100 + i) for i in range(5)]

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response(hits),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert len(items) == 2

    def test_stories_sorted_by_points_descending(self) -> None:
        cfg = _make_config(max_stories=3, keywords=["LLM"])
        hits = [
            _make_hit("1", title="LLM story A", points=300),
            _make_hit("2", title="LLM story B", points=100),
            _make_hit("3", title="LLM story C", points=200),
        ]

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response(hits),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert [i.id for i in items] == ["1", "3", "2"]

    def test_content_contains_points_and_comments(self) -> None:
        cfg = _make_config()
        hit = _make_hit("42", points=250, num_comments=88)

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([hit]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert "Points: 250" in items[0].content
        assert "Comments: 88" in items[0].content
        # Discussion URL is in the URL: header sent to AI — not duplicated in content
        assert "Discussion:" not in items[0].content

    def test_content_labels_article_url_as_context_only(self) -> None:
        """Article URL must be labelled so the AI doesn't use it as the item's canonical URL."""
        cfg = _make_config()
        hit = _make_hit("42", url="https://external.example.com/article")

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([hit]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert "https://external.example.com/article" in items[0].content
        # Must NOT appear as a bare 'Article:' label that could be mistaken for item URL
        assert "Article:" not in items[0].content
        assert "context only" in items[0].content.lower()

    def test_uses_hn_url_when_no_article_url(self) -> None:
        cfg = _make_config()
        hit = _make_hit("55", url="")
        hit["url"] = None  # no external URL (Ask HN etc.)

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([hit]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert items[0].url == "https://news.ycombinator.com/item?id=55"

    def test_published_date_parsed(self) -> None:
        cfg = _make_config()
        hit = _make_hit("1", created_at="2026-02-21T07:30:00.000Z")

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([hit]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert items[0].published is not None
        assert items[0].published.year == 2026
        assert items[0].published.day == 21

    def test_network_failure_returns_empty(self) -> None:
        cfg = _make_config()

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            side_effect=OSError("network error"),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert items == []

    def test_empty_hits_returns_empty(self) -> None:
        cfg = _make_config()

        with patch(
            "src.fetchers.hackernews._fetch_algolia",
            return_value=_algolia_response([]),
        ):
            items = HackerNewsFetcher(cfg).fetch(set())

        assert items == []


class TestParseHnDate:
    def test_parses_algolia_timestamp(self) -> None:
        result = _parse_hn_date("2026-02-21T07:00:00.000Z")
        assert result is not None
        assert result == datetime(2026, 2, 21, 7, 0, 0)

    def test_returns_none_for_empty(self) -> None:
        assert _parse_hn_date("") is None
        assert _parse_hn_date(None) is None

    def test_returns_none_for_invalid(self) -> None:
        assert _parse_hn_date("not-a-date") is None
