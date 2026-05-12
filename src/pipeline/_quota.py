"""Shared quota-exhaustion detection and retry sentinel errors for the Gemini pipeline.

Extracted here so both src/pipeline/run.py and src/pipeline/backfill.py can
import them without pulling in each other's heavy transitive dependencies
(run.py imports fetch.py → hackernews.py → trafilatura, etc.).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_QUOTA_METRIC_TOKEN = "generate_content_free_tier_requests"
_QUOTA_PERDAY_TOKEN = "generaterequestsperday"
_QUOTA_METRIC_PHRASE = "quota exceeded for metric"


class NonRetryableEnrichError(Exception):
    """Wrap non-transport enrich errors so with_backoff won't retry them.

    Raised when enrich() throws a programming/runtime error that is
    not a Gemini transport condition (ClientError/ServerError).
    """


class QuotaExhaustedEnrichError(Exception):
    """Signal that Gemini free-tier quota is exhausted for this run."""


class ModelNotFoundEnrichError(Exception):
    """Signal that the current model ID is invalid (HTTP 404) — advance the cascade."""


def is_quota_exhausted_error(exc: Exception) -> bool:
    """Return True when a Gemini transport error indicates quota exhaustion."""
    code = getattr(exc, "code", None)
    status_code = getattr(exc, "status_code", None)
    if (code is not None and code != 429) or (status_code is not None and status_code != 429):
        return False

    details = getattr(exc, "details", None)
    if isinstance(details, list):
        for entry in details:
            if not isinstance(entry, dict):
                continue
            if entry.get("@type") != "type.googleapis.com/google.rpc.QuotaFailure":
                continue
            for violation in entry.get("violations", []):
                if not isinstance(violation, dict):
                    continue
                metric = violation.get("quotaMetric", "").lower()
                quota_id = violation.get("quotaId", "").lower()
                if _QUOTA_METRIC_TOKEN in metric or _QUOTA_PERDAY_TOKEN in quota_id:
                    return True

    text = str(exc).lower()
    return (
        _QUOTA_METRIC_TOKEN in text or _QUOTA_PERDAY_TOKEN in text or _QUOTA_METRIC_PHRASE in text
    )


def is_model_not_found_error(exc: Exception) -> bool:
    """Return True when a Gemini transport error indicates the model ID is invalid (404)."""
    code = getattr(exc, "code", None)
    status_code = getattr(exc, "status_code", None)
    return code == 404 or status_code == 404


def is_rate_limited(exc: Exception) -> bool:
    """Return True for any HTTP 429 response, regardless of quota-metric details."""
    code = getattr(exc, "code", None)
    status_code = getattr(exc, "status_code", None)
    return code == 429 or status_code == 429


def log_quota_exhausted(item_id: str, remaining: int) -> None:
    logger.warning(
        "Gemini quota exhausted while enriching %r; skipping AI enrichment for remaining %d item(s)",
        item_id,
        remaining,
    )
