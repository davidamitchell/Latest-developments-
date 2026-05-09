"""Backfill AI enrichment for ProcessedItems where theme is missing.

CLI: python -m src.pipeline.backfill [--all] [--date YYYY-MM-DD] [--dry-run] [--debug]

Reads data/processed/*.jsonl, finds items with theme == "", and re-runs the
combined AI enrich stage on them. Updates files in-place.

Use --all to scan all processed files (default: today only).
Use --date to target a specific date.
Use --dry-run to report counts without writing changes.

This is an ops tool for recovering from periods when GEMINI_API_KEY was absent
or when gemini-2.5-flash thinking tokens exhausted the max_output_tokens budget
(fixed in cb6dfe0 via thinking_budget=0).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv()
except ImportError:
    pass

from src.logger import setup_logging
from src.models import ProcessedItem, read_processed_jsonl, write_processed_jsonl
from src.retry import with_backoff

logger = logging.getLogger(__name__)

_PROCESSED_DIR = Path("data/processed")


class _NullRateLimiter:
    """No-op rate limiter used in tests and dry-run mode."""

    def wait(self) -> None:
        pass


def enrich(item: ProcessedItem, client: object, max_output_tokens: int = 500):
    """Thin wrapper around stages.enrich.enrich; imported lazily to avoid triggering
    google.genai at module load time (which requires the cryptography C extension).
    Module-level name so tests can patch src.pipeline.backfill.enrich directly.
    """
    from src.pipeline.stages.enrich import enrich as _enrich  # noqa: PLC0415

    return _enrich(item, client, max_output_tokens=max_output_tokens)  # type: ignore[arg-type]


def backfill_file(
    path: Path,
    client: object,
    rate_limiter: object,
    max_output_tokens: int,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Enrich items with theme == '' in a single processed file.

    Returns (enriched_count, failed_count).  When dry_run is True, counts
    are computed but the file is not written.
    """
    items = read_processed_jsonl(path)
    unenriched = [i for i in items if not i.theme]

    if not unenriched:
        return 0, 0

    logger.info(
        "%s: %d unenriched item(s) of %d total", path.name, len(unenriched), len(items)
    )

    if dry_run:
        logger.info("Dry run — skipping enrichment calls for %s", path.name)
        return len(unenriched), 0

    item_map: dict[str, ProcessedItem] = {i.id: i for i in items}
    enriched_count = 0
    failed_count = 0
    quota_exhausted = False

    from src.pipeline._quota import (  # noqa: I001, PLC0415
        NonRetryableEnrichError as _NonRetryableEnrichError,
        QuotaExhaustedEnrichError as _QuotaExhaustedEnrichError,
        is_quota_exhausted_error as _is_quota_exhausted_error,
        log_quota_exhausted as _log_quota_exhausted,
    )

    for idx, item in enumerate(unenriched):
        if quota_exhausted:
            failed_count += 1
            continue

        rate_limiter.wait()  # type: ignore[union-attr]

        def _make_attempt(current: ProcessedItem = item):
            def _attempt():
                try:
                    return enrich(current, client, max_output_tokens=max_output_tokens)  # type: ignore[arg-type]
                except Exception as exc:
                    # Pass quota-sentinel through so the outer handler can stop the batch.
                    if isinstance(exc, _QuotaExhaustedEnrichError):
                        raise
                    # Only classify as a Gemini transport error if the exception
                    # originated from google.genai — avoids importing the C-extension
                    # backed google.genai.errors for non-Gemini exceptions (e.g.
                    # AttributeError from a programming mistake in enrich()).
                    if type(exc).__module__.startswith("google.genai"):
                        from google.genai.errors import (  # noqa: PLC0415, B023
                            ClientError,
                            ServerError,
                        )

                        if isinstance(exc, (ClientError, ServerError)):  # noqa: B023
                            if _is_quota_exhausted_error(exc):
                                raise _QuotaExhaustedEnrichError from exc
                            raise  # let with_backoff retry ServerError / non-quota ClientError
                    raise _NonRetryableEnrichError from exc

            return _attempt

        pre_enrich = item
        try:
            enriched_item, ok = with_backoff(
                _make_attempt(item),
                max_attempts=3,
                base_delay=60.0,
                label=f"backfill:{item.id}",
                no_retry=(_NonRetryableEnrichError, _QuotaExhaustedEnrichError),
            )
        except _QuotaExhaustedEnrichError:
            enriched_item = pre_enrich
            ok = False
            quota_exhausted = True
            remaining = len(unenriched) - idx - 1
            _log_quota_exhausted(item.id, remaining)
        except RuntimeError as exc:
            cause = exc.__cause__
            cause_module = type(cause).__module__ if cause is not None else ""
            is_gemini_transport = False
            if cause_module.startswith("google.genai"):
                from google.genai.errors import ClientError, ServerError  # noqa: PLC0415

                is_gemini_transport = isinstance(cause, (ClientError, ServerError))

            if is_gemini_transport:
                enriched_item = pre_enrich
                if _is_quota_exhausted_error(exc.__cause__):
                    quota_exhausted = True
                    remaining = len(unenriched) - idx - 1
                    _log_quota_exhausted(item.id, remaining)
                else:
                    logger.warning(
                        "AI enrichment failed for %r after retries: %s",
                        item.id,
                        exc.__cause__,
                    )
                ok = False
            else:
                raise
        except _NonRetryableEnrichError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

        if ok:
            item_map[item.id] = enriched_item
            enriched_count += 1
            logger.debug("Enriched %r → theme=%r", item.id, enriched_item.theme)
        else:
            failed_count += 1
            logger.warning("Enrichment returned ok=False for %r — keeping defaults", item.id)

    # Preserve original insertion order
    ordered = [item_map[i.id] for i in items]
    write_processed_jsonl(ordered, path)
    logger.info(
        "%s: enriched %d, failed %d", path.name, enriched_count, failed_count
    )
    return enriched_count, failed_count


def backfill_all(
    processed_dir: Path,
    client: object,
    rate_limiter: object,
    max_output_tokens: int,
    dry_run: bool = False,
    date_filter: str | None = None,
) -> tuple[int, int, int]:
    """Backfill all (or a single date's) processed files.

    Returns (total_enriched, total_failed, files_updated).
    files_updated counts files where at least one item was enriched (or would
    be enriched in dry_run mode).
    """
    if date_filter:
        paths = [processed_dir / f"{date_filter}.jsonl"]
        paths = [p for p in paths if p.exists()]
    else:
        paths = sorted(processed_dir.glob("*.jsonl"))

    if not paths:
        logger.warning("No processed files found in %s", processed_dir)
        return 0, 0, 0

    total_enriched = 0
    total_failed = 0
    files_updated = 0

    for path in paths:
        enriched, failed = backfill_file(
            path, client, rate_limiter, max_output_tokens, dry_run=dry_run
        )
        total_enriched += enriched
        total_failed += failed
        if enriched > 0:
            files_updated += 1

    return total_enriched, total_failed, files_updated


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Re-enrich ProcessedItems where theme == '' using the Gemini API."
    )
    p.add_argument(
        "--all",
        action="store_true",
        dest="all_dates",
        help="Scan all dates in data/processed/ (default: today only)",
    )
    p.add_argument("--date", default=None, help="Target a specific date (YYYY-MM-DD)")
    p.add_argument("--dry-run", action="store_true", help="Report counts without writing files")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    from src.config import load_config

    cfg = load_config()
    setup_logging(debug=args.debug, log_file=cfg.logging.log_file)

    api_key = os.environ.get("GEMINI_API_KEY") or None
    if not api_key:
        logger.error("GEMINI_API_KEY not set — cannot run backfill without an API key")
        return 1

    from src.pipeline.run import _make_gemini_client, _RateLimiter

    client = _make_gemini_client(api_key)
    rate_limiter = _RateLimiter(rpm=cfg.pipeline.gemini_rpm)

    if args.date:
        date_filter = args.date
    elif args.all_dates:
        date_filter = None
    else:
        date_filter = datetime.now(UTC).strftime("%Y-%m-%d")

    dry_label = " (dry run)" if args.dry_run else ""
    logger.info(
        "Backfill%s — target: %s",
        dry_label,
        date_filter or "all dates",
    )

    enriched, failed, files = backfill_all(
        _PROCESSED_DIR,
        client,
        rate_limiter,
        max_output_tokens=cfg.pipeline.enrich_max_output_tokens,
        dry_run=args.dry_run,
        date_filter=date_filter,
    )

    logger.info(
        "Backfill complete%s — %d enriched, %d failed, %d file(s) updated",
        dry_label,
        enriched,
        failed,
        files,
    )

    if failed and enriched + failed > 0 and failed / (enriched + failed) > 0.5:
        logger.error("More than 50%% of enrichment attempts failed — check Gemini quota/key")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
