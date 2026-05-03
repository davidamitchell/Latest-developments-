"""TDD tests for src/site/build.py — site build as a pure ProcessedItem consumer.

build.py reads data/processed/*.jsonl, computes trend metrics from the structured
fields on ProcessedItem (theme, source_class, etc.), and writes docs/data/*.json.
It must not import any fetcher or pipeline stage directly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.models import ProcessedItem


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_processed(
    id_: str = "item-1",
    theme: str = "inference scaling",
    domain: str = "infra",
    source_class: str = "practitioner",
    source_name: str = "Hacker News",
    fetch_date: str = "2026-05-02",
    credibility_score: float = 0.65,
    hype_risk: float = 0.2,
) -> ProcessedItem:
    return ProcessedItem(
        id=id_,
        title=f"Title {id_}",
        url=f"https://example.com/{id_}",
        source_name=source_name,
        source_type="rss",
        source_class=source_class,
        author="Alice",
        published=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        has_code=False,
        evidence_type="analysis",
        fetch_date=fetch_date,
        cleaned_content="Content about AI.",
        theme=theme,
        domain=domain,
        summary="A summary.",
        credibility_score=credibility_score,
        hype_risk=hype_risk,
    )


def _write_processed_jsonl(items: list[ProcessedItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for item in items:
            f.write(json.dumps(item.to_dict()) + "\n")


# ── load_processed_items ─────────────────────────────────────────────────────

class TestLoadProcessedItems:
    """load_processed_items(data_dir, window_days) → list[ProcessedItem]"""

    def test_returns_list(self, tmp_path):
        from src.site.build import load_processed_items

        result = load_processed_items(tmp_path / "processed", window_days=30)
        assert isinstance(result, list)

    def test_loads_items_from_jsonl_files(self, tmp_path):
        from src.site.build import load_processed_items

        proc_dir = tmp_path / "processed"
        items = [_make_processed("a"), _make_processed("b")]
        _write_processed_jsonl(items, proc_dir / "2026-05-02.jsonl")

        result = load_processed_items(proc_dir, window_days=30)
        assert len(result) == 2
        assert {r.id for r in result} == {"a", "b"}

    def test_loads_multiple_files(self, tmp_path):
        from src.site.build import load_processed_items

        proc_dir = tmp_path / "processed"
        _write_processed_jsonl([_make_processed("d1", fetch_date="2026-05-01")], proc_dir / "2026-05-01.jsonl")
        _write_processed_jsonl([_make_processed("d2", fetch_date="2026-05-02")], proc_dir / "2026-05-02.jsonl")

        result = load_processed_items(proc_dir, window_days=30)
        assert len(result) == 2

    def test_returns_empty_for_missing_directory(self, tmp_path):
        from src.site.build import load_processed_items

        result = load_processed_items(tmp_path / "no-such-dir", window_days=30)
        assert result == []

    def test_all_results_are_processed_items(self, tmp_path):
        from src.site.build import load_processed_items

        proc_dir = tmp_path / "processed"
        _write_processed_jsonl([_make_processed("x")], proc_dir / "2026-05-02.jsonl")

        result = load_processed_items(proc_dir, window_days=30)
        assert all(isinstance(r, ProcessedItem) for r in result)


# ── items_to_entries ─────────────────────────────────────────────────────────

class TestItemsToEntries:
    """items_to_entries(items) → list of (date_str, theme, source_class, source_name) tuples."""

    def test_returns_list_of_tuples(self):
        from src.site.build import items_to_entries

        items = [_make_processed("a", theme="inference scaling")]
        result = items_to_entries(items)
        assert isinstance(result, list)
        assert len(result) == 1
        assert len(result[0]) == 4

    def test_tuple_fields_correct(self):
        from src.site.build import items_to_entries
        from src.themes import normalize_theme_name

        item = _make_processed("a", theme="LLM agents", source_class="primary",
                               source_name="arXiv", fetch_date="2026-05-02")
        date_str, theme, cls, name = items_to_entries([item])[0]
        assert date_str == "2026-05-02"
        assert theme == normalize_theme_name("LLM agents")
        assert cls == "primary"
        assert name == "arXiv"

    def test_skips_items_with_no_theme(self):
        from src.site.build import items_to_entries

        item = _make_processed("a", theme="")
        result = items_to_entries([item])
        assert result == []

    def test_empty_input_returns_empty(self):
        from src.site.build import items_to_entries

        assert items_to_entries([]) == []

    def test_multiple_items_all_included(self):
        from src.site.build import items_to_entries

        items = [_make_processed(f"i{n}", theme=f"theme-{n}") for n in range(5)]
        result = items_to_entries(items)
        assert len(result) == 5


# ── write_site_data ──────────────────────────────────────────────────────────

class TestWriteSiteData:
    """write_site_data(metrics, theme_nodes, source_list, edges, docs_data_dir)"""

    def _make_minimal_inputs(self):
        from src.models import TrendMetrics, ThemeNode
        metrics = [
            TrendMetrics(theme="inference scaling", domain="infra", state="emerging",
                        volume=3.0, velocity=0.2, diversity=2, item_count=4)
        ]
        theme_nodes = [
            ThemeNode(name="inference scaling", domain="infra", state="emerging", item_count=4)
        ]
        source_list = [
            {"name": "arXiv", "source_class": "primary", "item_count": 4,
             "first_seen": "2026-05-01", "last_seen": "2026-05-02",
             "days_active": 2, "top_themes": ["inference scaling"]}
        ]
        edges = [{"source": "inference scaling", "target": "agentic RAG",
                  "rel_type": "compositional", "weight": 3}]
        return metrics, theme_nodes, source_list, edges

    def test_creates_docs_data_directory(self, tmp_path):
        from src.site.build import write_site_data

        docs_dir = tmp_path / "docs" / "data"
        metrics, nodes, sources, edges = self._make_minimal_inputs()
        write_site_data(metrics, nodes, sources, edges, docs_dir)
        assert docs_dir.exists()

    def test_writes_meta_json(self, tmp_path):
        from src.site.build import write_site_data

        docs_dir = tmp_path / "docs" / "data"
        metrics, nodes, sources, edges = self._make_minimal_inputs()
        write_site_data(metrics, nodes, sources, edges, docs_dir)
        assert (docs_dir / "meta.json").exists()
        data = json.loads((docs_dir / "meta.json").read_text())
        assert "last_run" in data
        assert "theme_count" in data

    def test_writes_trends_json(self, tmp_path):
        from src.site.build import write_site_data

        docs_dir = tmp_path / "docs" / "data"
        metrics, nodes, sources, edges = self._make_minimal_inputs()
        write_site_data(metrics, nodes, sources, edges, docs_dir)
        assert (docs_dir / "trends.json").exists()
        data = json.loads((docs_dir / "trends.json").read_text())
        assert "trends" in data
        assert len(data["trends"]) == 1
        assert data["trends"][0]["theme"] == "inference scaling"

    def test_writes_themes_json(self, tmp_path):
        from src.site.build import write_site_data

        docs_dir = tmp_path / "docs" / "data"
        metrics, nodes, sources, edges = self._make_minimal_inputs()
        write_site_data(metrics, nodes, sources, edges, docs_dir)
        assert (docs_dir / "themes.json").exists()
        data = json.loads((docs_dir / "themes.json").read_text())
        assert "themes" in data

    def test_writes_sources_json(self, tmp_path):
        from src.site.build import write_site_data

        docs_dir = tmp_path / "docs" / "data"
        metrics, nodes, sources, edges = self._make_minimal_inputs()
        write_site_data(metrics, nodes, sources, edges, docs_dir)
        assert (docs_dir / "sources.json").exists()
        data = json.loads((docs_dir / "sources.json").read_text())
        assert "sources" in data

    def test_writes_graph_json(self, tmp_path):
        from src.site.build import write_site_data

        docs_dir = tmp_path / "docs" / "data"
        metrics, nodes, sources, edges = self._make_minimal_inputs()
        write_site_data(metrics, nodes, sources, edges, docs_dir)
        assert (docs_dir / "graph.json").exists()
        data = json.loads((docs_dir / "graph.json").read_text())
        assert "edges" in data
        assert "nodes" in data

    def test_writes_items_json(self, tmp_path):
        from src.site.build import write_site_data

        docs_dir = tmp_path / "docs" / "data"
        metrics, nodes, sources, edges = self._make_minimal_inputs()
        write_site_data(metrics, nodes, sources, edges, docs_dir, items=[_make_processed("item-1")])
        assert (docs_dir / "items.json").exists()
        data = json.loads((docs_dir / "items.json").read_text())
        assert "items" in data


# ── build (integration) ──────────────────────────────────────────────────────

class TestBuild:
    """build(processed_dir, docs_data_dir, window_days, dry_run) → writes docs/data/"""

    def _setup_processed_data(self, tmp_path) -> Path:
        proc_dir = tmp_path / "data" / "processed"
        items = [
            _make_processed("a1", theme="inference scaling", source_class="primary",
                            source_name="arXiv", fetch_date="2026-05-01"),
            _make_processed("a2", theme="inference scaling", source_class="practitioner",
                            source_name="Hacker News", fetch_date="2026-05-01"),
            _make_processed("b1", theme="agentic RAG", source_class="operator",
                            source_name="Anthropic", fetch_date="2026-05-02"),
            _make_processed("b2", theme="agentic RAG", source_class="practitioner",
                            source_name="YouTube", fetch_date="2026-05-02"),
        ]
        _write_processed_jsonl(items[:2], proc_dir / "2026-05-01.jsonl")
        _write_processed_jsonl(items[2:], proc_dir / "2026-05-02.jsonl")
        return proc_dir

    def test_build_writes_output_files(self, tmp_path):
        from src.site.build import build

        proc_dir = self._setup_processed_data(tmp_path)
        docs_dir = tmp_path / "docs" / "data"

        build(processed_dir=proc_dir, docs_data_dir=docs_dir, window_days=30, dry_run=False)

        assert (docs_dir / "meta.json").exists()
        assert (docs_dir / "trends.json").exists()
        assert (docs_dir / "themes.json").exists()
        assert (docs_dir / "sources.json").exists()
        assert (docs_dir / "graph.json").exists()
        assert (docs_dir / "items.json").exists()

    def test_build_dry_run_does_not_write(self, tmp_path):
        from src.site.build import build

        proc_dir = self._setup_processed_data(tmp_path)
        docs_dir = tmp_path / "docs" / "data"

        build(processed_dir=proc_dir, docs_data_dir=docs_dir, window_days=30, dry_run=True)

        assert not (docs_dir / "meta.json").exists()

    def test_build_themes_in_output(self, tmp_path):
        from src.site.build import build
        from src.themes import normalize_theme_name

        proc_dir = self._setup_processed_data(tmp_path)
        docs_dir = tmp_path / "docs" / "data"

        build(processed_dir=proc_dir, docs_data_dir=docs_dir, window_days=30, dry_run=False)

        data = json.loads((docs_dir / "trends.json").read_text())
        theme_names = [t["theme"] for t in data["trends"]]
        assert normalize_theme_name("inference scaling") in theme_names
        assert normalize_theme_name("agentic RAG") in theme_names

    def test_build_with_empty_data_succeeds(self, tmp_path):
        from src.site.build import build

        proc_dir = tmp_path / "data" / "processed"
        proc_dir.mkdir(parents=True)
        docs_dir = tmp_path / "docs" / "data"

        # Should not raise even with no data
        build(processed_dir=proc_dir, docs_data_dir=docs_dir, window_days=30, dry_run=False)

    def test_build_does_not_import_fetchers(self):
        """build.py must not import any fetcher or pipeline stage."""
        import src.site.build as build_module
        assert build_module is not None
