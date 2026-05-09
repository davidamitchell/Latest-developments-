"""Site build entrypoint — Concern 3B: SITE BUILD.

CLI: python -m src.site.build

Reads data/processed/*.jsonl (ProcessedItem records), converts them to the
(date, theme, source_class, source_name) tuples consumed by the existing
build_trend_metrics() function, computes TrendMetrics per theme, optionally
enriches with Gemini (cluster_themes), and writes docs/data/*.json.

This module must not import any fetcher or pipeline stage. It depends only on
Schema Contract B (ProcessedItem) and the existing trend computation modules.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv()
except ImportError:
    pass

from src.config import load_config
from src.logger import setup_logging
from src.models import CanonicalRecord, ProcessedItem, ThemeNode, TrendMetrics, read_processed_jsonl
from src.themes import cluster_themes, normalize_theme_name
from src.trends import (
    _load_existing_metrics,
    build_trend_metrics,
)

logger = logging.getLogger(__name__)

_PROCESSED_DIR = Path("data/processed")
_DOCS_DATA_DIR = Path("docs/data")

_VOLUME_WINDOW_DAYS = 14
_MIN_THEME_APPEARANCES = 2


def load_processed_items(
    data_dir: Path,
    window_days: int = 90,
) -> tuple[list[ProcessedItem], list[dict]]:
    """Load ProcessedItem records from data_dir/*.jsonl, returning (items, file_log).

    Filters out "hist-" prefixed items — these are artefacts from the legacy
    src/trends.py history-parsing pipeline and are not valid ProcessedItem
    records (they have empty URLs and single-word titles).

    Returns a tuple of:
      - items: valid ProcessedItem list
      - file_log: per-file audit dicts with keys file, total, valid, filtered_hist, themed
    """
    if not data_dir.exists():
        logger.debug("Processed data directory not found: %s", data_dir)
        return [], []

    all_items: list[ProcessedItem] = []
    file_log: list[dict] = []
    for jsonl_file in sorted(data_dir.glob("*.jsonl")):
        raw = read_processed_jsonl(jsonl_file)
        valid = [i for i in raw if not i.id.startswith("hist-")]
        filtered = len(raw) - len(valid)
        if filtered:
            logger.debug("Filtered %d hist- items from %s", filtered, jsonl_file.name)
        all_items.extend(valid)
        file_log.append(
            {
                "file": jsonl_file.name,
                "total": len(raw),
                "valid": len(valid),
                "filtered_hist": filtered,
                "themed": sum(1 for i in valid if i.theme),
            }
        )
        logger.debug("Loaded %d valid items from %s", len(valid), jsonl_file)

    hist_total = sum(f["filtered_hist"] for f in file_log)
    if hist_total:
        logger.info("Filtered %d legacy hist- items across all files", hist_total)
    logger.info("Loaded %d valid ProcessedItem records from %s", len(all_items), data_dir)
    return all_items, file_log


def items_to_entries(
    items: list[ProcessedItem],
) -> list[tuple[str, str, str, str]]:
    """Convert ProcessedItem list to (date_str, theme, source_class, source_name) tuples.

    Items with no theme assigned are skipped — the pipeline may not have run
    AI stages on all items (e.g. enrichment failure or missing API key).
    """
    entries: list[tuple[str, str, str, str]] = []
    for item in items:
        if not item.theme:
            continue
        theme = normalize_theme_name(item.theme)
        date_str = item.fetch_date or (
            item.published.strftime("%Y-%m-%d") if item.published else ""
        )
        if not date_str:
            continue
        entries.append((date_str, theme, item.source_class, item.source_name))
    return entries


def _build_source_list(
    items: list[ProcessedItem],
    entries: list[tuple[str, str, str, str]],
) -> list[dict]:
    """Build the per-source detail list for sources.json.

    Counts item_count from ALL items (not just themed entries) so that sources
    like arXiv or HuggingFace are visible even when AI enrichment hasn't run.
    Theme data is populated from entries (which only contains themed items).
    """
    per_source: dict[str, dict] = {}

    # Pass 1: count all items per source regardless of theme status
    for item in items:
        name = item.source_name
        date_str = item.fetch_date or (
            item.published.strftime("%Y-%m-%d") if item.published else ""
        )
        if name not in per_source:
            per_source[name] = {
                "name": name,
                "source_class": item.source_class,
                "item_count": 0,
                "themed_count": 0,
                "dates": set(),
                "theme_counts": Counter(),
            }
        per_source[name]["item_count"] += 1
        if date_str:
            per_source[name]["dates"].add(date_str)

    # Pass 2: augment with theme data from entries (themed items only)
    for _date_str, theme, _cls, name in entries:
        if name in per_source:
            per_source[name]["themed_count"] += 1
            per_source[name]["theme_counts"][theme] += 1

    source_list = []
    for name, info in sorted(per_source.items(), key=lambda x: -x[1]["item_count"]):
        dates_sorted = sorted(info["dates"])
        top_themes = [t for t, _ in info["theme_counts"].most_common(5)]
        source_list.append(
            {
                "name": name,
                "source_class": info["source_class"],
                "item_count": info["item_count"],
                "themed_count": info["themed_count"],
                "first_seen": dates_sorted[0] if dates_sorted else "",
                "last_seen": dates_sorted[-1] if dates_sorted else "",
                "days_active": len(info["dates"]),
                "top_themes": top_themes,
            }
        )
    return source_list


def _build_source_classes(source_list: list[dict]) -> dict[str, dict]:
    """Build the per-class summary dict expected by the Source Coverage Cards UI.

    Returns {"primary": {"count": N, "sources": [...]}, "operator": {...}, ...}
    """
    _all_classes = ("primary", "operator", "practitioner", "media", "market")
    class_counts: dict[str, int] = dict.fromkeys(_all_classes, 0)
    class_sources: dict[str, set] = {c: set() for c in _all_classes}
    for s in source_list:
        cls = s.get("source_class", "practitioner")
        if cls in class_counts:
            class_counts[cls] += s.get("item_count", 0)
            class_sources[cls].add(s["name"])
    return {
        cls: {"count": class_counts[cls], "sources": sorted(class_sources[cls])}
        for cls in _all_classes
    }


def _build_graph_edges(
    metrics: list[TrendMetrics],
    entries: list[tuple[str, str, str, str]],
    gemini_edges: list[dict],
) -> list[dict]:
    """Build graph edges from co-occurrence and Gemini-derived relationships."""
    dates_per_theme: dict[str, set] = defaultdict(set)
    for date_str, theme, _, _ in entries:
        dates_per_theme[theme].add(date_str)

    top_themes = {m.theme for m in metrics[:15]}
    edges: list[dict] = []
    theme_list = [m.theme for m in metrics if m.theme in top_themes]
    for i, t1 in enumerate(theme_list):
        for t2 in theme_list[i + 1 :]:
            shared = len(dates_per_theme[t1] & dates_per_theme[t2])
            if shared >= 3:
                edges.append(
                    {
                        "source": t1,
                        "target": t2,
                        "rel_type": "compositional",
                        "weight": shared,
                    }
                )
    edges.sort(key=lambda e: e["weight"], reverse=True)

    if gemini_edges:
        existing_pairs = {(e["source"], e["target"]) for e in edges}
        for ge in gemini_edges:
            pair = (ge.get("source", ""), ge.get("target", ""))
            if pair not in existing_pairs and pair[0] and pair[1]:
                edges.append(ge)
                existing_pairs.add(pair)

    return edges


def write_site_data(
    metrics: list[TrendMetrics],
    theme_nodes: list[ThemeNode],
    source_list: list[dict],
    edges: list[dict],
    docs_data_dir: Path,
    items: list[ProcessedItem] | None = None,
    file_log: list[dict] | None = None,
) -> None:
    """Write all docs/data/*.json files."""
    docs_data_dir.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(UTC).isoformat()
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")

    _items = items or []
    total_items = len(_items)
    themed_items = sum(1 for i in _items if i.theme)
    unthemed_items = total_items - themed_items
    enrichment_rate = round(themed_items / total_items, 3) if total_items else 0.0

    # Compute date range from fetch_date fields
    dates = sorted(i.fetch_date for i in _items if i.fetch_date)
    date_range = {"first": dates[0] if dates else "", "last": dates[-1] if dates else ""}

    (docs_data_dir / "meta.json").write_text(
        json.dumps(
            {
                "last_run": now_iso,
                "run_id": today_str,
                "total_items": total_items,
                "themed_items": themed_items,
                "unthemed_items": unthemed_items,
                "enrichment_rate": enrichment_rate,
                "item_count": total_items,
                "qualifying_theme_items": sum(m.item_count for m in metrics),
                "theme_count": len(metrics),
                "source_count": len(source_list),
                "date_range": date_range,
            },
            indent=2,
        )
    )

    (docs_data_dir / "trends.json").write_text(
        json.dumps({"generated": now_iso, "trends": [asdict(m) for m in metrics]}, indent=2)
    )

    (docs_data_dir / "themes.json").write_text(
        json.dumps({"generated": now_iso, "themes": [asdict(n) for n in theme_nodes]}, indent=2)
    )

    source_classes = _build_source_classes(source_list)
    (docs_data_dir / "sources.json").write_text(
        json.dumps(
            {"generated": now_iso, "classes": source_classes, "sources": source_list},
            indent=2,
        )
    )

    graph_nodes = [
        {"id": m.theme, "domain": m.domain, "state": m.state, "volume": m.volume} for m in metrics
    ]
    (docs_data_dir / "graph.json").write_text(
        json.dumps({"generated": now_iso, "nodes": graph_nodes, "edges": edges}, indent=2)
    )

    # items.json: lightweight per-item records for the drill-down view
    items_payload: list[dict] = []
    if items:
        for item in items:
            items_payload.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "url": item.url,
                    "source_name": item.source_name,
                    "source_class": item.source_class,
                    "theme": item.theme,
                    "domain": item.domain,
                    "fetch_date": item.fetch_date,
                    "credibility_score": item.credibility_score,
                    "hype_risk": item.hype_risk,
                    "summary": item.summary,
                }
            )
    (docs_data_dir / "items.json").write_text(
        json.dumps({"generated": now_iso, "items": items_payload}, indent=2)
    )

    # log.json: per-run audit record for the site Log view
    (docs_data_dir / "log.json").write_text(
        json.dumps(
            {
                "generated": now_iso,
                "run_id": today_str,
                "total_items": total_items,
                "themed_items": themed_items,
                "unthemed_items": unthemed_items,
                "enrichment_rate": enrichment_rate,
                "qualifying_theme_items": sum(m.item_count for m in metrics),
                "qualifying_themes": len(metrics),
                "source_count": len(source_list),
                "date_range": date_range,
                "ai_note": (
                    "AI enrichment ran on all items"
                    if enrichment_rate >= 0.95
                    else f"AI enrichment incomplete — {themed_items}/{total_items} items themed "
                    f"({round(enrichment_rate * 100)}%). "
                    "Check GEMINI_API_KEY secret and pipeline logs."
                ),
                "files": file_log or [],
            },
            indent=2,
        )
    )

    logger.info(
        "Wrote site data: %d themes, %d/%d themed items, %d graph edges → %s",
        len(metrics),
        themed_items,
        total_items,
        len(edges),
        docs_data_dir,
    )


def build(
    processed_dir: Path,
    docs_data_dir: Path,
    window_days: int = 90,
    dry_run: bool = False,
) -> None:
    """Build all site data from ProcessedItem records.

    Reads all *.jsonl files from processed_dir, computes trend metrics,
    and writes docs/data/*.json. When dry_run=True, logs what would be
    written without touching the filesystem.
    """
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")

    items, file_log = load_processed_items(processed_dir, window_days=window_days)
    themed_count = sum(1 for i in items if i.theme)
    logger.info(
        "Loaded %d items (%d themed, %d unthemed) from %d files",
        len(items),
        themed_count,
        len(items) - themed_count,
        len(file_log),
    )
    entries = items_to_entries(items)
    logger.info("Converted %d items to %d theme-day entries", len(items), len(entries))

    existing = _load_existing_metrics(docs_data_dir)
    metrics = build_trend_metrics(entries, existing, today_str)
    logger.info("Computed metrics for %d themes", len(metrics))

    # Optional Gemini enrichment: domain assignment + theme definitions
    gemini_edges: list[dict] = []
    if os.environ.get("GEMINI_API_KEY") and metrics:
        try:
            theme_records = [
                CanonicalRecord(
                    url=f"theme://{m.theme}",
                    title=m.theme,
                    source_class="practitioner",
                    claim=m.theme,
                    domain="unknown",  # type: ignore[arg-type]
                )
                for m in metrics
            ]
            existing_theme_names = [m.theme for m in metrics]
            _, theme_definitions, gemini_edges = cluster_themes(theme_records, existing_theme_names)
            def_lookup = {td["theme"]: td for td in theme_definitions if td.get("theme")}
            for m in metrics:
                if m.theme in def_lookup:
                    meta = def_lookup[m.theme]
                    if not m.domain or m.domain == "unknown":
                        m.domain = meta.get("domain", "unknown")
                    if not m.definition:
                        m.definition = meta.get("definition", "")
            logger.info("Gemini theme enrichment: %d themes updated", len(def_lookup))
        except Exception as exc:
            logger.warning("Gemini theme enrichment failed — skipping: %s", exc)
            gemini_edges = []

    theme_nodes = [
        ThemeNode(
            name=m.theme,
            domain=m.domain,
            definition=m.definition,
            state=m.state,
            item_count=m.item_count,
            last_seen=m.last_seen,
            source_classes=m.source_classes,
            source_class_counts=m.source_class_counts,
            hype_risk=m.hype_risk,
        )
        for m in metrics
    ]

    source_list = _build_source_list(items, entries)
    edges = _build_graph_edges(metrics, entries, gemini_edges)

    if dry_run:
        logger.info(
            "[dry-run] Would write %d themes, %d/%d themed items, %d graph edges to %s",
            len(metrics),
            themed_count,
            len(items),
            len(edges),
            docs_data_dir,
        )
        return

    write_site_data(
        metrics,
        theme_nodes,
        source_list,
        edges,
        docs_data_dir,
        items=items,
        file_log=file_log,
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build site data from data/processed/")
    p.add_argument("--processed-dir", default=str(_PROCESSED_DIR))
    p.add_argument("--docs-data-dir", default=str(_DOCS_DATA_DIR))
    p.add_argument("--window-days", type=int, default=90)
    p.add_argument("--no-fetch", action="store_true", help="No-op; kept for backward compat")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        cfg = load_config()
        setup_logging(debug=args.debug, log_file=cfg.logging.log_file)
    except Exception:
        setup_logging(debug=args.debug)

    build(
        processed_dir=Path(args.processed_dir),
        docs_data_dir=Path(args.docs_data_dir),
        window_days=args.window_days,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
