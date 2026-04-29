"""Hugging Face model releases fetcher — trend pipeline only.

Fetches recently-updated text-generation and related models from the
Hugging Face Hub public API. No auth required.
Source class: primary (model cards represent direct capability evidence).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_API_URL = "https://huggingface.co/api/models"

# Tasks that signal LLM / foundation model activity
_RELEVANT_TASKS = {
    "text-generation",
    "text2text-generation",
    "question-answering",
    "summarization",
    "translation",
    "conversational",
    "fill-mask",
    "image-to-text",
    "visual-question-answering",
}

_HEADERS = {
    "User-Agent": "latest-developments-bot/1.0",
    "Accept": "application/json",
}

_MAX_CONTENT_CHARS = 6_000


class HuggingFaceFetcher:
    """Fetch recently-updated models from the Hugging Face Hub."""

    def __init__(self, max_models: int = 50, min_downloads: int = 100) -> None:
        self._max_models = max_models
        self._min_downloads = min_downloads

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        try:
            return with_backoff(lambda: self._fetch_models(already_processed))
        except Exception as exc:
            logger.warning("HuggingFace fetch failed: %s", exc)
            return []

    def _fetch_models(self, already_processed: set[str]) -> list[FetchedItem]:
        params = {
            "sort": "lastModified",
            "direction": -1,
            "limit": min(self._max_models * 3, 200),  # over-fetch to allow filtering
            "full": "true",
        }
        response = httpx.get(_API_URL, params=params, headers=_HEADERS, timeout=30)
        response.raise_for_status()

        models = response.json()
        if not isinstance(models, list):
            logger.warning("HuggingFace API returned unexpected format")
            return []

        items: list[FetchedItem] = []
        for model in models:
            if len(items) >= self._max_models:
                break

            model_id = model.get("modelId") or model.get("id", "")
            if not model_id:
                continue

            # Skip irrelevant tasks
            pipeline_tag = model.get("pipeline_tag", "")
            if pipeline_tag and pipeline_tag not in _RELEVANT_TASKS:
                continue

            # Skip low-download models (noise reduction)
            downloads = model.get("downloads", 0) or 0
            if downloads < self._min_downloads:
                continue

            url = f"https://huggingface.co/{model_id}"
            norm_url = url.rstrip("/")
            item_id = f"hf:{model_id}"

            if norm_url in already_processed or item_id in already_processed:
                continue

            # Build a content summary from available metadata
            tags = model.get("tags") or []
            likes = model.get("likes", 0) or 0
            card_data = model.get("cardData") or {}
            description = card_data.get("model_summary", "") or ""

            content_parts = [f"Model: {model_id}"]
            if pipeline_tag:
                content_parts.append(f"Task: {pipeline_tag}")
            if tags:
                content_parts.append(f"Tags: {', '.join(tags[:10])}")
            if downloads:
                content_parts.append(f"Downloads: {downloads:,}")
            if likes:
                content_parts.append(f"Likes: {likes:,}")
            if description:
                content_parts.append(f"Description: {description}")

            content = "\n".join(content_parts)[:_MAX_CONTENT_CHARS]

            # Parse lastModified date
            pub_date: datetime | None = None
            last_modified = model.get("lastModified") or model.get("updatedAt")
            if last_modified:
                try:
                    pub_date = datetime.fromisoformat(
                        last_modified.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            # Title: use model_id, prettified
            title = model_id.split("/")[-1].replace("-", " ").replace("_", " ").title()
            if "/" in model_id:
                org = model_id.split("/")[0]
                title = f"{title} ({org})"

            items.append(FetchedItem(
                id=item_id,
                title=title,
                url=norm_url,
                content=content,
                source_name="Hugging Face",
                source_type="HuggingFace",
                source_class="primary",
                published=pub_date,
            ))

        logger.info("Hugging Face: %d relevant models fetched", len(items))
        return items
