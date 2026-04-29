# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
