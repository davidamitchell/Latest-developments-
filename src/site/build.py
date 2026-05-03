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
from src.trend_state import classify_state, compute_stability
from src.trends import (
    _backfill_history,
    _dates_in_window,
    _load_existing_metrics,
    build_trend_metrics,
)

logger = logging.getLogger(__name__)

_PROCESSED_DIR = Path("data/processed")
_DOCS_DATA_DIR = Path("docs/data")

_VOLUME_WINDOW_DAYS = 14
_MIN_THEME_APPEARANCES = 2


def load_processed_items(data_dir: Path, window_days: int = 90) -> list[ProcessedItem]:
    """Load all ProcessedItem records from data_dir/*.jsonl files.

    Reads every .jsonl file found in the directory. The window_days parameter
    is reserved for future use (filtering by fetch_date); currently all files
    are loaded.
    """
    if not data_dir.exists():
        logger.debug("Processed data directory not found: %s", data_dir)
        return []

    all_items: list[ProcessedItem] = []
    for jsonl_file in sorted(data_dir.glob("*.jsonl")):
        items = read_processed_jsonl(jsonl_file)
        all_items.extend(items)
        logger.debug("Loaded %d items from %s", len(items), jsonl_file)

    logger.info("Loaded %d total ProcessedItem records from %s", len(all_items), data_dir)
    return all_items


def items_to_entries(
    items: list[ProcessedItem],
) -> list[tuple[str, str, str, str]]:
    """Convert ProcessedItem list to (date_str, theme, source_class, source_name) tuples.

    Items with no theme assigned are skipped — the pipeline may not have run
    AI stages on all items (e.g. when GEMINI_API_KEY was absent).
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
    """Build the per-source detail list for sources.json."""
    per_source: dict[str, dict] = {}
    for date_str, theme, cls, name in entries:
        if name not in per_source:
            per_source[name] = {
                "name": name,
                "source_class": cls,
                "item_count": 0,
                "dates": set(),
                "theme_counts": Counter(),
            }
        per_source[name]["item_count"] += 1
        per_source[name]["dates"].add(date_str)
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
    _ALL_CLASSES = ("primary", "operator", "practitioner", "media", "market")
    class_counts: dict[str, int] = {c: 0 for c in _ALL_CLASSES}
    class_sources: dict[str, set] = {c: set() for c in _ALL_CLASSES}
    for s in source_list:
        cls = s.get("source_class", "practitioner")
        if cls in class_counts:
            class_counts[cls] += s.get("item_count", 0)
            class_sources[cls].add(s["name"])
    return {
        cls: {"count": class_counts[cls], "sources": sorted(class_sources[cls])}
        for cls in _ALL_CLASSES
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
        for t2 in theme_list[i + 1:]:
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
) -> None:
    """Write all docs/data/*.json files."""
    docs_data_dir.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(UTC).isoformat()
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")

    (docs_data_dir / "meta.json").write_text(
        json.dumps(
            {
                "last_run": now_iso,
                "run_id": today_str,
                "item_count": sum(m.item_count for m in metrics),
                "theme_count": len(metrics),
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
        {"id": m.theme, "domain": m.domain, "state": m.state, "volume": m.volume}
        for m in metrics
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

    logger.info(
        "Wrote site data: %d themes, %d items, %d graph edges → %s",
        len(metrics),
        len(items_payload),
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

    items = load_processed_items(processed_dir, window_days=window_days)
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
            _, theme_definitions, gemini_edges = cluster_themes(
                theme_records, existing_theme_names
            )
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
            "[dry-run] Would write %d themes, %d items, %d graph edges to %s",
            len(metrics),
            len(items),
            len(edges),
            docs_data_dir,
        )
        return

    write_site_data(metrics, theme_nodes, source_list, edges, docs_data_dir, items=items)


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
