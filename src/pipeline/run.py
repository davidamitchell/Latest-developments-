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
import json
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

from src.fetchers import FetchedItem
from src.logger import setup_logging
from src.models import ProcessedItem, read_processed_jsonl, write_processed_jsonl
from src.pipeline.fetch import read_raw_jsonl
from src.pipeline.stages.clean import clean
from src.pipeline.stages.concept_extraction import extract_concepts
from src.pipeline.stages.credibility_scoring import score_credibility
from src.pipeline.stages.hype_scoring import score_hype
from src.pipeline.stages.ingest import ingest
from src.pipeline.stages.media_id import identify_marketing
from src.pipeline.stages.summary_extraction import extract_summary
from src.pipeline.stages.theme_classification import classify_theme

logger = logging.getLogger(__name__)

_RAW_DIR = Path("data/raw")
_PROCESSED_DIR = Path("data/processed")


def _make_gemini_client(api_key: str):
    """Construct and return a Gemini client."""
    from google import genai
    return genai.Client(api_key=api_key)


def process(
    items: list[FetchedItem],
    gemini_api_key: str | None,
    fetch_date: str,
) -> list[ProcessedItem]:
    """Run all 8 pipeline stages over items; return ProcessedItem list.

    When gemini_api_key is None, AI stages (3–6) are skipped gracefully and
    their fields remain at defaults. Non-AI stages always run.
    """
    if not items:
        return []

    client = _make_gemini_client(gemini_api_key) if gemini_api_key else None
    results: list[ProcessedItem] = []

    for fetched in items:
        # Stage 1 — Ingest
        processed = ingest(fetched, fetch_date=fetch_date)

        # Stage 2 — Clean
        processed = clean(processed, raw_content=fetched.content)

        if client is not None:
            # Stage 3 — Concept Extraction
            processed = extract_concepts(processed, client)

            # Stage 4 — Theme Classification
            processed = classify_theme(processed, client)

            # Stage 5 — Summary Extraction
            processed = extract_summary(processed, client)

            # Stage 6 — Media / Marketing Identification
            processed = identify_marketing(processed, client)

        # Stage 7 — Hype Scoring (deterministic)
        processed = score_hype(processed)

        # Stage 8 — Credibility Scoring (deterministic)
        processed = score_credibility(processed)

        results.append(processed)

    logger.info("Processed %d item(s)", len(results))
    return results


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

    api_key = os.environ.get("GEMINI_API_KEY") or None
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — AI stages (3–6) will be skipped")

    processed = process(items, gemini_api_key=api_key, fetch_date=today)
    write_processed_jsonl(processed, out_path)
    logger.info("Processing complete — %d item(s) written to %s", len(processed), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
