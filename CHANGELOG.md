# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- **W-0008 — Papers with Code fetcher** (`src/fetchers/paperswithcode.py`): fetches trending papers from the Papers with Code JSON API as `source_class="primary"` with `has_code=True`. 10 tests in `tests/test_fetchers_paperswithcode.py`.
- **W-0009 — Operator changelog fetcher** (`src/fetchers/operator_changelog.py`): fetches 6 AI lab RSS feeds (Anthropic, OpenAI, Google AI, DeepMind, AWS ML, Microsoft AI) as `source_class="operator"`. 6 tests in `tests/test_fetchers_operator_changelog.py`.
- **W-0010 — Replicate fetcher** (`src/fetchers/replicate.py`): fetches popular public models from the Replicate API ordered by run count as `source_class="operator"`. 8 tests in `tests/test_fetchers_replicate.py`.
- **W-0011 — OpenReview fetcher** (`src/fetchers/openreview.py`): fetches accepted papers from ICLR/NeurIPS/ICML 2025 via the OpenReview API as `source_class="primary"`, `evidence_type="experiment"`. 9 tests in `tests/test_fetchers_openreview.py`.
- `has_code: bool = False` field on `FetchedItem` and `CanonicalRecord`; when `True`, credibility scoring sets `reproducibility=1.0`.
- `evidence_type: str = ""` field on `FetchedItem` (mirrors `CanonicalRecord.evidence_type` for fetcher-level signal).
- `PapersWithCodeConfig`, `OperatorChangelogConfig`, `ReplicateConfig`, `OpenReviewConfig` added to `src/config.py` and `TrendsConfig`.
- All four sources added to `config/sources.yaml` under `trends.*` (`enabled: false` by default).
- All four fetchers wired into `src/trends.py`.
- **Per-theme unique colour system**: every theme is assigned a unique, maximally-contrasting hex colour from a 20-slot palette. The same colour is used everywhere that theme appears — trend chart lines, hype bar charts, trend table swatch, theme card border and name, heatmap row label, source table theme pills. Assignment is deterministic (alphabetical sort before palette slot), so colours are stable across page reloads.
- **Dark mode GitHub Pages site**: converted `docs/` dashboard to dark mode using IBM Plex Mono font and Research site palette (`#0d0d0d` bg, `#00C3A5` teal, `#E8A1A8` dusk, `#252b33` borders)
- `learnings.md`: session notes capturing patterns, friction, and root causes

### Fixed
- **CodeQL unused imports** removed from `src/credibility.py` (`SourceClass`), `src/fetchers/arxiv.py` (`UTC`), `src/models.py` (`datetime`), `src/trends.py` (`compute_velocity`), `tests/test_fetchers_arxiv.py` (`UTC`, `datetime`, `pytest`)
- **CodeQL unused globals** removed from `src/fetchers/arxiv.py` (`_NS_ATOM`, `_ARXIV_NS`)
- **CodeQL empty except** in `src/fetchers/arxiv.py` replaced with `contextlib.suppress` and explanatory comment
- Additional ruff lint fixes in `src/fetchers/huggingface.py`, `tests/test_fetchers_huggingface.py`, `src/summariser.py` (F401, SIM105, N806)

### Added
- **GitHub Pages trend intelligence site** (`docs/index.html`, `docs/css/`, `docs/js/`): static dashboard showing themes, trend states, hype vs substantiation split, and source-class coverage heatmap — auto-updated daily
- **Trend analysis pipeline** (`src/trends.py`): reads history, extracts canonical records via Gemini, clusters themes, computes rolling trend metrics, writes structured JSON to `docs/data/`
- **Canonical record model** (`src/models.py`): `CanonicalRecord`, `TrendMetrics`, `ThemeNode`, `GraphEdge` dataclasses
- **Credibility scoring** (`src/credibility.py`): 5-axis scoring (proximity, incentive, reproducibility, adoption, time decay); hype detection (evidence density × source incentive)
- **Theme clustering** (`src/themes.py`): Gemini-powered clustering with synonym normalization, domain taxonomy enforcement, relationship graph extraction
- **Trend state machine** (`src/trend_state.py`): `classify_state()` with emerging/scaling/mature/declining states; cross-class confirmation gate (diversity ≥ 2 required)
- `source_class` field on `FetchedItem` and all fetchers (`practitioner` for YouTube/HN, `media` for Substack, configurable for RSS)
- `source_class` field on `RSSFeed` config (defaults to `"practitioner"`; set in `sources.yaml`)
- **ADR-0016**: documents GitHub Pages architecture and data contract
- Trend analysis step in `daily-digest.yml`: runs `python -m src.trends` after digest, commits `docs/data/` alongside state and history
- `.github/copilot-instructions.md`: unified **Continuous Improvement & Learning** framework (supersedes old Mini-Retro and Continuous Improvement — Always On sections)
- `.github/copilot-instructions.md`: **Chain-of-Thought Reasoning** section with 7 pipeline-specific reasoning steps
- `PROGRESS.md` entry for 2026-03-07 session

### Changed
- `.github/copilot-instructions.md`: replaced "Mini-Retro — After Each Piece of Work" and "Continuous Improvement — Always On" sections with unified **Continuous Improvement & Learning** framework

### Removed
- `.github/copilot-instructions.md`: old "Mini-Retro — After Each Piece of Work" section (superseded by unified framework)
- `.github/copilot-instructions.md`: old "Continuous Improvement — Always On" section (superseded by unified framework)
