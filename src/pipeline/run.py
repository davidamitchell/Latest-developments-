"""Processing entrypoint — Concern 2: PROCESSING.

CLI: python -m src.pipeline.run

Reads data/raw/YYYY-MM-DD.jsonl (FetchedItem records), runs all 8 pipeline
stages, and writes data/processed/YYYY-MM-DD.jsonl (ProcessedItem records).

Stages 3–6 require a Gemini API key (GEMINI_API_KEY env var).
When the key is absent those stages are skipped and their fields remain at
default values — the pipeline still completes and writes output.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv()
except ImportError:
    pass

from src.fetchers import FetchedItem
from src.logger import setup_logging
from src.models import ProcessedItem, read_processed_jsonl, write_processed_jsonl
from src.pipeline._quota import (
    NonRetryableEnrichError as _NonRetryableEnrichError,
)
from src.pipeline._quota import (
    QuotaExhaustedEnrichError as _QuotaExhaustedEnrichError,
)
from src.pipeline._quota import (
    is_quota_exhausted_error as _is_quota_exhausted_error,
)
from src.pipeline._quota import (
    log_quota_exhausted as _log_quota_exhausted,
)
from src.pipeline.fetch import read_raw_jsonl
from src.pipeline.stages.clean import clean
from src.pipeline.stages.credibility_scoring import score_credibility
from src.pipeline.stages.enrich import enrich
from src.pipeline.stages.hype_scoring import score_hype
from src.pipeline.stages.ingest import ingest
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_RAW_DIR = Path("data/raw")
_PROCESSED_DIR = Path("data/processed")


def _remaining_item_count(total: int, idx: int) -> int:
    return total - idx - 1


class _HeaderCapturingClient(httpx.Client):
    """httpx.Client subclass that records x-ratelimit-* headers from each response.

    Passed to genai.Client via HttpOptions so the rate limiter can read real
    quota state without hardcoding per-model limits.
    """

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("follow_redirects", True)
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.ratelimit_headers: dict[str, str] = {}

    def send(self, request: httpx.Request, **kwargs: object) -> httpx.Response:  # type: ignore[override]
        response = super().send(request, **kwargs)  # type: ignore[arg-type]
        self.ratelimit_headers = {
            k.lower(): v
            for k, v in response.headers.items()
            if k.lower().startswith("x-ratelimit")
        }
        return response


def _parse_reset_seconds(reset_str: str) -> float | None:
    """Parse x-ratelimit-reset-requests into seconds until reset.

    Handles: bare float ("60"), duration with suffix ("4s"), ISO-8601 timestamp.
    Returns None when the string is empty or unparseable.
    """
    s = reset_str.strip()
    if not s:
        return None
    if s.endswith("s"):
        try:
            return max(float(s[:-1]), 0.0)
        except ValueError:
            pass
    try:
        return max(float(s), 0.0)
    except ValueError:
        pass
    try:
        from datetime import timezone
        reset_dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return max((reset_dt - datetime.now(timezone.utc)).total_seconds(), 0.0)
    except (ValueError, OverflowError):
        pass
    return None


class _RateLimiter:
    """Adaptive pacer for Gemini API calls.

    Uses a fixed minimum interval (60 / rpm) as a floor. After each API call
    the captured x-ratelimit-* response headers are inspected:
      - remaining == 0  → wait for the reset window before the next call
      - remaining <= 3  → triple the interval to coast to the window boundary
      - remaining > 3   → restore the minimum interval

    When headers are absent (e.g. network error, mocked client in tests) the
    fixed interval is used unchanged.
    """

    def __init__(self, rpm: int = 15, http_client: _HeaderCapturingClient | None = None) -> None:
        self._min_interval = 60.0 / rpm
        self._interval = self._min_interval
        self._last: float = 0.0
        self._http_client = http_client

    def _update_from_headers(self, headers: dict[str, str]) -> None:
        remaining_str = headers.get("x-ratelimit-remaining-requests")
        if not remaining_str:
            return
        try:
            remaining = int(remaining_str)
        except ValueError:
            logger.debug("Rate limiter: non-integer x-ratelimit-remaining-requests %r", remaining_str)
            return

        if remaining <= 0:
            reset_str = headers.get("x-ratelimit-reset-requests", "")
            wait = _parse_reset_seconds(reset_str) or 60.0
            logger.warning("Rate limiter: quota window exhausted — waiting %.1fs for reset", wait)
            self._interval = wait
        elif remaining <= 3:
            self._interval = max(self._min_interval * 3, 20.0)
            logger.debug(
                "Rate limiter: %d request(s) remaining — slowing to %.1fs interval",
                remaining, self._interval,
            )
        else:
            self._interval = self._min_interval

    def wait(self) -> None:
        if self._http_client and self._http_client.ratelimit_headers:
            self._update_from_headers(self._http_client.ratelimit_headers)
        now = time.monotonic()
        gap = self._interval - (now - self._last)
        if gap > 0:
            logger.debug("Rate limiter: waiting %.1fs before next Gemini call", gap)
            time.sleep(gap)
        self._last = time.monotonic()


def _make_gemini_client(api_key: str) -> tuple[object, _HeaderCapturingClient]:
    """Construct a Gemini client wired to a header-capturing httpx transport.

    Returns (genai_client, http_client). Pass http_client to _RateLimiter so it
    can read x-ratelimit-* headers and adapt pacing without hardcoded per-model limits.

    Retry policy is handled at the application level in process() via
    src.retry.with_backoff so Gemini retryDelay hints can be honoured.
    """
    from google import genai
    from google.genai import types

    http_client = _HeaderCapturingClient()
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(httpx_client=http_client),
    )
    return client, http_client


def process(
    items: list[FetchedItem],
    gemini_api_key: str | None,
    fetch_date: str,
    rpm: int = 15,
    enrich_max_output_tokens: int = 500,
    gemini_model: str = "gemini-2.0-flash",
) -> tuple[list[ProcessedItem], int]:
    """Run all 8 pipeline stages over items; return (results, ai_failures).

    When gemini_api_key is None, AI stages (3–6) are skipped gracefully and
    their fields remain at defaults. Non-AI stages always run.
    ai_failures counts items where the combined Gemini call raised an exception.

    rpm, enrich_max_output_tokens, and gemini_model can be overridden via pipeline config.
    """
    if not items:
        return [], 0

    if gemini_api_key:
        client, http_client = _make_gemini_client(gemini_api_key)
        rate_limiter = _RateLimiter(rpm=rpm, http_client=http_client)
    else:
        client = None
        rate_limiter = None
    ai_disabled_for_quota = False
    results: list[ProcessedItem] = []
    ai_failures = 0

    for idx, fetched in enumerate(items):
        # Stage 1 — Ingest
        processed = ingest(fetched, fetch_date=fetch_date)

        # Stage 2 — Clean
        processed = clean(processed, raw_content=fetched.content)

        if client is not None and not ai_disabled_for_quota:
            from google.genai.errors import ClientError, ServerError

            def _make_enrich_once(current: ProcessedItem):
                def _enrich_once() -> tuple[ProcessedItem, bool]:
                    try:
                        return enrich(current, client, max_output_tokens=enrich_max_output_tokens, model=gemini_model)
                    except (ClientError, ServerError) as exc:
                        if _is_quota_exhausted_error(exc):
                            raise _QuotaExhaustedEnrichError from exc
                        raise
                    except Exception as exc:
                        raise _NonRetryableEnrichError from exc

                return _enrich_once

            # Pace to ≤rpm RPM before each Gemini call to stay under the free-tier quota.
            rate_limiter.wait()  # type: ignore[union-attr]
            # Stages 3–6 — combined AI enrichment (1 Gemini call per item)
            pre_enrich = processed
            try:
                processed, ok = with_backoff(
                    _make_enrich_once(processed),
                    max_attempts=3,
                    base_delay=60.0,
                    label=f"enrich:{processed.id}",
                    no_retry=(_NonRetryableEnrichError, _QuotaExhaustedEnrichError),
                )
            except _QuotaExhaustedEnrichError:
                processed = pre_enrich
                ok = False
                ai_disabled_for_quota = True
                remaining = _remaining_item_count(len(items), idx)
                _log_quota_exhausted(processed.id, remaining)
            except RuntimeError as exc:
                if isinstance(exc.__cause__, (ClientError, ServerError)):
                    processed = pre_enrich
                    if _is_quota_exhausted_error(exc.__cause__):
                        ai_disabled_for_quota = True
                        remaining = _remaining_item_count(len(items), idx)
                        _log_quota_exhausted(processed.id, remaining)
                    else:
                        logger.warning(
                            "AI enrichment failed for %r after retries: %s",
                            processed.id,
                            exc.__cause__,
                        )
                    ok = False
                else:
                    raise
            except _NonRetryableEnrichError as exc:
                raise exc.__cause__ from None
            if not ok:
                ai_failures += 1

        # Stage 7 — Hype Scoring (deterministic)
        processed = score_hype(processed)

        # Stage 8 — Credibility Scoring (deterministic)
        processed = score_credibility(processed)

        results.append(processed)

    if client is not None and items:
        failure_rate = ai_failures / len(items)
        if ai_failures:
            logger.warning(
                "AI enrichment failed for %d/%d items (%.0f%%)",
                ai_failures,
                len(items),
                failure_rate * 100,
            )
        else:
            logger.info("AI enrichment succeeded for all %d items", len(items))

    logger.info("Processed %d item(s)", len(results))
    return results, ai_failures


def _merge_and_write(
    out_path: Path,
    new_items: list[ProcessedItem],
) -> list[ProcessedItem]:
    """Merge new_items with any items already in out_path; write and return merged list."""
    existing = read_processed_jsonl(out_path)
    existing_ids = {item.id for item in existing}
    merged = existing + [item for item in new_items if item.id not in existing_ids]
    write_processed_jsonl(merged, out_path)
    return merged


def _exit_code(ai_failures: int, total: int, api_key_present: bool) -> int:
    """Return 2 if AI failure rate exceeds 50%, else 0."""
    if api_key_present and total and ai_failures / total > 0.5:
        logger.error(
            "AI enrichment failed for >50%% of items (%d/%d) — check Gemini quota/key",
            ai_failures,
            total,
        )
        return 2
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Process raw data → data/processed/YYYY-MM-DD.jsonl")
    p.add_argument("--date", default=None, help="Override fetch date (YYYY-MM-DD)")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    from src.config import load_config

    cfg = load_config()
    setup_logging(debug=args.debug, log_file=cfg.logging.log_file)

    today = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    raw_path = _RAW_DIR / f"{today}.jsonl"
    out_path = _PROCESSED_DIR / f"{today}.jsonl"

    logger.info("Processing run for %s — input: %s", today, raw_path)

    items = read_raw_jsonl(raw_path)
    if not items:
        logger.info(
            "No raw items found for %s — preserving existing processed file if present", today
        )
        merged = _merge_and_write(out_path, [])
        logger.info(
            "Processing complete — %d new item(s) added; %d total in %s",
            0,
            len(merged),
            out_path,
        )
        return 0

    # GEMINI_API_KEY is intentionally optional: when absent, AI stages (3–6)
    # are skipped and pipeline output uses default field values.  This allows
    # the pipeline to complete without an API key — useful for testing and for
    # runs where enrichment is not required.
    api_key = os.environ.get("GEMINI_API_KEY") or None
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — AI stages (3–6) will be skipped")

    processed, ai_failures = process(
        items,
        gemini_api_key=api_key,
        fetch_date=today,
        rpm=cfg.pipeline.gemini_rpm,
        enrich_max_output_tokens=cfg.pipeline.enrich_max_output_tokens,
        gemini_model=cfg.pipeline.gemini_model,
    )

    merged = _merge_and_write(out_path, processed)
    logger.info(
        "Processing complete — %d new item(s) added; %d total in %s",
        len(processed),
        len(merged),
        out_path,
    )

    return _exit_code(ai_failures, len(items), bool(api_key))


if __name__ == "__main__":
    sys.exit(main())
