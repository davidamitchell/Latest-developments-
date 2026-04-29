"""Trend analysis pipeline.

Reads history/*.txt and the current day's items, extracts canonical records via
Gemini, scores credibility, clusters themes, updates trend state, and writes
structured JSON to docs/data/ for the GitHub Pages site.

Usage (called from daily-digest workflow after the main digest):
    python -m src.trends [--docs DOCS_DIR] [--history HISTORY_DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from src.credibility import detect_hype, score_credibility
from src.logger import setup_logging
from src.models import CanonicalRecord, GraphEdge, ThemeNode, TrendMetrics
from src.themes import build_graph_edges, build_theme_nodes, cluster_themes, normalize_theme_name
from src.trend_state import classify_state, update_metrics

logger = logging.getLogger(__name__)

_MAX_HISTORY_FILES = 30   # days of history to load for trend analysis
_MAX_CONTENT_CHARS = 2000  # chars to keep from each history digest for the Gemini prompt
_MIN_ITEMS_FOR_TREND = 2   # minimum items before a theme gets a state classification


# ── Record extraction ────────────────────────────────────────────────


def _build_extraction_prompt(digest_text: str) -> str:
    return f"""You are a structured data extractor for AI/ML research trend analysis.

Given the digest text below, extract a canonical record for each distinct item mentioned.

For each item output one JSON object per line (JSON-lines format), no markdown:
{{"url":"...","title":"...","claim":"one sentence","evidence_type":"experiment|benchmark|anecdote|announcement|analysis|unknown","domain":"multimodal|agents|infra|reasoning|safety|evals|data|hardware|general|unknown","technique":"short phrase or empty","impact_vector":"cost|latency|capability|safety|adoption|unknown","actors":["name1"],"source_class":"primary|operator|practitioner|media|market"}}

Rules:
- claim: the single most important assertion in the item (≤ 25 words)
- evidence_type: how the claim is supported
- domain: primary AI/ML domain affected
- technique: specific method (e.g. "RLHF", "LoRA", "RAG") or empty string
- impact_vector: primary dimension of change
- actors: organisations or models mentioned
- source_class: classification of the original source

Digest:
---
{digest_text[:8000]}
---
"""


def extract_records_from_digest(
    digest_text: str,
    default_date: str = "",
) -> list[CanonicalRecord]:
    """Call Gemini to extract canonical records from a plain-text digest."""
    if not digest_text.strip():
        return []

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    prompt = _build_extraction_prompt(digest_text)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=4096),
        )
        raw = response.text.strip()
    except genai_errors.APIError as exc:
        logger.warning("Gemini extraction failed: %s", exc)
        return []

    records: list[CanonicalRecord] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not data.get("url") and not data.get("title"):
            continue
        rec = CanonicalRecord(
            url=data.get("url", ""),
            title=data.get("title", ""),
            source_class=data.get("source_class", "practitioner"),
            claim=data.get("claim", ""),
            evidence_type=data.get("evidence_type", "unknown"),
            domain=data.get("domain", "unknown"),
            technique=data.get("technique", ""),
            impact_vector=data.get("impact_vector", "unknown"),
            actors=data.get("actors", []),
            date=default_date,
        )
        rec.credibility_score = score_credibility(rec)
        rec.hype_risk = detect_hype(rec)
        records.append(rec)

    logger.info("Extracted %d canonical records from digest", len(records))
    return records


# ── History loading ──────────────────────────────────────────────────


def load_history_digests(history_dir: Path, max_files: int = _MAX_HISTORY_FILES) -> list[tuple[str, str]]:
    """Return list of (date_str, digest_text) pairs, most recent first."""
    txt_files = sorted(history_dir.glob("*.txt"), reverse=True)[:max_files]
    result = []
    for f in txt_files:
        date_str = f.stem  # filename is YYYY-MM-DD
        try:
            text = f.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read %s: %s", f, exc)
            continue
        result.append((date_str, text))
    return result


# ── Existing state loading / saving ──────────────────────────────────


def load_existing_data(docs_data_dir: Path) -> tuple[list[TrendMetrics], list[ThemeNode], list[GraphEdge]]:
    """Load previously written trends.json, themes.json, graph.json."""
    trends: list[TrendMetrics] = []
    themes: list[ThemeNode] = []
    edges: list[GraphEdge] = []

    trends_path = docs_data_dir / "trends.json"
    if trends_path.exists():
        try:
            raw = json.loads(trends_path.read_text())
            for t in raw.get("trends", []):
                m = TrendMetrics(
                    theme=t.get("theme", ""),
                    domain=t.get("domain", "unknown"),
                    definition=t.get("definition", ""),
                    state=t.get("state", "unknown"),
                    confidence=t.get("confidence", 0.5),
                    volume=t.get("volume", 0.0),
                    velocity=t.get("velocity", 0.0),
                    diversity=t.get("diversity", 0),
                    adoption_proxy=t.get("adoption_proxy", 0.0),
                    stability=t.get("stability", 1.0),
                    hype_risk=t.get("hype_risk", 0.0),
                    item_count=t.get("item_count", 0),
                    last_seen=t.get("last_seen", ""),
                    source_classes=t.get("source_classes", []),
                    source_class_counts=t.get("source_class_counts", {}),
                    history=t.get("history", []),
                )
                trends.append(m)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Could not load trends.json: %s", exc)

    themes_path = docs_data_dir / "themes.json"
    if themes_path.exists():
        try:
            raw = json.loads(themes_path.read_text())
            for t in raw.get("themes", []):
                themes.append(ThemeNode(
                    name=t.get("name", ""),
                    domain=t.get("domain", "unknown"),
                    definition=t.get("definition", ""),
                    state=t.get("state", "unknown"),
                    item_count=t.get("item_count", 0),
                    last_seen=t.get("last_seen", ""),
                    source_classes=t.get("source_classes", []),
                    source_class_counts=t.get("source_class_counts", {}),
                    hype_risk=t.get("hype_risk", 0.0),
                ))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Could not load themes.json: %s", exc)

    return trends, themes, edges


# ── Trend metrics computation ─────────────────────────────────────────


def compute_theme_metrics(
    theme_name: str,
    records_for_theme: list[CanonicalRecord],
    existing: TrendMetrics | None,
    today_str: str,
    theme_def: str = "",
    theme_domain: str = "unknown",
) -> TrendMetrics:
    """Compute updated TrendMetrics for a single theme from today's records."""
    metrics = existing or TrendMetrics(theme=theme_name)

    # Update definition and domain if we have new data
    if theme_def:
        metrics.definition = theme_def
    if theme_domain and theme_domain != "unknown":
        metrics.domain = theme_domain

    # Credibility-weighted volume for today
    today_volume = sum(r.credibility_score for r in records_for_theme)

    # Source class diversity
    sc_counter: Counter = Counter(r.source_class for r in records_for_theme)
    metrics.source_class_counts = dict(sc_counter)
    metrics.source_classes = [cls for cls, _ in sc_counter.most_common()]
    metrics.diversity = len(sc_counter)

    # Hype risk: average across items
    if records_for_theme:
        metrics.hype_risk = round(
            sum(r.hype_risk for r in records_for_theme) / len(records_for_theme), 3
        )

    metrics.item_count = len(records_for_theme)
    metrics.last_seen = today_str

    # Confidence: based on cross-class support (diversity) and credibility
    avg_cred = (sum(r.credibility_score for r in records_for_theme) / len(records_for_theme)
                if records_for_theme else 0.5)
    diversity_factor = min(1.0, metrics.diversity / 3)
    metrics.confidence = round(avg_cred * 0.6 + diversity_factor * 0.4, 3)

    # Update rolling history and state via trend_state module
    metrics = update_metrics(metrics, today_volume, today_str)

    return metrics


# ── JSON serialization ───────────────────────────────────────────────


def _safe_asdict(obj) -> dict:
    """Convert a dataclass to dict, handling nested lists of dataclasses."""
    d = asdict(obj)
    return d


# ── Main pipeline ─────────────────────────────────────────────────────


def run(
    docs_data_dir: Path,
    history_dir: Path,
    dry_run: bool = False,
) -> None:
    """Run the trend analysis pipeline and write docs/data/*.json."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    logger.info("Trend analysis: loading history from %s", history_dir)
    history = load_history_digests(history_dir)
    if not history:
        logger.warning("No history files found — skipping trend analysis")
        return

    logger.info("Loaded %d history files", len(history))

    # Load existing state
    existing_trends, existing_themes, _ = load_existing_data(docs_data_dir)
    existing_trend_map = {m.theme: m for m in existing_trends}
    existing_theme_names = [t.name for t in existing_themes]

    # Extract canonical records from all history digests
    all_records: list[CanonicalRecord] = []
    # Only process the most recent N days for the actual extraction to bound cost
    for date_str, digest_text in history[:14]:
        records = extract_records_from_digest(digest_text, default_date=date_str)
        all_records.extend(records)

    if not all_records:
        logger.warning("No canonical records extracted — skipping theme clustering")
        return

    logger.info("Extracted %d canonical records total", len(all_records))

    # Cluster into themes
    url_to_theme, definitions, relationships = cluster_themes(all_records, existing_theme_names)

    # Group records by theme for this run
    theme_records: dict[str, list[CanonicalRecord]] = {}
    for rec in all_records:
        theme = url_to_theme.get(rec.url, normalize_theme_name(rec.domain or "General"))
        theme_records.setdefault(theme, []).append(rec)

    # Build theme definitions lookup
    def_map = {d["theme"]: d for d in definitions}

    # Compute trend metrics per theme
    updated_metrics: list[TrendMetrics] = []
    for theme_name, recs in sorted(theme_records.items()):
        if len(recs) < _MIN_ITEMS_FOR_TREND:
            continue
        defn = def_map.get(theme_name, {})
        existing = existing_trend_map.get(theme_name)
        metrics = compute_theme_metrics(
            theme_name=theme_name,
            records_for_theme=recs,
            existing=existing,
            today_str=today_str,
            theme_def=defn.get("definition", ""),
            theme_domain=defn.get("domain", "unknown"),
        )
        updated_metrics.append(metrics)

    # Sort by credibility-weighted volume desc
    updated_metrics.sort(key=lambda m: m.volume, reverse=True)

    # Build theme nodes
    nodes = build_theme_nodes(all_records, url_to_theme, definitions, existing_themes)
    for node in nodes:
        # Sync state from metrics
        m = next((m for m in updated_metrics if m.theme == node.name), None)
        if m:
            node.state = m.state
            node.hype_risk = m.hype_risk
            node.item_count = m.item_count

    # Build graph edges
    edges = build_graph_edges(relationships)

    # Source class coverage stats
    all_sc: Counter = Counter(r.source_class for r in all_records)
    source_class_info: dict[str, dict] = {}
    for cls in ("primary", "operator", "practitioner", "media", "market"):
        source_class_info[cls] = {
            "count": all_sc.get(cls, 0),
            "sources": list({r.source_name for r in all_records if r.source_class == cls}),
        }

    # ── Write output ─────────────────────────────────────────────────

    if dry_run:
        logger.info("[dry-run] Would write %d themes, %d trend metrics to %s",
                    len(nodes), len(updated_metrics), docs_data_dir)
        return

    docs_data_dir.mkdir(parents=True, exist_ok=True)

    # meta.json
    meta = {
        "last_run": now_iso,
        "run_id": today_str,
        "item_count": len(all_records),
        "theme_count": len(updated_metrics),
        "source_class_counts": dict(all_sc),
    }
    (docs_data_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    # trends.json
    trends_out = {
        "generated": now_iso,
        "trends": [_safe_asdict(m) for m in updated_metrics],
    }
    (docs_data_dir / "trends.json").write_text(json.dumps(trends_out, indent=2))

    # themes.json
    themes_out = {
        "generated": now_iso,
        "themes": [_safe_asdict(n) for n in nodes],
    }
    (docs_data_dir / "themes.json").write_text(json.dumps(themes_out, indent=2))

    # graph.json
    graph_out = {
        "generated": now_iso,
        "nodes": [{"id": n.name, "domain": n.domain, "state": n.state, "volume": m.volume if (m := next((x for x in updated_metrics if x.theme == n.name), None)) else 0} for n in nodes],
        "edges": [_safe_asdict(e) for e in edges],
    }
    (docs_data_dir / "graph.json").write_text(json.dumps(graph_out, indent=2))

    # items.json (last 30 days of records)
    items_out = {
        "generated": now_iso,
        "items": [_safe_asdict(r) for r in all_records],
    }
    (docs_data_dir / "items.json").write_text(json.dumps(items_out, indent=2))

    # sources.json
    sources_out = {
        "generated": now_iso,
        "classes": source_class_info,
    }
    (docs_data_dir / "sources.json").write_text(json.dumps(sources_out, indent=2))

    logger.info(
        "Trend analysis complete: %d themes, %d metrics, %d edges written to %s",
        len(nodes), len(updated_metrics), len(edges), docs_data_dir,
    )


# ── CLI entry point ──────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trend analysis pipeline")
    parser.add_argument("--docs", default="docs/data", help="Path to docs/data/ directory")
    parser.add_argument("--history", default="history", help="Path to history/ directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip writing output files")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    setup_logging(debug=args.debug)

    repo_root = Path(__file__).parent.parent
    docs_data_dir = Path(args.docs) if Path(args.docs).is_absolute() else repo_root / args.docs
    history_dir = Path(args.history) if Path(args.history).is_absolute() else repo_root / args.history

    if not history_dir.exists():
        logger.error("History directory not found: %s", history_dir)
        sys.exit(1)

    run(docs_data_dir=docs_data_dir, history_dir=history_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
