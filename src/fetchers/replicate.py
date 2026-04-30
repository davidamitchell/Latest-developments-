"""Replicate model fetcher — trend pipeline only.

Fetches popular public models from the Replicate API, ordered by run count.
No authentication required for public models.
Source class: operator (vendor-hosted deployment reflects real production usage).
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime

import httpx

from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_API_URL = "https://api.replicate.com/v1/models"

_HEADERS = {
    "User-Agent": "latest-developments-bot/1.0",
    "Accept": "application/json",
}

_MAX_CONTENT_CHARS = 6_000


class ReplicateFetcher:
    """Fetch popular public models from Replicate."""

    def __init__(self, limit: int = 20) -> None:
        self._limit = limit

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        try:
            return with_backoff(lambda: self._fetch_models(already_processed))
        except Exception as exc:
            logger.warning("Replicate fetch failed: %s", exc)
            return []

    def _fetch_models(self, already_processed: set[str]) -> list[FetchedItem]:
        params: dict[str, str | int] = {"order": "run_count"}
        response = httpx.get(_API_URL, params=params, headers=_HEADERS, timeout=30)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            logger.warning("Replicate API returned unexpected format")
            return []

        results = data.get("results", [])
        if not isinstance(results, list):
            logger.warning("Replicate API: 'results' field missing or not a list")
            return []

        items: list[FetchedItem] = []
        for model in results:
            if len(items) >= self._limit:
                break
            try:
                item = self._parse_model(model, already_processed)
            except Exception as exc:
                logger.warning("Skipping Replicate model due to error: %s", exc)
                continue
            if item is not None:
                items.append(item)

        logger.info("Replicate: %d model(s) fetched", len(items))
        return items

    def _parse_model(
        self,
        model: dict,
        already_processed: set[str],
    ) -> FetchedItem | None:
        owner = model.get("owner", "") or ""
        name = model.get("name", "") or ""
        if not owner or not name:
            return None

        url = model.get("url", "") or f"https://replicate.com/{owner}/{name}"
        norm_url = url.rstrip("/")

        if norm_url in already_processed:
            return None

        title = f"{name} ({owner})"

        description = model.get("description", "") or ""
        run_count = model.get("run_count", 0) or 0

        content_parts = [f"Model: {owner}/{name}"]
        if description:
            content_parts.append(f"Description: {description}")
        if run_count:
            content_parts.append(f"Run count: {run_count:,}")
        visibility = model.get("visibility", "") or ""
        if visibility:
            content_parts.append(f"Visibility: {visibility}")

        content = "\n".join(content_parts)[:_MAX_CONTENT_CHARS]

        pub_date: datetime | None = None
        created_at = model.get("created_at", "") or ""
        if created_at:
            with contextlib.suppress(ValueError):
                pub_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        return FetchedItem(
            id=norm_url,
            title=title,
            url=norm_url,
            content=content,
            source_name="Replicate",
            source_type="Replicate",
            source_class="operator",
            published=pub_date,
        )
