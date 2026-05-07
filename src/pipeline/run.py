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

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]
    load_dotenv()
except ImportError:
    pass

from src.fetchers import FetchedItem
from src.logger import setup_logging
from src.models import ProcessedItem, read_processed_jsonl, write_processed_jsonl
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


class _NonRetryableEnrichError(Exception):
    """Wrap non-transport enrich errors so with_backoff won't retry them.

    Raised when enrich() throws a programming/runtime error that is
    not a Gemini transport condition (ClientError/ServerError).
    """


class _RateLimiter:
    """Token-bucket pacer for the Gemini free tier (default: 5 RPM).

    Calling .wait() before each API request ensures the pipeline never fires
    more than `rpm` requests per 60-second window, keeping us under the
    GenerateRequestsPerMinutePerProjectPerModel-FreeTier quota.
    """

    def __init__(self, rpm: int = 5) -> None:
        self._interval = 60.0 / rpm
        self._last: float = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        gap = self._interval - (now - self._last)
        if gap > 0:
            logger.debug("Rate limiter: waiting %.1fs before next Gemini call", gap)
            time.sleep(gap)
        self._last = time.monotonic()


def _make_gemini_client(api_key: str):
    """Construct and return a Gemini client.

    Retry policy is handled at the application level in process() via
    src.retry.with_backoff so Gemini retryDelay hints can be honoured.
    """
    from google import genai
    return genai.Client(api_key=api_key)


def process(
    items: list[FetchedItem],
    gemini_api_key: str | None,
    fetch_date: str,
    rpm: int = 5,
    enrich_max_output_tokens: int = 500,
) -> tuple[list[ProcessedItem], int]:
    """Run all 8 pipeline stages over items; return (results, ai_failures).

    When gemini_api_key is None, AI stages (3–6) are skipped gracefully and
    their fields remain at defaults. Non-AI stages always run.
    ai_failures counts items where the combined Gemini call raised an exception.

    rpm and enrich_max_output_tokens can be overridden via pipeline config.
    """
    if not items:
        return [], 0

    client = _make_gemini_client(gemini_api_key) if gemini_api_key else None
    rate_limiter = _RateLimiter(rpm=rpm) if client is not None else None
    results: list[ProcessedItem] = []
    ai_failures = 0

    for fetched in items:
        # Stage 1 — Ingest
        processed = ingest(fetched, fetch_date=fetch_date)

        # Stage 2 — Clean
        processed = clean(processed, raw_content=fetched.content)

        if client is not None:
            from google.genai.errors import ClientError, ServerError

            def _make_enrich_once(current: ProcessedItem):
                def _enrich_once() -> tuple[ProcessedItem, bool]:
                    try:
                        return enrich(current, client, max_output_tokens=enrich_max_output_tokens)
                    except (ClientError, ServerError):
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
                    no_retry=(_NonRetryableEnrichError,),
                )
            except RuntimeError as exc:
                if isinstance(exc.__cause__, (ClientError, ServerError)):
                    processed = pre_enrich
                    logger.warning("AI enrichment failed for %r after retries: %s", processed.id, exc.__cause__)
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
                ai_failures, len(items), failure_rate * 100,
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
            ai_failures, total,
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
        logger.info("No raw items found for %s — writing empty processed file", today)
        write_processed_jsonl([], out_path)
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
    )

    merged = _merge_and_write(out_path, processed)
    logger.info(
        "Processing complete — %d new item(s) added; %d total in %s",
        len(processed), len(merged), out_path,
    )

    return _exit_code(ai_failures, len(items), bool(api_key))


if __name__ == "__main__":
    sys.exit(main())
