"""Live integration test: validates YouTube Data API connectivity using the real key.

Skipped automatically when YOUTUBE_API_KEY is not set (unit test runs, fork PRs).
Run locally with: YOUTUBE_API_KEY=<key> pytest tests/test_youtube_api_live.py -v
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("YOUTUBE_API_KEY"),
    reason="YOUTUBE_API_KEY not set — skipping live API test",
)


def test_youtube_api_returns_results() -> None:
    """YouTube Data API v3 search.list returns at least 1 video for a known active channel."""
    key = os.environ["YOUTUBE_API_KEY"]
    resp = httpx.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "channelId": "UC295-Dw4tzbMmcArTTnNMcQ",  # Google Developers — regularly publishes
            "type": "video",
            "order": "date",
            "maxResults": 1,
            "key": key,
        },
        timeout=15,
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:300]}"
    items = resp.json().get("items", [])
    assert len(items) >= 1, (
        "API returned 0 results for the Google Developers channel — "
        "check that the key is valid and YouTube Data API v3 is enabled in Google Cloud Console"
    )
    assert items[0]["id"].get("videoId"), "First result is missing videoId"
