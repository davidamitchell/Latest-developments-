"""Trend analysis pipeline.

Reads history/*.txt files for theme signals from the email pipeline,
and optionally fetches live arXiv papers (primary source class) to
enrich cross-class confirmation. Writes docs/data/*.json for the site.

Usage:
    python -m src.trends [--docs docs/data] [--history history] [--dry-run] [--debug]
    python -m src.trends --no-fetch   # history-only, no network calls
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from src.config import load_config
from src.fetchers.arxiv import ArxivFetcher
from src.fetchers.huggingface import HuggingFaceFetcher
from src.logger import setup_logging
from src.models import CanonicalRecord, ThemeNode, TrendMetrics
from src.themes import cluster_themes, normalize_theme_name
from src.trend_state import classify_state, compute_stability

logger = logging.getLogger(__name__)

# Minimum times a theme must appear across history to be included in output.
_MIN_THEME_APPEARANCES = 2

# Rolling window for volume calculation (days).
_VOLUME_WINDOW_DAYS = 14

# Source class inferred from URL domain.
_URL_SOURCE_CLASS: list[tuple[str, str]] = [
    ("youtube.com", "practitioner"),
    ("youtu.be", "practitioner"),
    ("news.ycombinator.com", "practitioner"),
    ("hacker", "practitioner"),
    ("substack.com", "media"),
    ("arxiv.org", "primary"),
    ("huggingface.co", "primary"),
    ("paperswithcode.com", "primary"),
    ("openreview.net", "primary"),
    ("github.com", "primary"),
    ("openai.com", "operator"),
    ("anthropic.com", "operator"),
    ("deepmind.google", "operator"),
    ("blog.google", "operator"),
    ("azure.com", "operator"),
    ("aws.amazon.com", "operator"),
    ("techcrunch.com", "media"),
    ("technologyreview.mit", "media"),
    ("theinformation.com", "media"),
]

# URL pattern → human-readable source name (for diversity counting).
# Diversity is measured in distinct source *names* (YouTube ≠ Hacker News),
# not source *classes* (both are "practitioner"). This gives a meaningful
# cross-source confirmation signal with the current source set.
_URL_SOURCE_NAME: list[tuple[str, str]] = [
    ("youtube.com", "YouTube"),
    ("youtu.be", "YouTube"),
    ("news.ycombinator.com", "Hacker News"),
    ("substack.com", "Substack"),
    ("arxiv.org", "arXiv"),
    ("huggingface.co", "Hugging Face"),
    ("paperswithcode.com", "Papers With Code"),
    ("github.com", "GitHub"),
    ("openai.com", "OpenAI"),
    ("anthropic.com", "Anthropic"),
]

# Source type name → class (from run summary section).
_SOURCE_TYPE_CLASS: dict[str, str] = {
    "youtube": "practitioner",
    "hacker news": "practitioner",
    "blogs/rss": "practitioner",
    "substack": "media",
    "rss": "practitioner",
}


# ── Parsers ──────────────────────────────────────────────────────────


def _infer_source_class(url: str) -> str:
    """Infer source class from URL domain without any API call."""
    url_lower = url.lower()
    for pattern, cls in _URL_SOURCE_CLASS:
        if pattern in url_lower:
            return cls
    return "practitioner"


def _infer_source_name(url: str) -> str:
    """Infer a human-readable source name from URL for diversity counting."""
    url_lower = url.lower()
    for pattern, name in _URL_SOURCE_NAME:
        if pattern in url_lower:
            return name
    return "Other"


def _parse_item_themes_section(text: str) -> dict[str, str]:
    """Extract url → theme from '## Item Themes' section.

    Format:
        ## Item Themes
        - https://... | Theme Label
    """
    themes: dict[str, str] = {}
    pattern = re.compile(
        r"(?:^|\n)\s*##\s*Item Themes\s*\n(.*?)(?=\n##\s|\n[─═]{4,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return themes
    for line in match.group(1).splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if " | " in stripped:
            url_part, theme_part = stripped.split(" | ", 1)
            url_part = url_part.strip()
            theme_part = theme_part.strip()
            if url_part and theme_part:
                themes[url_part] = normalize_theme_name(theme_part)
    return themes


def _parse_inline_themes(text: str) -> list[str]:
    """Extract theme labels from inline 'Theme: X' format.

    Format:
        Theme: Multi-Agent Systems
        Summary: ...
    """
    return [
        normalize_theme_name(m.group(1).strip())
        for m in re.finditer(r"^Theme:\s*(.+)$", text, re.MULTILINE)
    ]


def _parse_run_summary_sources(text: str) -> dict[str, int]:
    """Extract source type → item count from the Run summary block.

    Format:
        Sources fetched:
          YouTube: 3 new item(s)
          Hacker News: 5 new item(s)
    """
    sources: dict[str, int] = {}
    in_sources = False
    for line in text.splitlines():
        if "Sources fetched:" in line:
            in_sources = True
            continue
        if in_sources:
            m = re.match(r"\s+([^:]+):\s*(\d+)\s+new item", line, re.IGNORECASE)
            if m:
                sources[m.group(1).strip()] = int(m.group(2))
            elif line.strip() and not line.startswith(" "):
                break
    return sources


def parse_history_file(
    date_str: str, text: str
) -> tuple[list[tuple[str, str, str]], dict[str, int]]:
    """Parse a history file into (theme_entries, source_counts).

    theme_entries: list of (theme_name, source_class, source_name).
    source_counts: dict of source_type_name → count from the run summary.
    """
    if "AI summarisation failed" in text and "## Item Themes" not in text:
        return [], _parse_run_summary_sources(text)

    source_counts = _parse_run_summary_sources(text)
    entries: list[tuple[str, str, str]] = []

    # Prefer structured ## Item Themes section (newest prompt format)
    structured = _parse_item_themes_section(text)
    if structured:
        for url, theme in structured.items():
            cls = _infer_source_class(url)
            name = _infer_source_name(url)
            entries.append((theme, cls, name))
        return entries, source_counts

    # Fall back to inline Theme: labels (older prompt format)
    inline_themes = _parse_inline_themes(text)
    if inline_themes:
        yt_count = source_counts.get("YouTube", 0)
        sub_count = source_counts.get("Substack", 0) + source_counts.get("Blogs/RSS", 0)
        total = sum(source_counts.values()) or 1

        for i, theme in enumerate(inline_themes):
            cum = i % total if total > 0 else 0
            if cum < yt_count:
                cls, name = "practitioner", "YouTube"
            elif cum < yt_count + sub_count:
                cls, name = "media", "Substack"
            else:
                cls, name = "practitioner", "Hacker News"
            entries.append((theme, cls, name))
        return entries, source_counts

    return [], source_counts


# ── Aggregation ──────────────────────────────────────────────────────


def _dates_in_window(all_dates: list[str], window_days: int) -> list[str]:
    """Return dates within the last *window_days* of the most recent date."""
    if not all_dates:
        return []
    sorted_dates = sorted(all_dates, reverse=True)
    cutoff = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date() if sorted_dates else date.today()
    result = []
    for d in sorted_dates:
        delta = (cutoff - datetime.strptime(d, "%Y-%m-%d").date()).days
        if delta <= window_days:
            result.append(d)
    return result


def _backfill_history(
    entries: list[tuple[str, str, str]],  # (date_str, source_class, source_name)
) -> list[dict]:
    """Build weekly volume snapshots from raw per-day entries.

    Called on first run for a theme to populate the history array from the
    full archive rather than showing a single point on the chart.
    """
    from datetime import timedelta

    week_counts: Counter = Counter()
    week_sources: dict[str, set] = defaultdict(set)

    for date_str, _cls, name in entries:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        week_start = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
        week_counts[week_start] += 1
        week_sources[week_start].add(name)

    weeks = sorted(week_counts.keys())
    if not weeks:
        return []

    snapshots = []
    for i, week in enumerate(weeks):
        count = week_counts[week]
        prev_count = week_counts.get(weeks[i - 1], 0) if i > 0 else 0
        velocity = (count - prev_count) / max(prev_count, 1)
        diversity = len(week_sources[week])

        # Simplified state for historical backfill (no adoption_proxy available)
        if velocity < -0.05 and prev_count > 0:
            state = "declining"
        elif velocity > 0.3 and diversity >= 2:
            state = "emerging"
        elif count >= 2 and diversity >= 2:
            state = "scaling"
        else:
            state = "unknown"

        snapshots.append(
            {
                "date": week,
                "volume": count,  # raw weekly item count
                "state": state,
            }
        )

    return snapshots[-30:]


def build_trend_metrics(
    history: list[tuple[str, str, str, str]],  # (date_str, theme, source_class, source_name)
    existing_metrics: dict[str, TrendMetrics],
    today_str: str,
) -> list[TrendMetrics]:
    """Compute TrendMetrics for every theme from the full history."""

    # Group by theme: store (date, source_class, source_name) tuples
    theme_entries: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for date_str, theme, cls, name in history:
        theme_entries[theme].append((date_str, cls, name))

    all_dates = sorted({d for d, _, _, _ in history}, reverse=True)

    # Span of history in weeks (used for per-week volume normalisation)
    if len(all_dates) >= 2:
        oldest = datetime.strptime(all_dates[-1], "%Y-%m-%d").date()
        newest = datetime.strptime(all_dates[0], "%Y-%m-%d").date()
        span_weeks = max(1.0, (newest - oldest).days / 7)
    else:
        span_weeks = 1.0

    # Recent and previous windows for velocity
    recent_dates = set(_dates_in_window(all_dates, _VOLUME_WINDOW_DAYS))
    prev_dates = set(_dates_in_window(all_dates, _VOLUME_WINDOW_DAYS * 2)) - recent_dates

    metrics_list: list[TrendMetrics] = []

    for theme, entries in theme_entries.items():
        if len(entries) < _MIN_THEME_APPEARANCES:
            continue

        existing = existing_metrics.get(theme, TrendMetrics(theme=theme))

        # Volume: average weekly appearance rate across full history
        volume = round(len(entries) / span_weeks, 2)

        # Velocity: recent window count vs previous window count (relative)
        recent_count = sum(1 for d, _, _ in entries if d in recent_dates)
        prev_count = sum(1 for d, _, _ in entries if d in prev_dates)
        vel_prev = prev_count or max(1, len(entries) - recent_count)
        velocity = round((recent_count - vel_prev) / vel_prev, 4)

        # Source class distribution (for hype risk)
        sc_counter: Counter = Counter(cls for _, cls, _ in entries)
        source_classes = [cls for cls, _ in sc_counter.most_common()]

        # Diversity: count of distinct source *names* (YouTube ≠ Hacker News,
        # even though both are "practitioner").  This gives a meaningful
        # cross-source confirmation signal with the current source set.
        source_name_counter: Counter = Counter(name for _, _, name in entries)
        diversity = len(source_name_counter)

        # Hype risk: fraction of media-class entries
        media_count = sc_counter.get("media", 0)
        hype_risk = round(media_count / max(len(entries), 1), 3)

        # Confidence: diversity and volume relative to history span
        diversity_factor = min(1.0, diversity / 3)
        volume_factor = min(1.0, volume / 3)
        confidence = round(diversity_factor * 0.5 + volume_factor * 0.5, 3)

        # Rolling history: always recompute weekly snapshots from raw entries.
        # This gives the chart the full date range regardless of when the
        # pipeline was first run.  State for the final snapshot is updated
        # below after classify_state() runs.
        prev_history = _backfill_history(entries)

        stability = compute_stability(prev_history)
        last_seen = max((d for d, _, _ in entries), default=today_str)

        m = TrendMetrics(
            theme=theme,
            domain=existing.domain or "unknown",
            definition=existing.definition,
            state="unknown",
            confidence=confidence,
            volume=volume,
            velocity=velocity,
            diversity=diversity,
            adoption_proxy=0.0,
            stability=stability,
            hype_risk=hype_risk,
            item_count=len(entries),
            last_seen=last_seen,
            source_classes=source_classes,
            source_class_counts=dict(sc_counter),
            history=prev_history,
        )
        m.state = classify_state(m)

        if m.history:
            m.history[-1]["state"] = m.state

        metrics_list.append(m)

    metrics_list.sort(key=lambda m: m.volume, reverse=True)
    return metrics_list


# ── Existing state loading ────────────────────────────────────────────


def _load_existing_metrics(docs_data_dir: Path) -> dict[str, TrendMetrics]:
    trends_path = docs_data_dir / "trends.json"
    if not trends_path.exists():
        return {}
    try:
        raw = json.loads(trends_path.read_text())
        result = {}
        for t in raw.get("trends", []):
            name = t.get("theme", "")
            if name:
                result[name] = TrendMetrics(
                    theme=name,
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
        return result
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Could not load existing trends.json: %s", exc)
        return {}


def _fetch_arxiv(
    trends_cfg,  # TrendsConfig — type annotation skipped to avoid circular import
    today_str: str,
) -> list[tuple[str, str, str, str]]:
    """Fetch arXiv papers and return (date, theme, source_class, source_name) tuples.

    Each paper's title is used as the theme name (normalised), so arXiv papers
    add primary-class signal to the theme diversity count.
    """
    try:
        fetcher = ArxivFetcher(
            categories=trends_cfg.arxiv.categories,
            max_papers=trends_cfg.arxiv.max_papers,
        )
        items = fetcher.fetch(already_processed=set())
    except Exception as exc:
        logger.warning("arXiv fetch failed — skipping: %s", exc)
        return []

    entries: list[tuple[str, str, str, str]] = []
    for item in items:
        # Use normalised title as an approximate theme signal.
        # Real theme clustering (W-0005) will improve this.
        raw_theme = item.title[:80]  # cap length for display
        theme = normalize_theme_name(raw_theme)
        pub_date = item.published.strftime("%Y-%m-%d") if item.published else today_str
        entries.append((pub_date, theme, "primary", "arXiv"))
    return entries


def _fetch_huggingface(
    trends_cfg,
    today_str: str,
) -> list[tuple[str, str, str, str]]:
    """Fetch HuggingFace model releases and return theme-day entries."""
    try:
        fetcher = HuggingFaceFetcher(
            max_models=trends_cfg.huggingface.max_models,
            min_downloads=trends_cfg.huggingface.min_downloads,
        )
        items = fetcher.fetch(already_processed=set())
    except Exception as exc:
        logger.warning("HuggingFace fetch failed — skipping: %s", exc)
        return []

    entries: list[tuple[str, str, str, str]] = []
    for item in items:
        raw_theme = item.title[:80]
        theme = normalize_theme_name(raw_theme)
        pub_date = item.published.strftime("%Y-%m-%d") if item.published else today_str
        entries.append((pub_date, theme, "primary", "Hugging Face"))
    return entries


# ── Main pipeline ─────────────────────────────────────────────────────


def run(
    docs_data_dir: Path,
    history_dir: Path,
    dry_run: bool = False,
    fetch_live: bool = True,
) -> None:
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    now_iso = datetime.now(UTC).isoformat()

    # ── 0. Load config (for trend sources) ───────────────────────────
    try:
        cfg = load_config()
        trends_cfg = cfg.trends
    except Exception as exc:
        logger.warning("Could not load config, using defaults: %s", exc)
        from src.config import TrendsConfig

        trends_cfg = TrendsConfig()

    # ── 1. Load and parse all history files ──────────────────────────
    txt_files = sorted(history_dir.glob("*.txt"), reverse=True)
    if not txt_files:
        logger.warning("No history files found in %s — nothing to process", history_dir)
        return

    logger.info("Parsing %d history files from %s", len(txt_files), history_dir)

    all_entries: list[
        tuple[str, str, str, str]
    ] = []  # (date_str, theme, source_class, source_name)
    all_source_counts: Counter = Counter()  # source_type_name → total count

    for f in txt_files:
        date_str = f.stem  # YYYY-MM-DD
        try:
            text = f.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", f, exc)
            continue

        entries, src_counts = parse_history_file(date_str, text)
        for theme, cls, name in entries:
            all_entries.append((date_str, normalize_theme_name(theme), cls, name))
        for src, count in src_counts.items():
            all_source_counts[src.lower()] += count

    logger.info("Extracted %d theme-day entries across %d files", len(all_entries), len(txt_files))

    # ── 1b. Fetch live sources (primary/operator class) ──────────────
    if fetch_live and trends_cfg.enabled:
        if trends_cfg.arxiv.enabled:
            arxiv_items = _fetch_arxiv(trends_cfg, today_str)
            all_entries.extend(arxiv_items)
            if arxiv_items:
                all_source_counts["arxiv"] += len(arxiv_items)
        if trends_cfg.huggingface.enabled:
            hf_items = _fetch_huggingface(trends_cfg, today_str)
            all_entries.extend(hf_items)
            if hf_items:
                all_source_counts["hugging face"] += len(hf_items)
    else:
        logger.info("Live fetching disabled — using history only")

    # ── 2. Load existing rolling state ───────────────────────────────
    existing = _load_existing_metrics(docs_data_dir)

    # ── 3. Compute trend metrics ──────────────────────────────────────
    metrics = build_trend_metrics(all_entries, existing, today_str)
    logger.info("Computed metrics for %d themes", len(metrics))

    # ── 3b. Enrich theme metadata via Gemini (W-0005) ─────────────────
    # cluster_themes() uses Gemini to assign canonical domain + write a
    # one-sentence definition for each theme.  It requires GEMINI_API_KEY
    # which is available in GitHub Actions but not in local --no-fetch runs.
    # Graceful fallback: keep "unknown" domain and empty definition.
    if os.environ.get("GEMINI_API_KEY"):
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

            def_lookup: dict[str, dict] = {
                td["theme"]: td for td in theme_definitions if td.get("theme")
            }
            for m in metrics:
                if m.theme in def_lookup:
                    meta = def_lookup[m.theme]
                    if not m.domain or m.domain == "unknown":
                        m.domain = meta.get("domain", "unknown")
                    if not m.definition:
                        m.definition = meta.get("definition", "")

            logger.info("Gemini theme enrichment: %d themes updated", len(def_lookup))
            _gemini_edges: list[dict] = gemini_edges
        except Exception as exc:
            logger.warning("Gemini theme enrichment failed — skipping: %s", exc)
            _gemini_edges = []
    else:
        logger.debug("GEMINI_API_KEY not set — skipping Gemini theme enrichment")
        _gemini_edges = []

    # ── 4. Build theme nodes (for themes tab) ─────────────────────────
    theme_nodes: list[ThemeNode] = [
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

    # ── 5. Source class coverage + per-source stats ───────────────────
    source_class_info: dict[str, dict] = {}
    class_source_names: dict[str, set] = defaultdict(set)
    for src_lower, _ in all_source_counts.items():
        cls = _SOURCE_TYPE_CLASS.get(src_lower, "practitioner")
        class_source_names[cls].add(src_lower.title())

    for cls in ("primary", "operator", "practitioner", "media", "market"):
        total = sum(
            count
            for src, count in all_source_counts.items()
            if _SOURCE_TYPE_CLASS.get(src, "practitioner") == cls
        )
        source_class_info[cls] = {
            "count": total,
            "sources": sorted(class_source_names.get(cls, [])),
        }

    # Per-source detail: group all_entries by source_name
    per_source: dict[str, dict] = {}
    for date_str, theme, cls, name in all_entries:
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

    # ── 6. Graph: co-occurrence + Gemini-derived relationships ──────────
    # Themes that appear on the same day → compositional edge candidate.
    # Gemini-derived edges (from cluster_themes) are merged and take precedence
    # over co-occurrence edges for the same source/target pair.
    dates_per_theme: dict[str, set] = defaultdict(set)
    for date_str, theme, _, _name in all_entries:
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

    # Merge Gemini-derived edges (W-0005): replace or extend co-occurrence set
    if _gemini_edges:
        existing_pairs = {(e["source"], e["target"]) for e in edges}
        for ge in _gemini_edges:
            pair = (ge.get("source", ""), ge.get("target", ""))
            if pair not in existing_pairs and pair[0] and pair[1]:
                edges.append(ge)
                existing_pairs.add(pair)

    # ── 7. Write output ───────────────────────────────────────────────
    if dry_run:
        logger.info(
            "[dry-run] Would write %d themes, %d metrics, %d graph edges to %s",
            len(theme_nodes),
            len(metrics),
            len(edges),
            docs_data_dir,
        )
        _preview(metrics[:5])
        return

    docs_data_dir.mkdir(parents=True, exist_ok=True)

    (docs_data_dir / "meta.json").write_text(
        json.dumps(
            {
                "last_run": now_iso,
                "run_id": today_str,
                "item_count": len(all_entries),
                "theme_count": len(metrics),
                "source_class_counts": dict(all_source_counts),
            },
            indent=2,
        )
    )

    (docs_data_dir / "trends.json").write_text(
        json.dumps(
            {
                "generated": now_iso,
                "trends": [asdict(m) for m in metrics],
            },
            indent=2,
        )
    )

    (docs_data_dir / "themes.json").write_text(
        json.dumps(
            {
                "generated": now_iso,
                "themes": [asdict(n) for n in theme_nodes],
            },
            indent=2,
        )
    )

    (docs_data_dir / "graph.json").write_text(
        json.dumps(
            {
                "generated": now_iso,
                "nodes": [
                    {"id": m.theme, "domain": m.domain, "state": m.state, "volume": m.volume}
                    for m in metrics
                ],
                "edges": edges,
            },
            indent=2,
        )
    )

    (docs_data_dir / "items.json").write_text(
        json.dumps(
            {
                "generated": now_iso,
                "items": [
                    {"date": d, "theme": t, "source_class": c, "source_name": n}
                    for d, t, c, n in all_entries
                ],
            },
            indent=2,
        )
    )

    (docs_data_dir / "sources.json").write_text(
        json.dumps(
            {
                "generated": now_iso,
                "classes": source_class_info,
                "sources": source_list,
            },
            indent=2,
        )
    )

    logger.info(
        "Trend analysis complete: %d themes, %d graph edges → %s",
        len(metrics),
        len(edges),
        docs_data_dir,
    )
    _preview(metrics[:5])


def _preview(metrics: list[TrendMetrics]) -> None:
    for m in metrics:
        logger.info(
            "  %-35s  state=%-10s  vol=%.1f  vel=%+.2f  div=%d  hype=%.0f%%",
            m.theme,
            m.state,
            m.volume,
            m.velocity,
            m.diversity,
            m.hype_risk * 100,
        )


# ── CLI ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trend analysis pipeline")
    parser.add_argument("--docs", default="docs/data", help="Path to docs/data/ directory")
    parser.add_argument("--history", default="history", help="Path to history/ directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview output without writing files"
    )
    parser.add_argument(
        "--no-fetch", action="store_true", help="Skip live source fetching; history only"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    setup_logging(debug=args.debug)

    repo_root = Path(__file__).parent.parent
    docs_data_dir = Path(args.docs) if Path(args.docs).is_absolute() else repo_root / args.docs
    history_dir = (
        Path(args.history) if Path(args.history).is_absolute() else repo_root / args.history
    )

    if not history_dir.exists():
        logger.error("History directory not found: %s", history_dir)
        sys.exit(1)

    run(
        docs_data_dir=docs_data_dir,
        history_dir=history_dir,
        dry_run=args.dry_run,
        fetch_live=not args.no_fetch,
    )


if __name__ == "__main__":
    main()
