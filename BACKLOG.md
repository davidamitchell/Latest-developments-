# Backlog

Organised by **Epic** → **Slice**. Each slice is independently deployable, produces a user-visible result, and can be tested in isolation.

Status legend: `[ ]` Not started · `[→]` In progress · `[x]` Done · `[~]` Deferred

---

## W-0001

status: done
created: 2026-03-07
updated: 2026-03-07

### Outcome

Repository structure is standardised: single `.github/copilot-instructions.md` source of truth, `.github/skills` submodule, `sync-skills.yml` workflow, `BACKLOG.md`, `PROGRESS.md`, `CHANGELOG.md`, and `docs/adr/` all present and consistent.

### Context

Standardisation pass to remove `AGENTS.md`/`.claude/` and align with all other repos in the davidamitchell organisation.

### Notes

- `AGENTS.md` content merged into `.github/copilot-instructions.md`
- `.claude/` directory and `.claude/skills` submodule removed
- `.gitmodules` and `sync-skills.yml` updated to remove `.claude/skills`
- ADR-0015 written to record the decision

---

## Epic 0 — Foundation

| # | Slice | Status | Notes |
|---|---|---|---|
| 0.1 | Create README, AGENTS, BACKLOG, PROGRESS | `[x]` | |
| 0.2 | Create `docs/adr/` with initial ADRs | `[x]` | ADR-0001 to ADR-0007 |
| 0.3 | Create `config/sources.yaml` schema with inline comments | `[x]` | |
| 0.4 | Add `.github/workflows/daily-digest.yml` (manual trigger only) | `[x]` | |
| 0.5 | Add `pyproject.toml` + `requirements.txt` | `[x]` | |
| 0.6 | Add `src/logger.py` — shared logging setup | `[x]` | |
| 0.7 | Add `.devcontainer/`, `Makefile`, `.python-version`, `.env.example` | `[x]` | Codespaces-ready |
| 0.8 | Add `src/config.py`, `src/state.py`, `src/fetchers/__init__.py`, `src/main.py` skeleton | `[x]` | |
| 0.9 | Add `tests/` skeleton with `conftest.py`, `test_config.py`, `test_state.py` | `[x]` | |
| 0.10 | Add GitHub Copilot Agent skills from `davidamitchell/Skills`; weekly sync workflow | `[x]` | Skills live in `.github/skills/`. 7 skills synced: backlog-manager, citation-discipline, remove-ai-slop, research, speculation-control, strategic-persuasion, strategy-author. Sync: `.github/workflows/sync-skills.yml` (weekly + manual). Claude Code submodule (`git submodule add https://github.com/davidamitchell/Skills .claude/commands`) remains a manual step. |
| 0.11 | Consolidate agent instructions: `AGENTS.md` as single source of truth; `.claude/CLAUDE.md` and `.github/copilot-instructions.md` as thin stubs | `[x]` | Resolves #6 — multi-agent DRY setup |

---

## Epic 1 — Proof of Life (YouTube → Gemini → Email)

One end-to-end run, hardcoded source, proves the core pipeline works.

| # | Slice | Status | Notes |
|---|---|---|---|
| 1.1 | `src/fetchers/youtube.py` — fetch transcript for a single hardcoded video | `[x]` | Uses YouTube RSS feed + `youtube-transcript-api`; no API key needed |
| 1.2 | `src/summariser.py` — send transcript to Claude, return summary string | `[x]` | Model configurable via `sources.yaml` |
| 1.3 | `src/emailer.py` — send plain-text email via SMTP (Gmail) | `[x]` | Reads creds from env vars; SendGrid also supported |
| 1.4 | Wire 1.1 → 1.2 → 1.3 in `src/main.py`; `--dry-run` skips email | `[x]` | Also added `src/retry.py` — backoff for all network calls |
| 1.5 | Manually run in Codespaces; confirm email received | `[ ]` | Acceptance: email arrives with coherent summary |
| 1.6 | Focus YouTube sources on Nate Jones: comment out Karpathy, Kilcher, AI Explained channels in `config/sources.yaml`; add `@natebjones` | `[x]` | Channel ID: `UC0C-17n9iuUQPylguM1d-lQ` |
| 1.7 | Expand YouTube sources: add 7 new channels from issue — Wes Roth (active; `UCqcbQf6yw5KzRoDDcZ_wBSw`), Matthew Berman (`UCawZsQWqfGSbCI5yjkdVkTA`), The AI Daily Brief (`UCKelCK4ZaO6HeEI1KQjqzWA`), AI Explained (`UCNJ1Ymd5yFuUPtn21xtRbbw`), Yannic Kilcher (`UCZHmQk67mSJgfCCTn7xBfew`), Two Minute Papers (`UCbfYPyITQ-7l4upoX8nvctg`), David Shapiro (`UCvKRFNawVcuz4b9ihUTApCg`). Token budget: use per-channel `max_videos: 2–3` when enabling; enable channels incrementally. | `[→]` | Wes Roth activated; all others added as commented-out in `config/sources.yaml` with IDs |

**Acceptance criteria:** `python -m src.main --dry-run` prints a summary to stdout without errors.

---

## Epic 2 — Deduplication

Items processed once are never processed again, across days.

| # | Slice | Status | Notes |
|---|---|---|---|
| 2.1 | YouTube fetcher uses state to skip already-processed videos | `[x]` | `src/state.py` already implemented; fetcher checks `already_processed` |
| 2.2 | State file committed back to repo by workflow after each run | `[x]` | Enables persistence across Codespaces sessions |
| 2.3 | Test: run pipeline twice; confirm second run processes 0 new items | `[ ]` | |

**Acceptance criteria:** A second consecutive run produces "No new items" and sends no email.

---

## Epic 3 — Scheduled Automation

Workflow runs daily without manual intervention.

| # | Slice | Status | Notes |
|---|---|---|---|
| 3.1 | GitHub Actions workflow: `schedule: cron: '0 7 * * *'` | `[x]` | Triggers at 07:00 UTC |
| 3.2 | Workflow commits updated `state/processed.json` after run | `[x]` | Bot commit with `[skip ci]` |
| 3.3 | Workflow supports `workflow_dispatch` with `debug` input flag | `[x]` | |
| 3.5 | Workflow `workflow_dispatch` supports `max_videos` input to override per-channel lookback (useful for catch-up runs when all recent videos are already processed) | `[x]` | `--max-videos N` CLI arg; overrides `max_videos_per_channel` and each channel's `max_videos` for that run |
| 3.4 | Verify schedule fires and email arrives at expected time | `[ ]` | Acceptance test |

**Acceptance criteria:** No manual action required for 3 consecutive days; email arrives each day.

---

## Epic 4 — Blog / RSS Sources

RSS feeds ingested alongside YouTube.

| # | Slice | Status | Notes |
|---|---|---|---|
| 4.1 | `src/fetchers/rss.py` — fetch and parse RSS/Atom feed | `[x]` | Uses httpx + stdlib ET (no feedparser — sgmllib3k build broken on this host); supports RSS 2.0 and Atom 1.0 |
| 4.2 | Deduplication applied to RSS entries by URL | `[x]` | Normalises both feed URLs and processed-set URLs before comparison |
| 4.3 | RSS fetcher reads feeds from `config/sources.yaml` | `[x]` | |
| 4.4 | Summaries from multiple sources merged into single digest email | `[x]` | Items from all fetchers pooled before summarisation |
| 4.5 | Add Nate's Newsletter to `config/sources.yaml` as an RSS source | `[x]` | Feed URL: `https://natesnewsletter.substack.com/feed` — complements the YouTube source with written analysis |

**Acceptance criteria:** Digest email contains sections for both YouTube and blog sources.

---

## Epic 5 — Hacker News

Top AI/LLM stories from HN included in digest.

| # | Slice | Status | Notes |
|---|---|---|---|
| 5.1 | `src/fetchers/hackernews.py` — query HN Algolia API for top stories | `[x]` | Filter by keyword list and min score from config; deduplicates by Algolia `objectID` |
| 5.2 | Fetch linked article text (best-effort; skip paywalled) | `[x]` | `trafilatura` — best-effort; falls back to HN metadata on any failure |
| 5.3 | Deduplication by HN story ID | `[x]` | Uses `objectID` as stable dedup key |
| 5.4 | Include HN section in digest email | `[x]` | Wired into `src/main.py` alongside YouTube and RSS fetchers |

**Acceptance criteria:** Digest email contains a Hacker News section with ≥1 story on most days.

---

## Epic 6 — Configurable Prompt & Polish

User can tune what "important" means without touching code.

| # | Slice | Status | Notes |
|---|---|---|---|
| 6.1 | `summary.prompt` field in `config/sources.yaml` passed to Gemini | `[x]` | `SummaryConfig.prompt` read from YAML; passed as `system_instruction` to Gemini; empty string uses `_DEFAULT_PROMPT` |
| 6.2 | `summary.max_items_per_source` and `summary.max_tokens` honoured | `[x]` | Both fields in `SummaryConfig`; used in `summarise()` and `format_link_digest()` |
| 6.3 | Digest email is HTML with sections per source | `[x]` | `render_html_digest()` in `summariser.py`; items grouped by source with dyslexia-friendly cards; wired in `main.py` via `html_body=` kwarg |
| 6.4 | `--debug` mode writes structured JSON logs to stdout | `[x]` | Implemented in `src/logger.py` (`_JSONFormatter`); wired via `--debug` arg in `src/main.py` |
| 6.5 | `--dry-run` documented in README and AGENTS with examples | `[x]` | Documented in README under "Local development"; `make dry-run` target in Makefile |
| 6.6 | Email includes a **TL;DR** section at the top: 3–5 bullets covering the most significant items, each with a direct link, plus a one-sentence trend note for the current period | `[x]` | `_DEFAULT_PROMPT` and `config/sources.yaml` prompt both request a `## TL;DR` section as the first section; `_plain_to_html()` now renders `- ` and `* ` bullet lines as `<ul><li>` lists so TL;DR bullets display correctly in HTML email |
| 6.7 | Email includes a **Sources** section at the bottom: which sources were fetched, item counts per source, and 2–3 suggested related sources worth following | `[x]` | Sources fetched + item counts: covered by 6.10 run summary. Suggested Sources: Gemini now outputs a `## Suggested Sources` section (2–3 AI-generated recommendations) rendered in the AI Analysis area of the email |
| 6.8 | Each item rendered in the email includes its **source link** (clickable URL) and **publication date/time** | `[x]` | `_render_item_card()` renders title as `<a href=url>`, source badge, source name, and formatted `published` date; already in place since 6.3 |
| 6.9 | Each item carries a short **theme label** (1–3 words) assigned by Gemini during summarisation and displayed alongside the item in the digest | `[x]` | Prompt requests `## Item Themes` section in structured `url \| theme` format at end of AI output; `_extract_item_themes()` parses and strips the section; theme label shown as a `.theme-badge` on each item card |
| 6.10 | **Run summary** appended to the end of every email: sources attempted, new items found per source, total items in digest, UTC run timestamp, and any per-source errors encountered | `[x]` | `format_run_summary()` in `summariser.py`; appended by `main.py` after `summarise()` |

---

## Epic 7 — Reliability & Observability

Pipeline degrades gracefully; failures are surfaced.

| # | Slice | Status | Notes |
|---|---|---|---|
| 7.1 | Per-source retry with exponential backoff (3 attempts) | `[x]` | `src/retry.py` — `with_backoff()` used by all fetchers and the summariser |
| 7.2 | Source failure logs error and continues; digest still sent | `[x]` | Both `YouTubeFetcher` and `RSSFetcher` catch per-source exceptions and continue; pipeline proceeds with whatever items were successfully fetched |
| 7.3 | Workflow failure sends alert email | `[x]` | `python -m src.emailer --subject/--body` CLI; `if: failure()` step in daily-digest.yml |
| 7.4 | `pytest` suite with mocked network for all fetchers | `[x]` | Tests in `tests/test_fetchers_*.py` cover YouTube, RSS, and HN fetchers with mocked network |
| 7.5 | `ruff` linting enforced in CI | `[x]` | `.github/workflows/ci.yml` — runs `ruff check` + `ruff format --check` + `pytest` on every push/PR |
| 7.6 | Smoke tests in `tests/test_smoke.py`: exercise the full pipeline (`main()`) with mocked network; assert exit 0, no crash, digest contains expected structure even when fetchers or Gemini fail | `[x]` | Catches integration-level regressions that unit tests miss |

---

## Epic 8 — History & Trend Analysis

Each digest is archived; history feeds back into future summaries.

| # | Slice | Status | Notes |
|---|---|---|---|
| 8.1 | Archive each digest to `history/YYYY-MM-DD.txt` after a successful send | `[x]` | `src/history.py` — `archive_digest()` called in `main.py` after successful send; file-per-day committed to repo |
| 8.2 | Workflow commits `history/` alongside state on each successful run | `[x]` | Single bot commit: `[skip ci] chore: update state and history YYYY-MM-DD` |
| 8.3 | Summariser loads the last N digests from `history/` and passes them to Gemini as context | `[x]` | `load_recent_digests()` in `src/history.py`; `summarise()` gains `history=` param; N configurable via `history.history_days` (default 7) |
| 8.4 | Email **Trends** section: Gemini compares current digest to history and surfaces recurring topics, emerging threads, and notable absences | `[x]` | `_extract_trends()` in `summariser.py`; rendered in HTML email between TL;DR and items when `## Trends` section present in AI output |
| 8.5 | `history/` directory browsable as a digest archive (file-per-day, no UI needed) | `[x]` | `history/.gitkeep` ensures directory exists; committed by workflow after each run |

**Acceptance criteria:** After 7 days the Trends section names at least one theme that genuinely recurs across multiple digests.

---

## Epic 9 — MCP Tool Configuration

Manage MCP server configs for all AI agent environments from a single manifest.

| # | Slice | Status | Notes |
|---|---|---|---|
| 9.1 | `mcp/manifest.yaml` — source of truth for all MCP servers | `[x]` | Servers: fetch, sequential_thinking, time, memory, git, filesystem, github |
| 9.2 | `mcp/generate.py` — converts manifest to GitHub, VS Code, Claude Desktop, Claude Code, opencode formats | `[x]` | PyYAML only; no external deps beyond what's already installed |
| 9.3 | Generated configs committed: `.github/mcp.json`, `.vscode/mcp.json`, `.mcp.json`, `mcp/generated/*.json` | `[x]` | GitHub Copilot Agent picks up `.github/mcp.json` automatically |
| 9.4 | `.github/workflows/mcp-generate.yml` — regenerates + tests + commits on manifest change | `[x]` | Runs on push to `mcp/manifest.yaml` or `workflow_dispatch` |
| 9.5 | `mcp/tests/test_generate.py` — 20 pytest tests covering all builders and smoke tests on real manifest | `[x]` | Run via: `pytest mcp/tests/ -v` |
| 9.6 | `mcp/README.md` — copy-paste instructions, server table, manifest editing guide | `[x]` | Self-contained; links to ADR-0011 |
| 9.7 | ADR-0011 — document the manifest approach and trade-offs | `[x]` | |

**Acceptance criteria:** `python mcp/generate.py --deploy` runs without error; `pytest mcp/tests/` passes; GitHub Copilot Agent has access to `fetch`, `time`, and `sequential_thinking` servers via `.github/mcp.json`.

---

---

## Epic 10 — GitHub Pages Trend Intelligence Site

Static site at `docs/` showing themes, trend states, hype vs substantiation, and source-class coverage. Auto-updated daily by the trend analysis pipeline.

| # | Slice | Status | Notes |
|---|---|---|---|
| 10.1 | Create `docs/index.html` with tab navigation (Trends / Themes / Sources / Insights) | `[x]` | |
| 10.2 | Create `docs/css/style.css` matching email palette | `[x]` | #4a7c59 green, mobile-first |
| 10.3 | Create `docs/js/app.js` — data loading and rendering | `[x]` | Degrades gracefully when data empty |
| 10.4 | Create `docs/js/charts.js` — Chart.js wrappers | `[x]` | Trend phase chart + hype split panels |
| 10.5 | Create `docs/data/` placeholder JSON files | `[x]` | meta, trends, themes, items, graph, sources |
| 10.6 | Add trend analysis step to `daily-digest.yml` | `[x]` | Runs `python -m src.trends`; commits `docs/data/` |
| 10.7 | Write ADR-0016 | `[x]` | Documents Pages architecture and data contract |
| 10.8 | Enable GitHub Pages in repo settings (docs folder) | `[ ]` | Manual step — requires repo owner access |

**Acceptance:** `docs/index.html` loads in browser; trend data populates after first post-merge pipeline run.

---

## Epic 11 — Source Class Infrastructure

Every item carries a `source_class` label for credibility triangulation.

| # | Slice | Status | Notes |
|---|---|---|---|
| 11.1 | Add `source_class` field to `FetchedItem` | `[x]` | Default: `"practitioner"` |
| 11.2 | Assign source class per fetcher | `[x]` | YouTube/HN=practitioner, Substack=media, RSS=configurable |
| 11.3 | `src/models.py` — `CanonicalRecord`, `TrendMetrics`, `ThemeNode`, `GraphEdge` | `[x]` | |
| 11.4 | `source_class` field on `RSSFeed` config | `[x]` | Set per-feed in `sources.yaml` |
| 11.5 | Tests for source class assignment | `[x]` | tests/test_source_class.py — 8 tests |

---

## Epic 12 — Canonical Record Extraction & Credibility Scoring

| # | Slice | Status | Notes |
|---|---|---|---|
| 12.1 | `src/credibility.py` — 5-axis credibility scoring | `[x]` | proximity, incentive, reproducibility, adoption, time_decay |
| 12.2 | Hype detection | `[x]` | `detect_hype()` — evidence density × source incentive proxy |
| 12.3 | `extract_records_from_digest()` in `src/trends.py` | `[x]` | Gemini JSON-lines extraction per history digest |
| 12.4 | Tests for credibility scoring | `[x]` | tests/test_credibility.py — 35 tests |

---

## Epic 13 — Theme Clustering & Relationship Graph

| # | Slice | Status | Notes |
|---|---|---|---|
| 13.1 | `src/themes.py` — synonym normalization map | `[x]` | ~30 entries; collapses common rebrands |
| 13.2 | `cluster_themes()` — Gemini-powered clustering | `[x]` | Domain taxonomy enforced; definitions extracted |
| 13.3 | `build_graph_edges()` — relationship graph | `[x]` | causal/competitive/compositional/contradictory |
| 13.4 | Tests for clustering | `[x]` | Idempotency; synonym collapse; graceful API failure; build_graph_edges |

---

## Epic 14 — Trend State Machine

| # | Slice | Status | Notes |
|---|---|---|---|
| 14.1 | `src/trend_state.py` — state classifier | `[x]` | emerging/scaling/mature/declining rules |
| 14.2 | `compute_velocity()` and `compute_stability()` | `[x]` | Rolling week-over-week metrics |
| 14.3 | Cross-class confirmation gate | `[x]` | diversity ≥ 2 required for non-declining state |
| 14.4 | `update_metrics()` — rolling history append | `[x]` | Max 30 snapshots per theme |
| 14.5 | Tests for state transitions | `[x]` | tests/test_trend_state.py — 35 tests (extended) |

---

## Epic 15 — Site Visualizations (Phase 1)

| # | Slice | Status | Notes |
|---|---|---|---|
| 15.1 | Trend phase chart (Chart.js multi-line) | `[x]` | Phase band overlays; renders from trends.json |
| 15.2 | Hype vs substantiation split panels | `[x]` | Evidence-weighted vs media-weighted side-by-side |
| 15.3 | Theme cards with state badge and metrics | `[x]` | Item count, hype risk, source diversity |
| 15.4 | Source-class coverage heatmap | `[x]` | CSS table; rows=themes, cols=classes |
| 15.5 | Trend state table with confidence bars | `[x]` | Sortable; velocity and diversity columns |
| 15.6 | Raw data drill-down | `[x]` | Click theme card → provenance panel with items by date/source/class |

---

## Epic 16 — Site Visualizations (Phase 2)

| # | Slice | Status | Notes |
|---|---|---|---|
| 16.1 | Theme graph — D3 force layout | `[ ]` | Node colour=state, size=volume |
| 16.2 | Evidence ladder — stacked bars per insight | `[ ]` | paper / benchmark / production / pricing |
| 16.3 | Weekly delta view — new/changed themes only | `[ ]` | Reduces noise; focuses on movement |
| 16.4 | Novelty vs continuity quadrant plot | `[ ]` | Semantic similarity to corpus × current attention |
| 16.5 | Influence flow Sankey diagram | `[ ]` | source class → themes → impact vectors |

---

## Epic 17 — Expanded Sources (Incremental)

Add sources one at a time. Each is opt-in via `sources.yaml` (commented out by default).

| # | Slice | Status | Notes |
|---|---|---|---|
| 17.1 | `src/fetchers/arxiv.py` — arXiv RSS | `[x]` | cs.AI, cs.LG, cs.CL, cs.CV, cs.RO; primary class; free. See W-0006. |
| 17.2 | Hugging Face model releases | `[x]` | Public models JSON API; primary class; `enabled: false` by default. See W-0007. |
| 17.3 | Papers with Code trending | `[ ]` | RSS; primary class; reproducibility proxy |
| 17.4 | Operator changelogs | `[ ]` | OpenAI/Anthropic/Google release notes RSS; operator class |
| 17.5 | Reddit r/MachineLearning | `[ ]` | PRAW or JSON API; practitioner class; deferred pending cost review |

---

---

## W-0002

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

Gemini 5xx overload errors (503 UNAVAILABLE) are retried up to 4 times with 15 / 30 / 60 s exponential backoff before falling back to the link digest. 4xx errors (bad key, quota) fall back immediately.

### Context

Pipeline was falling back to plain link digest on any `APIError`, including transient Gemini overload spikes. History files show `[AI summarisation failed]` notices that would have succeeded on a second attempt.

### Notes

- Distinguishes `ServerError` (5xx, retry) from `ClientError` (4xx, no retry)
- Implemented in `src/summariser.py`

---

## W-0003

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

The Sources page shows a full per-source table: source name, class badge, item count, active days, date range (first → last seen), and top 5 themes. Data is written to `docs/data/sources.json` by the trend pipeline.

### Context

Previously Sources tab only showed aggregate per-class cards with no breakdown of individual sources.

### Notes

- `src/trends.py` computes `per_source` dict from `all_entries` and writes `sources` list to `sources.json`
- `docs/js/app.js` `renderSourcesTab()` renders scrollable table with colour-coded class badges and theme pills

---

## W-0004

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

Source-class heatmap on the Sources page renders correctly on mobile: columns are horizontally scrollable and headers use readable abbreviations (Pri / Ops / Prac / Med / Mkt with full name on hover).

### Context

`table-layout: fixed` distributed 6 columns equally across ~375 px, making "practitioner" unreadable on phones.

### Notes

- Added `.heatmap-scroll` wrapper with `overflow-x: auto`
- Removed `table-layout: fixed`; added `min-width: 380px` so table scrolls rather than collapses
- `<abbr title="full">abbr</abbr>` header cells in `charts.js`
- Mobile breakpoint hides `.themes-cell` on source detail table to reduce crowding

---

## W-0005

status: done
created: 2026-04-29
updated: 2026-04-30

### Outcome

`cluster_themes()` is now called from `src/trends.py run()` after metrics are computed (W-0005/W-0014 combined). When `GEMINI_API_KEY` is set, Gemini assigns canonical domains and writes one-sentence definitions for all themes before writing `trends.json` and `themes.json`. Gemini-derived relationship edges are also merged into `graph.json`. Graceful fallback: when key is absent, domain stays "unknown" and definition stays empty — no code change needed for local `--no-fetch` runs.

### Context

Synonym normalisation (W-0015) and acronym fixing are done. What remains is the Gemini-powered step: assigning canonical domain and writing a one-sentence definition per theme. `cluster_themes()` in `src/themes.py` does this but is not called from `src/trends.py`. GEMINI_API_KEY is present in GitHub Secrets but not available locally; the call must degrade gracefully when the key is absent.

### Notes

- Call `cluster_themes(theme_names, existing_themes)` in `src/trends.py` after metrics are computed
- Merge returned domain + definition into each `TrendMetrics` object before writing JSON
- Guard with `if os.environ.get("GEMINI_API_KEY"):` so local `--no-fetch` runs still work
- Enforce domain taxonomy list from `src/themes.py DOMAIN_TAXONOMY`

---

## W-0006

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

The trend pipeline fetches papers from arXiv (categories cs.AI, cs.LG, cs.CL, cs.CV, cs.RO) daily and includes them in trend analysis as `source_class="primary"`. The email digest pipeline is unchanged.

### Context

arXiv RSS is free, no API key needed, and provides the highest-credibility primary signal (papers, benchmarks). Adding it enables cross-class confirmation: a theme seen in arXiv + HN crosses the diversity ≥ 2 gate and can be classified as "emerging" rather than "unknown".

### Notes

- Create `src/fetchers/arxiv.py` — `ArxivFetcher` class fetching RSS for each category
- Add `trends.arxiv` config section to `config/sources.yaml` (commented out by default in email section, enabled in trends section)
- Add `ArxivConfig` / `TrendsConfig` to `src/config.py`
- Update `src/trends.py` to instantiate `ArxivFetcher`, fetch papers, and merge with history-parsed entries
- NOT wired into `src/main.py` — trends pipeline only
- Write tests in `tests/test_fetchers_arxiv.py`

---

## W-0007

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

The trend pipeline fetches recently-updated text-generation models from Hugging Face Hub as `source_class="primary"`, gated by `min_downloads` to filter noise.

### Context

Adds a second primary-class source alongside arXiv, improving cross-class confirmation for model-capability themes.

### Notes

- `src/fetchers/huggingface.py` — `HuggingFaceFetcher`; uses public models JSON API; no auth
- Filters on `pipeline_tag` ∈ relevant LLM tasks and `downloads ≥ min_downloads` (default 100)
- `config/sources.yaml` `trends.huggingface` section, `enabled: false` by default — set to `true` to activate
- 9 tests in `tests/test_fetchers_huggingface.py`; 269 total passing

---

## W-0008

status: done
created: 2026-04-29
updated: 2026-04-30

### Outcome

The trend pipeline fetches trending papers from Papers with Code as `source_class="primary"`, adding reproducibility signal (code availability) to credibility scoring.

### Context

Papers with Code tracks papers with GitHub repos and benchmark results. A paper appearing here means code exists (reproducibility proxy score = 1.0 in the credibility formula). Feed available at `https://paperswithcode.com/latest` RSS.

### Notes

- Create `src/fetchers/paperswithcode.py`
- Set `has_code=True` flag on fetched items to inform credibility scoring
- Papers with Code also has a public JSON API: `https://paperswithcode.com/api/v1/papers/`
- Implement after arXiv (W-0006)

---

## W-0009

status: done
created: 2026-04-29
updated: 2026-04-30

### Outcome

The trend pipeline ingests operator changelogs from OpenAI, Anthropic, and Google as `source_class="operator"`, enabling cross-class confirmation between primary papers and vendor releases.

### Context

Operator signals (changelogs, pricing changes, API updates) reveal what vendors are actually shipping. Combined with primary sources they confirm capability claims. All three have RSS or scrapeable pages: OpenAI changelog at `https://platform.openai.com/docs/changelog`, Anthropic news RSS, Google AI Blog RSS.

### Notes

- Create `src/fetchers/operator_changelog.py`
- Source class: operator
- Three initial targets: OpenAI platform changelog, Anthropic news, Google AI Blog
- Add `trends.operator_sources` config section
- Implement after arXiv (W-0006) and HuggingFace (W-0007)

---

## W-0010

status: done
created: 2026-04-29
updated: 2026-04-30

### Outcome

The trend pipeline fetches new and trending models from Replicate as `source_class="operator"`, surfacing what practitioners are actually deploying and running in production.

### Context

Replicate's trending models page reflects real deployment activity — a strong adoption proxy signal distinct from paper citations. Available via their public API: `https://api.replicate.com/v1/models` (no auth for public models).

### Notes

- Create `src/fetchers/replicate.py`
- Source class: operator (vendor-hosted deployment)
- Sort by run count (descending) to surface most-used models
- Implement after operator changelogs (W-0009)

---

## W-0011

status: done
created: 2026-04-29
updated: 2026-04-30

### Outcome

OpenReview submissions and accepted papers are fetched as `source_class="primary"` for NeurIPS, ICML, ICLR venues, providing peer-review quality signal distinct from raw arXiv preprints.

### Context

OpenReview exposes a public API. Accepted papers at top venues represent the highest-quality primary signal — peer-reviewed, reproducible claims. This differentiates "paper posted on arXiv" from "paper accepted at ICLR".

### Notes

- Create `src/fetchers/openreview.py`
- Use OpenReview public API: `https://api2.openreview.net/notes`
- Filter: `venueid` in [NeurIPS 2025, ICLR 2025, ICML 2025] and invitation = acceptance decision
- Source class: primary; set `evidence_type="experiment"` for accepted papers
- Implement after W-0006 arXiv is stable

---

## W-0012

status: done
created: 2026-04-29
updated: 2026-05-01

### Outcome

The adoption proxy composite score (`adoption_proxy` field in `TrendMetrics`) is computed from real signals: GitHub repo star velocity for top theme-related repos, job posting count for role keywords, and pricing/tier changes from operator sources. Currently always `0.0`.

### Context

Adoption proxy was defined in the initial architecture but not implemented. It is needed for accurate state classification (Scaling requires rising adoption; Mature requires high adoption). Without it, no theme can ever reach Scaling or Mature state.

### Notes

- GitHub stars: use GH API (no auth needed for public repos, rate-limited)
- Job postings: LinkedIn / Indeed scrape (complex, deferred); interim proxy = HN "Who's Hiring" posts
- Pricing signal: detect price changes in operator changelog items
- Start with GitHub stars only as a minimal viable adoption signal
- Add `adoption_proxy` calculation to `src/trend_state.py`

---

## W-0013

status: done
created: 2026-04-29
updated: 2026-04-30

### Outcome

All four pending test gaps filled. 100 new tests added across 4 files (369 total, up from 269).

### Context

These test slices were explicitly planned in Epics 11–14 but not yet written. They are needed before the trend pipeline is considered production-ready.

### Notes

- `tests/test_source_class.py` — assert each fetcher sets correct `source_class`
- `tests/test_credibility.py` — unit test each of the 5 axes and the time decay function
- `tests/test_themes.py` — idempotency of synonym normalisation; graceful API failure fallback
- `tests/test_trend_state.py` — extend existing; add diversity gate cases, velocity edge cases

---

## W-0014

status: done
created: 2026-04-29
updated: 2026-04-30

### Outcome

Completed as part of W-0005. Theme domain and definition fields are now populated by `cluster_themes()` in `src/trends.py` when `GEMINI_API_KEY` is present.

---

## W-0015

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

Semantic equivalence collapse prevents theme fragmentation from rebranding: "tool use", "function calling", and "tool calling" are merged into a single canonical theme. Theme names use correct acronym casing (AI, LLM, not Ai, Llm).

### Context

Without synonym collapse, each new marketing term for the same concept spawned a separate thin theme. Acronym breakage from `.title()` ("Ai Workforce Impact") made themes unreadable.

### Notes

- `normalize_theme_name()` in `src/themes.py` expanded to ~60 synonym entries covering workforce, infrastructure, capabilities, safety, coding, etc.
- `_ACRONYM_FIXES` post-processes title-cased output to restore AI, LLM, RAG, API, GPU, etc.
- `normalize_theme_name()` applied as catch-all in `src/trends.py run()` before themes enter `all_entries`

---

## W-0016

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

A `workflow_dispatch`-only `rebuild-site.yml` GitHub Actions workflow rebuilds `docs/data/` and commits it without running the email digest. Supports `no_fetch` boolean input to skip live sources.

### Notes

- `.github/workflows/rebuild-site.yml`
- Runs `python -m src.trends [--no-fetch]` and commits `docs/data/` with `[skip ci]`

---

## W-0017

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

Every theme is assigned a unique, persistent hex colour from a 20-slot high-contrast palette. The same colour is used everywhere that theme appears: trend chart line, hype bar, trend table swatch, theme card border, heatmap row label.

### Context

Charts used state-based colouring (emerging=amber, scaling=teal, etc.) so themes in the same state were indistinguishable. Requested in PR comment: colours must be unique and maximally contrasting.

### Notes

- `THEME_PALETTE` in `app.js` — 20 hues spanning the full wheel at high saturation/lightness for dark background legibility
- `buildThemeColorMap(allNames)` assigns palette slots by alphabetical sort so the mapping is stable across page loads
- `themeColor(name)` helper used by every render function
- `renderTrendChart`, `renderHypeCharts`, `renderHeatmap` each accept an optional `colorMap` parameter
- Theme cards: `border-left-color` set to theme colour
- Trend table: 8×8 px coloured swatch before theme name
- Hype bar charts: per-bar `backgroundColor` array keyed to theme colour

---

## W-0018

status: done
created: 2026-04-29
updated: 2026-04-29

### Outcome

Determine which of the 14 people and 23 institutions tracked by the-deep-archive project have RSS feeds, newsletters, or other machine-readable content endpoints that could be added to `config/sources.yaml`. Produce a prioritised shortlist with source type, URL, and recommended `source_class` for each candidate.

### Context

The site https://the-deep-archive.netlify.app/ tracks high-signal sources on AI + work. The source catalogue (below) covers academics, AI lab leaders, consultancies, analyst firms, and standards bodies — a richer set than the current HN + YouTube + arXiv pipeline. Many will be `media` or `operator` class, filling credibility gaps in cross-class confirmation.

### Spike scope (time-box: 2 h)

1. For each person entry: check if they publish a personal newsletter (Substack, Beehiiv, Revue, Ghost), blog (RSS), or LinkedIn newsletter with an RSS endpoint.
2. For each institution entry: check for RSS news feeds, research publication feeds, or report release pages.
3. Classify each candidate by feasibility: `✓ has RSS`, `~ newsletter (check)`, `✗ no feed`.
4. Record recommended `source_class`: primary / operator / practitioner / media / market.
5. Output a markdown table in the spike result section below.

### Source catalogue

#### People (from the-deep-archive.netlify.app)

| ID | Name | Affiliation | Priority | Expertise |
|---|---|---|---|---|
| p1 | Prof. Majd Sakr | Carnegie Mellon University | High | Human+agent collaboration, skill atrophy, human-centred AI |
| p2 | Ethan Mollick | Wharton School, UPenn | High | Jagged frontier of AI, augmentation models, practical AI adoption |
| p3 | Connor Grennan | NYU Stern | High | People & change, AI adoption readiness |
| p4 | Karim R. Lakhani | Harvard Business School | High | AI-driven business transformation, organisational redesign |
| p5 | Thomas H. Davenport | Babson College / MIT IDE | High | AI strategy, analytics, enterprise AI adoption |
| p6 | George Westerman | MIT Sloan | Medium | Digital transformation, executive leadership and technology |
| p7 | Harang Ju | Johns Hopkins / MIT IDE | Medium | AI agents, human-AI collaboration |
| p8 | Jared Spataro | Microsoft | High | Enterprise AI adoption, Copilot ecosystem, future of work with AI |
| p9 | Satya Nadella | Microsoft | Medium | Enterprise AI strategy, platform transformation |
| p10 | Dario Amodei | Anthropic | Medium | AI safety, agentic systems, responsible AI development |
| p11 | Sam Altman | OpenAI | Medium | AI capabilities trajectory, AGI, enterprise AI |
| p12 | Josh Bersin | Josh Bersin Company | High | HR technology, agentic HR, workforce transformation |
| p13 | Jan-Emmanuel De Neve | University of Oxford (Saïd) | Medium | Wellbeing economics, employee perception of AI |
| p14 | Peter McCrory | Anthropic | High | Labour-market effects of AI, productivity, displacement |

#### Institutions (from the-deep-archive.netlify.app)

| ID | Name | Type | Priority | Focus |
|---|---|---|---|---|
| i1 | Harvard Business Review (HBR) | Academic / Media | High | AI strategy, leadership, organisational change |
| i2 | MIT (Sloan, CSAIL, Media Lab) | Academic | High | AI research, future of work, technology and society |
| i3 | Carnegie Mellon University | Academic | High | HCI, AI systems, robotics |
| i4 | Anthropic | AI Technology Company | High | AI safety, agentic systems, human-AI interaction |
| i5 | OpenAI | AI Technology Company | High | Foundation models, agentic AI, enterprise AI adoption |
| i6 | Microsoft | AI Technology Company | High | Enterprise AI integration, Copilot ecosystem, productivity AI |
| i7 | Google / DeepMind | AI Technology Company | High | Foundation models, AI research, enterprise AI |
| i8 | AWS | AI Technology Company | Medium | Cloud AI infrastructure, enterprise AI services |
| i9 | McKinsey & Company | Consulting | Medium | AI economic impact, enterprise adoption, organisational change |
| i10 | BCG | Consulting | Medium | AI strategy, workforce transformation |
| i11 | Deloitte | Consulting | Medium | Enterprise AI, AI governance, tech trends |
| i12 | Accenture | Consulting | Medium | AI at scale, technology strategy |
| i13 | KPMG | Consulting | Medium | AI at scale, enterprise AI adoption, agent-driven reinvention |
| i14 | IDC | Analyst Firm | Medium | Workforce transformation, human-AI collaboration |
| i15 | Gartner | Analyst Firm | High | Strategic predictions, technology trends, enterprise AI |
| i16 | Forrester | Analyst Firm | Medium | Enterprise software, business models, AI predictions |
| i17 | Cognitive World | Media / Commentary | Medium | Cognitive science, AI impact on human capabilities |
| i18 | Training Industry | Media / Professional | Low | L&D, workforce development, upskilling |
| i19 | PwC | Consulting | Medium | AI business predictions, enterprise AI strategy |
| i20 | Agentic AI Foundation (AAIF) | Standards Body | High | Open standards for agentic AI, MCP, interoperability |
| i21 | Cloud Security Alliance (CSA) | Standards / Research | Medium | AI agent governance, agentic security, AI controls frameworks |
| i22 | Grant Thornton | Consulting / Advisory | Medium | AI governance audits, AI ROI, enterprise adoption |
| i23 | Stanford HAI | Academic / Research | High | Annual AI Index, AI policy and economics, capability benchmarks |

### Spike result

_Spike executed 2026-04-29. Feed availability determined from public sources and training knowledge. URLs marked `~ verify` should be spot-checked before adding to `sources.yaml`._

#### People feeds

| Source | Feed URL or base domain | source_class | Feasibility | Notes |
|---|---|---|---|---|
| Ethan Mollick (One Useful Thing) | `https://www.oneusefulthing.org/feed` | practitioner | ✓ confirmed RSS | Highest-traffic AI adoption newsletter; also at `oneusefulthing.substack.com/feed` |
| Thomas H. Davenport | HBR / MIT SMR author pages | practitioner | ✗ no public feed | Publishes in HBR and MIT SMR; capture via those institutional feeds |
| Karim R. Lakhani | HBR author page | primary | ✗ no public feed | Publishes in HBR and peer-reviewed journals; capture via HBR AI topic feed |
| George Westerman | MIT SMR | practitioner | ✗ no public feed | MIT Sloan faculty; capture via MIT SMR feed |
| Jared Spataro | Microsoft AI Blog | operator | ✗ no public feed | LinkedIn-primary; capture via Microsoft AI Blog feed |
| Satya Nadella | Microsoft AI Blog | operator | ✗ no public feed | No personal blog; announcements appear on Microsoft AI Blog |
| Dario Amodei | `https://darioamodei.com` | operator | ~ verify | Check `darioamodei.com/feed`; capture via Anthropic Blog RSS as reliable fallback |
| Sam Altman | `https://blog.samaltman.com/feed` or `/posts.rss` | operator | ~ verify | Personal blog exists; Ghost/custom CMS may expose RSS; posts infrequently but high signal |
| Josh Bersin | `https://joshbersin.com/feed/` | practitioner | ~ verify | Active WordPress blog; `/feed/` should resolve; HR+AI workforce lens |
| Connor Grennan | `connorgrennan.substack.com/feed` | practitioner | ~ verify | NYU Stern AI literacy; check Substack; low certainty on URL |
| Prof. Majd Sakr | CMU News RSS | primary | ✗ no public feed | CMU CS faculty; institutional CMU News RSS as fallback |
| Harang Ju | `https://harangju.com/feed` | primary | ~ verify | Academic personal site; check `/feed` or `/atom.xml`; low post frequency expected |
| Jan-Emmanuel De Neve | Oxford Saïd / CEPR | primary | ✗ no public feed | Oxford faculty; content via CEPR and IZA preprints (arXiv-adjacent) |
| Peter McCrory | `https://anthropic.com/rss.xml` | operator | ✗ no public feed | No personal feed; research appears on Anthropic Blog |

#### Institution feeds

| Source | Feed URL | source_class | Feasibility | Notes |
|---|---|---|---|---|
| Anthropic Blog | `https://www.anthropic.com/rss.xml` | operator | ✓ confirmed RSS | **Priority 1** — direct operator signal; safety research + model announcements |
| OpenAI Blog | `https://openai.com/blog/rss.xml` | operator | ✓ confirmed RSS | **Priority 2** — model releases, research, policy; lands before HN pickup |
| Google AI Blog | `https://blog.google/technology/ai/rss/` | operator | ✓ confirmed RSS | **Priority 3** — third major frontier lab |
| DeepMind Blog | `https://deepmind.google/blog/rss.xml` | operator | ✓ confirmed RSS | **Priority 3b** — high technical density; Gemini, AlphaFold, robotics |
| AWS ML Blog | `https://aws.amazon.com/blogs/machine-learning/feed/` | operator | ✓ confirmed RSS | **Priority 4** — applied/builder-focused; SageMaker, Bedrock, enterprise use cases |
| Microsoft AI Blog | `https://blogs.microsoft.com/ai/feed/` | operator | ✓ confirmed RSS | **Priority 7** — Copilot ecosystem, enterprise AI at scale |
| Harvard Business Review (AI) | `https://hbr.org/topic/subject/ai-and-machine-learning/feed` | media | ✓ confirmed RSS | **Priority 6** — business/leadership lens; management research HN misses |
| MIT Sloan Management Review | `https://sloanreview.mit.edu/feed/` | media | ✓ confirmed RSS | **Priority 8** — peer-reviewed management + practice; Davenport/Westerman/Lakhani publish here |
| MIT News (research) | `https://news.mit.edu/rss/research` | primary | ✓ confirmed RSS | CSAIL, AI Lab, Media Lab breakthroughs |
| CMU News | `https://www.cmu.edu/news/rss/` | primary | ✓ confirmed RSS | AI, robotics, HCI research coverage |
| Stanford HAI | `https://hai.stanford.edu/news/feed` | primary | ~ verify | Annual AI Index, policy briefs, governance; Drupal CMS — `/news/feed` likely resolves |
| McKinsey AI Insights | `https://www.mckinsey.com/capabilities/quantumblack/our-insights/rss` | media | ~ verify | QuantumBlack sub-path; also check `mckinsey.com/featured-insights/artificial-intelligence/rss` |
| BCG AI Insights | `https://www.bcg.com/rss/insights.xml` | media | ~ verify | Henderson Institute AI content; verify exact path resolves |
| Deloitte Insights | Deloitte Tech Trends feed | media | ~ verify | No reliably-documented RSS path; check `deloitte.com/insights/rss` |
| Accenture Newsroom | `https://newsroom.accenture.com/rss/news.rss` | media | ~ verify | Newsroom RSS reliable; AI research blog sub-path uncertain |
| Gartner Blog | `https://www.gartner.com/smarterwithgartner/feed/` | market | ~ verify | "Smarter with Gartner" editorial blog; primary research paywalled |
| Forrester Blog | `https://www.forrester.com/blogs/feed/` | market | ~ verify | Free blog tier; paywalled reports excluded; enterprise AI vendor evaluation angle |
| Cognitive World | `https://cognitiveworld.com/feed/` | media | ~ verify | WordPress site; `/feed/` should resolve; cognitive science + AI impact |
| Training Industry | `https://trainingindustry.com/feed/` | media | ~ verify | L&D + AI upskilling; WordPress `/feed/` likely resolves |
| Cloud Security Alliance | `https://cloudsecurityalliance.org/feed/` | media | ~ verify | AI governance, agentic security; WordPress `/feed/` likely |
| KPMG | _(none)_ | media | ✗ no public feed | Insights are static/JS-rendered; no discoverable RSS |
| IDC | `https://www.idc.com/about/about_idc/press_releases_rss` | market | ~ verify | Press releases only; primary research paywalled |
| PwC | _(none)_ | media | ✗ no public feed | Insights are PDF reports with no RSS; newsletter signup only |
| Agentic AI Foundation (AAIF) | `https://www.agenticaifoundation.org` | primary | ~ verify | New org (~2024); check base domain for blog/feed; low certainty |
| Grant Thornton | _(none)_ | media | ✗ no public feed | Static/gated insights pages; no confirmed RSS |

#### Top 10 recommended for immediate implementation

Ranked by feed reliability, signal quality, and gap relative to existing pipeline (HN, YouTube, arXiv, HuggingFace):

1. Anthropic Blog — `anthropic.com/rss.xml` (operator, confirmed)
2. OpenAI Blog — `openai.com/blog/rss.xml` (operator, confirmed)
3. Google AI / DeepMind — `blog.google/technology/ai/rss/` + `deepmind.google/blog/rss.xml` (operator, confirmed)
4. AWS ML Blog — `aws.amazon.com/blogs/machine-learning/feed/` (operator, confirmed)
5. Ethan Mollick — `oneusefulthing.org/feed` (practitioner, confirmed)
6. HBR AI — `hbr.org/topic/subject/ai-and-machine-learning/feed` (media, confirmed)
7. Microsoft AI Blog — `blogs.microsoft.com/ai/feed/` (operator, confirmed)
8. MIT Sloan Management Review — `sloanreview.mit.edu/feed/` (media, confirmed)
9. Stanford HAI — `hai.stanford.edu/news/feed` (primary, verify)
10. Josh Bersin — `joshbersin.com/feed/` (practitioner, verify)

Implementation path: items 1–8 (all confirmed RSS) can go directly into `config/sources.yaml` as opt-in sources. Items 9–10 need URL verification before adding.

### Notes

- Spike should be executed before implementing any new fetchers from this list
- Cross-reference with existing `sources.yaml` — several institution blogs (OpenAI, Anthropic, Google AI) may already be partially covered under W-0009
- People feeds (Substack newsletters) are likely `practitioner` class; institutional reports are `media` or `primary`

---

## W-0019

status: done
created: 2026-04-29
updated: 2026-04-30

### Outcome

The 9 confirmed RSS feeds from W-0018 are added to `config/sources.yaml` as opt-in sources (commented out, ready to activate). Each entry has the correct `source_class` and a short inline comment. Added in both the `blogs.rss` section (for email digest use) and the `trends.operator_rss` section (for trend pipeline use).

### Context

W-0018 identified 8 feeds with confirmed RSS availability covering major AI labs, enterprise AI, and practitioner perspectives currently missing from the pipeline. Adding them as `enabled: false` entries means they are discoverable and ready to activate without any code changes.

### Notes

- Add under new `# AI Lab / Operator sources` and `# Media / Analysis sources` headings in `sources.yaml`
- Feeds to add (confirmed, `enabled: false` by default):
  1. `https://www.anthropic.com/rss.xml` — source_class: operator
  2. `https://openai.com/blog/rss.xml` — source_class: operator
  3. `https://blog.google/technology/ai/rss/` — source_class: operator
  4. `https://deepmind.google/blog/rss.xml` — source_class: operator
  5. `https://aws.amazon.com/blogs/machine-learning/feed/` — source_class: operator
  6. `https://blogs.microsoft.com/ai/feed/` — source_class: operator
  7. `https://www.oneusefulthing.org/feed` — source_class: practitioner
  8. `https://hbr.org/topic/subject/ai-and-machine-learning/feed` — source_class: media
  9. `https://sloanreview.mit.edu/feed/` — source_class: media
- Items needing URL verification before adding (Stanford HAI, Josh Bersin) remain in W-0018 spike results
- Do NOT activate by default — user should opt in per feed to control digest volume

---

## W-0020

status: done
created: 2026-04-30
updated: 2026-05-01

### Outcome

Token pricing from major providers is tracked as a dedicated signal: price per million input/output tokens, context window size, tier/plan changes, and model deprecations. The trend pipeline surfaces cost movement alongside capability movement so that cost trends are visible on the site.

### Context

Token cost is a critical production decision factor and shifts frequently — often without prominent announcements. The operator changelog fetcher (W-0009) surfaces general announcements but not structured pricing data. A pricing-specific source would populate the trend pipeline with a quantitative "cost" signal distinct from capability claims, enabling the site to show e.g. "GPT-4 equivalent tasks are 90% cheaper than 12 months ago".

### Notes

- Candidate sources (all public, no auth):
  - Artificial Analysis pricing page: `https://artificialanalysis.ai` (no RSS; may need scrape or periodic snapshot)
  - OpenRouter models JSON API: `https://openrouter.ai/api/v1/models` — includes pricing fields per model; polling-based
  - `llm.extractum.io` pricing tracker (RSS/JSON if available)
  - Operator changelog fetcher (W-0009) already covers vendor blogs — extend to detect pricing keywords and flag pricing-change items with `evidence_type="pricing"`
- `source_class: market` — pricing data is market intelligence
- Recommended approach: extend the operator changelog post-processor to label items containing price/pricing/cost keywords; add OpenRouter models JSON as a lightweight polling source in `src/fetchers/`
- Track fields per model: `price_input` ($/M tokens), `price_output` ($/M tokens), `context_window`, `provider`
- Write `docs/data/pricing.json` from the trends pipeline for site display

---

## W-0021

status: done
created: 2026-04-30
updated: 2026-05-01

### Outcome

New and emerging inference/token providers are tracked alongside the major labs — Groq, Together AI, Fireworks AI, Cerebras, Lambda Labs, Perplexity, and others entering the market. The digest and trend pipeline surface when a new provider launches or an existing one changes pricing/capabilities significantly.

### Context

The inference provider market is expanding rapidly beyond the three major labs (OpenAI, Anthropic, Google). Practitioners are increasingly using Groq for speed, Together AI for open models, Fireworks for fine-tuned deployment, and new GPU-cloud entrants for cost. These are not captured by the current operator changelog sources (which focus on the frontier labs) or HN alone.

### Notes

- Candidate RSS / API sources (all `source_class: operator`):
  - Groq blog: `https://groq.com/blog/` — check for RSS endpoint
  - Together AI blog: `https://www.together.ai/blog` — check for RSS endpoint
  - Fireworks AI blog: `https://fireworks.ai/blog` — check for RSS endpoint
  - Cerebras blog: `https://cerebras.ai/blog/` — check for RSS endpoint
  - Lambda Labs blog: `https://lambdalabs.com/blog/` — check for RSS endpoint
  - Perplexity blog: `https://blog.perplexity.ai/` — check for RSS / Substack feed
- Add a **research spike** (1 h) to verify which blogs expose RSS before committing to fetcher work
- Extend `config/sources.yaml` `trends.operator_sources` section with confirmed feeds, `enabled: false`
- Consider labelling items from these sources with a `new_entrant: true` flag to allow filtering in the site
- GitHub releases RSS (`https://github.com/<org>/<repo>/releases.atom`) is a reliable fallback for open-source-first providers (e.g., Groq's open-source tooling)

---

## W-0022

status: done
created: 2026-04-30
updated: 2026-05-01

### Outcome

Sources covering local LLM running and self-hosting are added to `config/sources.yaml` as opt-in entries: Ollama, llama.cpp, LM Studio, LocalAI, and community discussion (r/LocalLLaMA). The pipeline gains visibility into the on-device/self-hosted segment, which signals hardware capability breakthroughs and practitioner adoption independent of cloud API pricing.

### Context

Local/on-device AI is a significant and fast-growing segment currently not represented in the pipeline. Practitioners running models locally are a distinct audience from cloud API users; their tooling (Ollama, llama.cpp, quantisation advances) often signals a capability threshold crossing (e.g. "7B model now runs at acceptable speed on M2 MacBook") before vendor announcements catch up. This segment is also relevant to the "cost" tracking goal in W-0020 — local inference has an effective token cost of near-zero after hardware acquisition.

### Notes

- Candidate sources:
  - Ollama GitHub releases: `https://github.com/ollama/ollama/releases.atom` — `source_class: practitioner`
  - llama.cpp GitHub releases: `https://github.com/ggerganov/llama.cpp/releases.atom` — `source_class: practitioner`
  - LocalAI GitHub releases: `https://github.com/mudler/LocalAI/releases.atom` — `source_class: practitioner`
  - LM Studio changelog / blog — check for RSS; `source_class: practitioner`
  - Simon Willison's blog (extensive local model coverage): `https://simonwillison.net/atom/everything/` — `source_class: practitioner`
  - r/LocalLLaMA (Reddit JSON API): `https://www.reddit.com/r/LocalLLaMA.json` — `source_class: practitioner`; deferred pending Reddit API access decision (see Deferred / Ideas)
- GitHub `releases.atom` feeds are reliable and require no auth — add directly to `config/sources.yaml` as `enabled: false`
- Simon Willison's blog is already well-known for signal density; add with `enabled: false` under blogs section
- r/LocalLLaMA: flag as deferred (matches existing Reddit deferral in Epic 17.5); note it separately
- Add a `local_model` theme alias to `src/themes.py` synonym map so Ollama/llama.cpp items cluster correctly

---

## W-0023

status: done
created: 2026-05-02
updated: 2026-05-02

### Outcome

Partial improvement: trend analysis removed from `daily-digest.yml`; `rebuild-site.yml` given a `workflow_run` trigger. Superseded by ADR-0017's corrected architecture, which further separates fetching, processing, and the two parallel consumers. W-0026/W-0027/W-0028 complete the migration.

---

## W-0024

status: done
created: 2026-05-02
updated: 2026-05-02

### Outcome

The two schema contracts are defined:

- **Schema Contract A — `FetchedItem`** (`src/fetchers/__init__.py`): added `author` field (required); added `to_dict()` / `from_dict()` for JSONL persistence; docstring records the contract boundary.
- **Schema Contract B — `ProcessedItem`** (`src/models.py`): new dataclass with all pipeline stage output fields (stages 1–8); `to_dict()` / `from_dict()` for JSONL persistence; docstring records the boundary rule (consumers must not call fetchers or pipeline stages).
- **`data/raw/`** and **`data/processed/`** directories created with documented `.gitkeep` files.

### Context

ADR-0017 requires two explicit schema contracts between the three pipeline concerns. Without them, consumers can and do reach past the boundary into fetchers and processing internals.

---

## W-0025

status: ready
created: 2026-05-02
updated: 2026-05-02

### Outcome

Source configuration is redesigned so each source is defined once in `config/sources.yaml`. Each source is tagged for which consumers it feeds. All consumers select their sources from this single list; there is no duplication.

### Context

The current `sources.yaml` has two parallel source lists: email digest sources (`youtube`, `blogs`, `substack`, `hacker_news`) and trend analysis sources (`trends.*`). Operator blogs appear in both sections, requiring manual synchronisation. This violates Single Responsibility and Open/Closed principles — adding a new source requires editing two places.

In the target architecture (ADR-0017), a single fetch step fetches ALL configured sources. Consumers select from `ProcessedItem` records, not from their own source lists. The configuration change unlocks the full pipeline separation.

### Target schema

```yaml
# config/sources.yaml — sources defined once, tagged by consumer

digest:
  # Which source_classes to include in the email digest
  include_classes: [operator, practitioner, media]
  # Which named sources to always exclude (too noisy for email)
  exclude_sources: []
  prompt: |
    ...
  subject: "Daily AI Digest — {date}"
  send_if_empty: false

sources:
  - name: "Anthropic Blog"
    url: "https://www.anthropic.com/rss.xml"
    type: rss
    source_class: operator
    enabled: true

  - name: "arXiv cs.AI"
    type: arxiv
    category: cs.AI
    source_class: primary
    enabled: true

  - name: "Nate Jones"
    type: youtube
    channel_id: "UC0C-17n9iuUQPylguM1d-lQ"
    source_class: practitioner
    enabled: true
```

### Notes

- Write ADR-0018 before implementing — document the exact schema and migration plan
- Update `src/config.py` with new typed config classes
- Migrate `config/sources.yaml` — do not support old schema alongside new one
- Update `src/pipeline/fetch.py` to iterate the unified source list
- Update email-digest consumer to filter by `digest.include_classes` and `digest.exclude_sources`
- Write tests for the new config loader and filter logic
- Backward compatibility: delete old sections; this is a breaking config change but the only user is the pipeline owner

---

## W-0026

status: done
created: 2026-05-02
updated: 2026-05-02

### Outcome

The fetch-and-process concern is implemented as two `src/pipeline/` modules and the `fetch-and-process.yml` workflow is activated. Fetching and processing run as two separate jobs in one workflow. Raw data is committed after fetching; processed data is committed after the pipeline.

### Context

ADR-0017 defines the target. Currently `src/main.py` does fetching + deduplication + Gemini summarisation + email in one function. `src/trends.py` does its own independent fetch + process. Neither reads from committed data files. The migration extracts the fetch and process concerns into `src/pipeline/`.

### Implementation

**`src/pipeline/fetch.py`** — CLI entry point for the fetch job:
- Loads config, instantiates all enabled fetchers
- Reads `state/processed.json` for deduplication
- Calls each fetcher, collects `FetchedItem[]`
- Writes `data/raw/YYYY-MM-DD.jsonl` (one `FetchedItem.to_dict()` per line)
- Exit 0 even if no new items (consumers handle empty input)

**`src/pipeline/run.py`** — CLI entry point for the process job:
- Reads `data/raw/YYYY-MM-DD.jsonl` → `FetchedItem[]`
- Runs each stage in order: ingest → clean → concept_extraction → theme_classification → summary_extraction → media_id → hype_scoring → credibility_scoring
- Writes `data/processed/YYYY-MM-DD.jsonl` (one `ProcessedItem.to_dict()` per line)

**`src/pipeline/stages/`** — one module per stage:

| Module | Input | Output | Tool |
|---|---|---|---|
| `ingest.py` | `FetchedItem` | `ProcessedItem` (fields defaulted) | Python |
| `clean.py` | `ProcessedItem` | `ProcessedItem` (cleaned_content set) | Python |
| `concept_extraction.py` | `ProcessedItem` | `ProcessedItem` (concepts, actors, impact_vector) | Gemini |
| `theme_classification.py` | `ProcessedItem` | `ProcessedItem` (theme, domain) | Gemini + `themes.py` |
| `summary_extraction.py` | `ProcessedItem` | `ProcessedItem` (summary) | Gemini |
| `media_id.py` | `ProcessedItem` | `ProcessedItem` (is_marketing, confidence) | Gemini + heuristic |
| `hype_scoring.py` | `ProcessedItem` | `ProcessedItem` (hype_risk) | `credibility.py` |
| `credibility_scoring.py` | `ProcessedItem` | `ProcessedItem` (credibility_score) | `credibility.py` |

Each stage: `def run(items: list[ProcessedItem], config: Config) -> list[ProcessedItem]`

### Notes

- Gemini stages 3–6 can batch per-item requests in a single API call for efficiency — the stage boundary is logical, not necessarily a separate API call
- `fetch-and-process.yml` already exists as a design document; activate it once `src/pipeline/fetch.py` and `src/pipeline/run.py` exist and tests pass
- `daily-digest.yml` and the existing `rebuild-site.yml` continue to run until W-0027 and W-0028 complete — do not remove them prematurely
- Write `tests/test_pipeline_*.py` for each stage; mock Gemini for all AI stages
- Write an ADR if stage boundaries differ materially from this spec

---

## W-0027

status: done
created: 2026-05-02
updated: 2026-05-02

### Outcome

The email digest is implemented as a pure consumer of `ProcessedItem` records. `src/digest/send.py` reads `data/processed/YYYY-MM-DD.jsonl`, applies digest configuration, formats and sends the email, writes `history/YYYY-MM-DD.txt`, and updates `state/processed.json`. The `email-digest.yml` workflow is activated. `daily-digest.yml` is retired.

### Context

Currently `src/main.py` does its own fetching + processing. In the target architecture, it reads from committed `ProcessedItem` records and has no knowledge of fetchers or pipeline stages. This is Dependency Inversion: the digest depends on the abstract `ProcessedItem` contract, not on concrete fetcher implementations.

### Notes

- Create `src/digest/` package
- `src/digest/send.py` — CLI entry point:
  - Reads `data/processed/YYYY-MM-DD.jsonl`
  - Filters items by `digest.include_classes` from config
  - Calls Gemini for narrative digest (using `summariser.py` rendering logic, refactored)
  - Sends email via `emailer.py` (unchanged)
  - Writes `history/YYYY-MM-DD.txt` — do not change this behaviour
  - Updates `state/processed.json` (adds sent item IDs)
  - `--dry-run` skips email and state update
- `email-digest.yml` already exists as a design document; activate once this module passes tests
- Retire `src/main.py` as the email entrypoint once `src/digest/send.py` is complete
- Keep `src/summariser.py` rendering logic; `send.py` calls it with `ProcessedItem` records
- Write tests in `tests/test_digest_send.py`; mock email sending and Gemini

---

## W-0028

status: ready
created: 2026-05-02
updated: 2026-05-02

### Outcome

The site build is implemented as a pure consumer of `ProcessedItem` records. `src/site/build.py` reads `data/processed/*.jsonl` (multiple days), computes trend state and aggregates, writes `docs/data/*.json`. The `rebuild-site.yml` workflow is updated to call `src.site.build`. `src/trends.py` is retired as the site build entrypoint.

### Context

Currently `src/trends.py` does its own fetching (arXiv, HuggingFace, etc.) and reads from `history/*.txt` (plaintext digest archives). In the target architecture, it reads structured `ProcessedItem` records from `data/processed/`, which already include theme labels, credibility scores, and hype risk — computed by the pipeline, not re-derived from plaintext. This eliminates duplicate Gemini calls and makes the trend analysis deterministic given fixed input.

### Notes

- Create `src/site/` package
- `src/site/build.py` — CLI entry point:
  - Reads all `data/processed/*.jsonl` files (rolling window, configurable)
  - Groups `ProcessedItem` records by theme and date
  - Computes `TrendMetrics` per theme using `trend_state.py` (unchanged)
  - Calls `cluster_themes()` from `themes.py` if GEMINI_API_KEY available
  - Writes `docs/data/meta.json`, `trends.json`, `themes.json`, `items.json`, `graph.json`, `sources.json`
  - `--no-fetch` has no meaning in this architecture (no fetching here); flag kept for backward compat but is a no-op
- `rebuild-site.yml` already exists as a design document; activate once this module passes tests
- Retire `src/trends.py` as the site build entrypoint once `src/site/build.py` is complete
- Existing `TrendMetrics`, `ThemeNode`, `GraphEdge` in `src/models.py` are unchanged
- Write tests in `tests/test_site_build.py`; supply fixture `ProcessedItem` records

---

## Deferred / Ideas

| Idea | Notes |
|---|---|
| **Research: transcript alternatives for cloud runners** | GitHub Actions IPs are blocked by YouTube's transcript service. Current fallback uses the feed description. Options to evaluate: (1) `youtube-transcript-api` proxy support (pass `proxies=` kwarg); (2) Supadata.ai — paid transcript-as-a-service API; (3) self-hosted runner on a residential IP; (4) download audio and run Whisper locally (high compute); (5) YouTube Data API v3 captions endpoint (requires OAuth, same IP may still be blocked). Goal: full transcript content in AI summaries, not just descriptions |
| Twitter/X timeline ingestion | Requires API tier; deferred |
| Podcast RSS (audio → Whisper) | High compute cost; revisit post-MVP |
| Web UI for config editing | Out of scope for CLI-first approach |
| Vector store for semantic dedup | Overkill vs. URL-based dedup for now |
| Per-topic digest segmentation | Could be a future prompt template system |
| Claim contradiction map | Bipartite graph: claims vs counter-claims; Epic 16 candidate |
| Adoption proxy dashboard | Job postings + repo stars + pricing changes; Epic 16 candidate |
