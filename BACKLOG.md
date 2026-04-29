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
| 5.2 | Fetch linked article text (best-effort; skip paywalled) | `[ ]` | Use `trafilatura` for article extraction |
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
| 7.3 | Workflow failure sends alert email | `[ ]` | Uses GitHub Actions failure notification |
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
| 11.5 | Tests for source class assignment | `[ ]` | Confirm each fetcher outputs correct class |

---

## Epic 12 — Canonical Record Extraction & Credibility Scoring

| # | Slice | Status | Notes |
|---|---|---|---|
| 12.1 | `src/credibility.py` — 5-axis credibility scoring | `[x]` | proximity, incentive, reproducibility, adoption, time_decay |
| 12.2 | Hype detection | `[x]` | `detect_hype()` — evidence density × source incentive proxy |
| 12.3 | `extract_records_from_digest()` in `src/trends.py` | `[x]` | Gemini JSON-lines extraction per history digest |
| 12.4 | Tests for credibility scoring | `[ ]` | Unit tests for each axis and edge cases |

---

## Epic 13 — Theme Clustering & Relationship Graph

| # | Slice | Status | Notes |
|---|---|---|---|
| 13.1 | `src/themes.py` — synonym normalization map | `[x]` | ~30 entries; collapses common rebrands |
| 13.2 | `cluster_themes()` — Gemini-powered clustering | `[x]` | Domain taxonomy enforced; definitions extracted |
| 13.3 | `build_graph_edges()` — relationship graph | `[x]` | causal/competitive/compositional/contradictory |
| 13.4 | Tests for clustering | `[ ]` | Idempotency; synonym collapse; graceful API failure |

---

## Epic 14 — Trend State Machine

| # | Slice | Status | Notes |
|---|---|---|---|
| 14.1 | `src/trend_state.py` — state classifier | `[x]` | emerging/scaling/mature/declining rules |
| 14.2 | `compute_velocity()` and `compute_stability()` | `[x]` | Rolling week-over-week metrics |
| 14.3 | Cross-class confirmation gate | `[x]` | diversity ≥ 2 required for non-declining state |
| 14.4 | `update_metrics()` — rolling history append | `[x]` | Max 30 snapshots per theme |
| 14.5 | Tests for state transitions | `[ ]` | Including spike vs trend, diversity gate |

---

## Epic 15 — Site Visualizations (Phase 1)

| # | Slice | Status | Notes |
|---|---|---|---|
| 15.1 | Trend phase chart (Chart.js multi-line) | `[x]` | Phase band overlays; renders from trends.json |
| 15.2 | Hype vs substantiation split panels | `[x]` | Evidence-weighted vs media-weighted side-by-side |
| 15.3 | Theme cards with state badge and metrics | `[x]` | Item count, hype risk, source diversity |
| 15.4 | Source-class coverage heatmap | `[x]` | CSS table; rows=themes, cols=classes |
| 15.5 | Trend state table with confidence bars | `[x]` | Sortable; velocity and diversity columns |
| 15.6 | Raw data drill-down | `[ ]` | Click theme → item-level provenance panel |

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
| 17.2 | Hugging Face model releases | `[ ]` | RSS or JSON API; primary/operator class |
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

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

### Outcome

Theme quality is measurably better: themes have recognisable, stable names (e.g. "Agentic Workflows" not "Ai Workforce Impact"), domains are populated (not "unknown"), and synonyms are collapsed (e.g. "tool use" ≡ "function calling" ≡ "tool calling" → "Agent Tool Use").

### Context

Current themes are derived from Gemini output in history files and are inconsistently named. All `domain` fields show "unknown". The synonym normalisation map in `src/themes.py` exists but is not called from `src/trends.py`. Gemini-powered clustering is implemented but not wired in because no API key was available locally; key is confirmed present in GitHub Secrets.

### Notes

- Wire `cluster_themes()` from `src/themes.py` into `src/trends.py` so Gemini normalises theme names each run
- Enforce domain taxonomy: multimodal, agents, infra, reasoning, safety, evals, data, hardware
- Validate synonym map covers common rebrands; add missing entries
- Consider whether theme names should be title-cased consistently

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

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

### Outcome

The trend pipeline fetches new model releases from Hugging Face (model cards RSS / JSON API) as `source_class="primary"`, contributing to cross-class confirmation for model-related themes.

### Context

HuggingFace model releases provide a high-frequency signal for capability advances, new architectures, and fine-tuning trends. Available via RSS at `https://huggingface.co/models` (sorted by recent) or the public models JSON API — no auth needed.

### Notes

- Implement after arXiv (W-0006) is stable
- Create `src/fetchers/huggingface.py`
- Source class: primary (model cards) or operator (if vendor-released)
- Limit to models with ≥ 100 downloads to reduce noise
- Add `trends.huggingface` section to `config/sources.yaml`

---

## W-0008

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

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

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

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

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

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

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

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

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

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

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

### Outcome

All four pending test gaps are filled: (11.5) source class per fetcher, (12.4) credibility scoring axes, (13.4) theme clustering idempotency, (14.5) trend state transitions including diversity gate and spike-vs-trend edge cases.

### Context

These test slices were explicitly planned in Epics 11–14 but not yet written. They are needed before the trend pipeline is considered production-ready.

### Notes

- `tests/test_source_class.py` — assert each fetcher sets correct `source_class`
- `tests/test_credibility.py` — unit test each of the 5 axes and the time decay function
- `tests/test_themes.py` — idempotency of synonym normalisation; graceful API failure fallback
- `tests/test_trend_state.py` — extend existing; add diversity gate cases, velocity edge cases

---

## W-0014

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

### Outcome

Theme domain fields in `trends.json` and `themes.json` are populated with values from the taxonomy (multimodal, agents, infra, reasoning, safety, evals, data, hardware) rather than "unknown". All themes have human-readable definitions.

### Context

Domain and definition fields are declared in `TrendMetrics` and `ThemeNode` but always default to "unknown" and "". This makes the site less useful and prevents domain-based filtering. The `cluster_themes()` function in `src/themes.py` uses Gemini to assign domains but is not wired into `src/trends.py`.

### Notes

- Wire `cluster_themes()` call into `src/trends.py` — requires GEMINI_API_KEY (available in GitHub Secrets, not locally)
- Run daily in CI where key is present
- Add graceful fallback (keep "unknown") when key not available (local dev)
- Dependent on W-0005 (theme quality)

---

## W-0015

status: needing_refinement
created: 2026-04-29
updated: 2026-04-29

### Outcome

Semantic equivalence collapse prevents theme fragmentation from rebranding: "tool use", "function calling", and "tool calling" are merged into a single canonical theme. The synonym map in `src/themes.py` covers all known rebrands from the session's 30-entry normalisation map.

### Context

Without synonym collapse, each new marketing term for the same concept spawns a separate thin theme with low volume and diversity, which never reaches a meaningful state classification. The synonym map exists in `src/themes.py` but `normalise_theme()` is not called on parsed history entries in `src/trends.py`.

### Notes

- Call `normalise_theme(name)` on each theme name in `parse_history_file()` in `src/trends.py`
- Validate the ~30 synonym entries cover current history themes
- Add test: same content with alternate phrasings produces identical theme output

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
