# ADR-0016: GitHub Pages Trend Intelligence Site

Status: Accepted
Date: 2026-04-29
Authors: Claude Code

---

## Context

The existing pipeline archives daily digests as plain text files in `history/`. Gemini already produces a narrative Trends section in each email. However, there is no persistent, queryable view of how themes are evolving across weeks, and no way to separate hype from substantiated claims.

The system needs:
1. A public, always-up-to-date website showing trend state per theme
2. Structured data files the site can consume (pipeline writes → site reads)
3. No new infrastructure: must work within the existing GitHub Actions + free-tier constraint

## Decision

### GitHub Pages site in `/docs`

Host a static site at `docs/` (GitHub Pages "docs folder" source setting). The site is pure HTML/CSS/vanilla JS — no build step, no framework. Chart.js is loaded from CDN for visualisations.

### Data contract: `docs/data/*.json`

The trend analysis pipeline writes six JSON files after each daily run:

| File | Contents |
|---|---|
| `meta.json` | last_run timestamp, item/theme counts |
| `trends.json` | per-theme TrendMetrics with rolling history |
| `themes.json` | ThemeNode list with definitions, source class counts |
| `graph.json` | relationship graph nodes + edges |
| `items.json` | canonical records for last 30 days |
| `sources.json` | per-source-class coverage stats |

The site reads these files with `fetch()` at page load and degrades gracefully when files are empty (pipeline hasn't run yet).

### Source class taxonomy

Every `FetchedItem` carries a `source_class` field:

| Class | Description | Existing sources |
|---|---|---|
| `primary` | Papers, benchmarks, model cards | (future: arXiv, Papers with Code) |
| `operator` | Vendor changelogs, pricing, APIs | (future: OpenAI/Anthropic RSS) |
| `practitioner` | Blogs, HN, conference talks | YouTube, Hacker News |
| `media` | Press, newsletters, analysis | Substack |
| `market` | Funding, filings, job postings | (future) |

### Trend analysis pipeline (`src/trends.py`)

Runs as a new step in `daily-digest.yml` after the email is sent, using `GEMINI_API_KEY`. Steps:

1. Load last 14 days of `history/*.txt`
2. Extract `CanonicalRecord` per item via Gemini (claim, evidence_type, domain, technique, impact_vector, actors)
3. Score credibility (5-axis: proximity, incentive, reproducibility, adoption, time_decay)
4. Detect hype (language intensity × evidence density proxy)
5. Cluster into canonical themes via Gemini + synonym normalization
6. Extract relationship graph (causal, competitive, compositional, contradictory edges)
7. Compute rolling `TrendMetrics` and classify state (emerging/scaling/mature/declining)
8. Write `docs/data/*.json` and commit (triggers Pages rebuild)

### Trend state machine

A theme reaches a non-`unknown` state only when:
- At least 2 distinct source classes represented (cross-class confirmation)
- Consistent signal across ≥ 2 items

States: `emerging` (high velocity, low volume) → `scaling` (high velocity, growing volume) → `mature` (stable, high adoption) → `declining` (falling velocity).

## Consequences

**Positive:**
- Zero new infrastructure — GitHub Actions + Pages are already free
- Data lives in the repo (consistent with state/processed.json pattern)
- Each push to `docs/data/` triggers automatic Pages rebuild
- Graceful degradation: site is usable from day 1 with placeholder data
- New sources (arXiv, Hugging Face) can be added incrementally with one config entry each

**Negative:**
- Gemini API costs: trend extraction adds ~2 API calls per run (bounded by history window)
- No server-side rendering or search — purely client-side JS
- Theme boundaries drift as terminology evolves; requires periodic human review

## Alternatives considered

- **Separate workflow for trends**: rejected — two commits per day is noisier; the main digest workflow already has `contents: write`
- **Jekyll or Hugo**: rejected — adds build complexity with no benefit given the simple data-driven layout
- **External database (Supabase, Firebase)**: rejected — violates the zero-infrastructure constraint

## Related ADRs

- ADR-0003: GitHub Actions for scheduling
- ADR-0008: Optional AI summarisation
- ADR-0014: History archiving and trend analysis
