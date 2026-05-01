"""OpenRouter model pricing fetcher — trend pipeline only.

Fetches the public OpenRouter model catalogue from
  https://openrouter.ai/api/v1/models
No authentication required for public model metadata.

Each model is surfaced as a FetchedItem whose content encodes the pricing
snapshot (price_input, price_output, context_window). Items are classified
as source_class="market" and evidence_type="pricing" so they feed the
pricing / inference-cost signal in the trend pipeline.

Deduplication key: the model ``id`` field (e.g. "openai/gpt-4o").
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from src.fetchers import FetchedItem
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/models"

_HEADERS = {
    "User-Agent": "latest-developments-bot/1.0",
    "Accept": "application/json",
}

_MAX_CONTENT_CHARS = 4_000


class OpenRouterFetcher:
    """Fetch model pricing data from the OpenRouter public catalogue."""

    def __init__(self, limit: int = 100) -> None:
        self._limit = limit

    def fetch(self, already_processed: set[str]) -> list[FetchedItem]:
        try:
            return with_backoff(lambda: self._fetch_models(already_processed))
        except Exception as exc:
            logger.warning("OpenRouter fetch failed: %s", exc)
            return []

    def _fetch_models(self, already_processed: set[str]) -> list[FetchedItem]:
        response = httpx.get(_API_URL, headers=_HEADERS, timeout=30)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            logger.warning("OpenRouter API returned unexpected format")
            return []

        models = data.get("data", [])
        if not isinstance(models, list):
            logger.warning("OpenRouter API: 'data' field missing or not a list")
            return []

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        items: list[FetchedItem] = []

        for model in models[: self._limit]:
            model_id: str = model.get("id", "")
            if not model_id:
                continue

            # Deduplication key includes today's date so we take a fresh snapshot
            # each day (prices change daily).  The key does NOT include a content
            # hash, so if two runs happen on the same day the second is skipped.
            # Stale keys in processed.json naturally age out because the date
            # component will not match future run dates — no explicit cleanup needed.
            dedup_key = f"openrouter:{model_id}:{today}"
            if dedup_key in already_processed:
                continue

            name: str = model.get("name") or model_id
            description: str = (model.get("description") or "").strip()

            # Extract pricing fields (OpenRouter returns as strings in USD/token)
            pricing: dict = model.get("pricing") or {}
            price_prompt = pricing.get("prompt", "0")
            price_completion = pricing.get("completion", "0")
            context_length: int = model.get("context_length") or 0

            # Format a human-readable pricing snapshot as the item content
            try:
                price_in_per_m = float(price_prompt) * 1_000_000
                price_out_per_m = float(price_completion) * 1_000_000
                pricing_line = (
                    f"Pricing: ${price_in_per_m:.4f}/M input tokens, "
                    f"${price_out_per_m:.4f}/M output tokens"
                )
            except (ValueError, TypeError):
                pricing_line = f"Pricing: prompt={price_prompt}, completion={price_completion}"

            content = (
                f"Model: {model_id}\n"
                f"Context window: {context_length:,} tokens\n"
                f"{pricing_line}\n"
                f"{description}"
            )[:_MAX_CONTENT_CHARS]

            url = f"https://openrouter.ai/models/{model_id}"

            items.append(
                FetchedItem(
                    id=dedup_key,
                    title=name,
                    url=url,
                    content=content,
                    source_name="OpenRouter",
                    published=datetime.now(UTC).replace(tzinfo=None),
                    source_type="API",
                    source_class="market",
                    evidence_type="pricing",
                )
            )

        logger.info("OpenRouter: %d new model pricing snapshot(s)", len(items))
        return items
