# Progress

Last updated: 2026-04-29

---

## Current Status

**Phase:** Epic 8 — History & Trend Analysis (all slices done)
**Active slice:** —
**Branch:** `copilot/complete-epic-8`

---

| Epic | Title | Status | Complete |
|---|---|---|---|
| 0 | Foundation | **Done** | 11 / 11 slices |
| 1 | Proof of Life (YouTube → Gemini → Email) | In Progress | 5 / 7 slices |
| 2 | Deduplication | In Progress | 2 / 3 slices |
| 3 | Scheduled Automation | In Progress | 4 / 5 slices |
| 4 | Blog / RSS Sources | Done | 5 / 5 slices |
| 5 | Hacker News | In Progress | 3 / 4 slices |
| 6 | Configurable Prompt & Polish | **Done** | 10 / 10 slices |
| 7 | Reliability & Observability | In Progress | 5 / 6 slices |
| 8 | History & Trend Analysis | **Done** | 5 / 5 slices |
| 9 | MCP Tool Configuration | Done | 7 / 7 slices |

---

## Work Log

### 2026-04-29 — Session 15

**Branch:** `claude/trend-detection-system-3StIE`

**Completed:**
- **GitHub Pages trend intelligence site** (`docs/index.html`, `docs/css/style.css`, `docs/js/app.js`, `docs/js/charts.js`): 4-tab dashboard (Trends / Themes / Sources / Insights); chart wrappers for trend phase chart, hype split panels, source-class heatmap; degrades gracefully when data is empty.
- **`src/models.py`**: `CanonicalRecord`, `TrendMetrics`, `ThemeNode`, `GraphEdge` dataclasses.
- **`src/credibility.py`**: 5-axis credibility scoring (proximity, incentive, reproducibility, adoption, time_decay); hype detection.
- **`src/themes.py`**: synonym normalization map (~30 entries); `cluster_themes()` and `build_graph_edges()` — available for optional Gemini-powered enhancement later.
- **`src/trend_state.py`**: `classify_state()` state machine (emerging/scaling/mature/declining); `compute_velocity()`, `compute_stability()`, `update_metrics()`.
- **`src/trends.py`**: No-API-key trend pipeline. Parses `## Item Themes` (15 files), inline `Theme:` labels (45 files), and plain-link fallbacks (12 files) from `history/*.txt`. Computes per-week volume, velocity, diversity (by source name not source class), hype risk, and trend state. Writes `docs/data/*.json`. Runs in seconds from `python -m src.trends`.
- **`src/fetchers/__init__.py`**: `source_class` field added to `FetchedItem` (default: `"practitioner"`).
- **Fetchers updated**: YouTube/HN → `"practitioner"`, Substack → `"media"`, RSS → configurable via `config/sources.yaml`.
- **`src/config.py`**: `source_class` field on `RSSFeed`.
- **`.github/workflows/daily-digest.yml`**: Added "Run trend analysis" step; commit step now also stages `docs/data/`.
- **`docs/adr/0016-github-pages-trend-intelligence-site.md`**: ADR documenting Pages architecture and data contract.
- `BACKLOG.md` extended with Epics 10–17.
- `CHANGELOG.md` updated.

**Key design decisions:**
- Trend pipeline reads existing history files rather than re-calling Gemini. All structured data (`## Item Themes`, `Theme:` labels) was already written by the summariser — no additional API cost or key requirement.
- Diversity is measured by distinct source *names* (YouTube ≠ Hacker News) not source *classes* (both are "practitioner"). This gives a meaningful cross-source signal with the current source set.
- Volume is per-week average over full history span, not a windowed count. Windowed count near-zeroed everything because recent Gemini failures left recent history files without theme sections.
- Co-occurrence graph edges (themes sharing ≥3 dates) are computed without API; more expressive relationship types (causal, competitive) deferred to Epic 13 with optional Gemini enhancement.

**Mini-Retro:**

1. **Did the process work?** Planning was thorough. Implementation was fast once the no-API approach was clear. The site, Python modules, and data pipeline all work end-to-end.

2. **What slowed down or went wrong?** The original `src/trends.py` called Gemini for record extraction and theme clustering — redundant, since the history files already contain AI-extracted themes, and blocked without a local API key. This was caught during execution, not design. Root cause: I designed for the ideal data model (canonical records) without checking what data already existed in the repo.

3. **What single change would prevent this next time?** Before designing any pipeline step that reads existing data, inspect the data format first. A 5-minute `head history/*.txt` check would have made the no-API approach obvious from the start. Add to working methodology: "Check what data already exists before planning extraction."

4. **Is this a pattern?** Yes — assuming external dependencies are available (API key) without checking the local environment. The repo instructions say credentials come from GitHub Secrets; locally they don't exist. This should have been the first constraint checked, not discovered at run time.

---

### 2026-03-02 — Session 14

**Completed:**
- `src/history.py` — new module: `archive_digest(today, text, history_dir)` writes `history/YYYY-MM-DD.txt`; `load_recent_digests(n, history_dir)` returns most-recent-first list of N archived digests. Handles missing directory gracefully.
- `src/config.py` — `HistoryConfig` dataclass added (`enabled`, `history_days`, `history_dir`); wired into `Config` and `load_config()`.
- `config/sources.yaml` — `history:` section added (defaults: enabled, 7 days, `history/` directory).
- `src/summariser.py` — `summarise()` gains `history: list[str] | None` parameter; `_build_history_context()` formats history into system prompt with per-digest 3,000-char truncation and `## Trends` instruction; `_extract_trends()` extracts the Trends section from AI output; `render_html_digest()` renders Trends section between TL;DR and items grid.
- `src/main.py` — loads historical digests before calling `summarise()`; calls `archive_digest()` after successful email send; skips archiving on `--dry-run`.
- `.github/workflows/daily-digest.yml` — commit step updated to also stage `history/*.txt` files; commit message updated to include date.
- `history/.gitkeep` — ensures directory exists in fresh checkouts.
- `tests/test_history.py` — 16 unit tests covering `archive_digest`, `load_recent_digests`, `history_date_from_path`.
- `tests/test_summariser.py` — 14 new tests: `TestExtractTrends` (5 tests), `TestRenderHtmlDigestTrends` (4 tests), `TestSummariseWithHistory` (4 tests); `_extract_trends` added to imports.
- `tests/test_smoke.py` — new smoke test file (slice 7.6); 9 integration-level tests exercising `main()` end-to-end with mocked network. Covers: no-items exit, dry-run behaviour, fetcher failure recovery, archive integration.
- `tests/test_config.py` — 2 new tests for `HistoryConfig` loading (defaults and custom values).
- `docs/adr/0014-history-archiving-and-trend-analysis.md` — ADR documenting the file format, config schema extension, summariser API change, and trade-offs.
- `docs/adr/README.md` — updated with ADR-0014.
- `AGENTS.md` — Testing section updated to mandate full testing pyramid (unit + smoke/integration); Slice Completion Checklist updated to include pyramid check; new "Continuous Improvement — Always On" section added (active struggle tracking, error logging, mandatory mini-retro in PROGRESS.md).
- `.github/skills` + `.claude/skills` — submodules advanced to latest commit (`e54136b`) in `davidamitchell/Skills` repo.
- `BACKLOG.md` — all Epic 8 slices marked `[x]`; slice 7.6 marked `[x]`.

**Key design decisions:**
- Plain-text archive format: zero new dependencies, human-readable, `git log`-browsable.
- Per-digest 3,000-char truncation: limits token spend (7 × 3,000 = 21,000 extra tokens per run, within free tier).
- Trends section is conditional: only rendered in HTML when Gemini outputs `## Trends` (only present when history was provided and substantial enough to compare).
- `archive_digest()` called only after successful send — ensures history files always represent real emails sent.

**Mini-Retro:**
- Process worked: explore → plan → tests + implementation → lint → full suite. No rework on core functionality.
- Two test failures on first run: (1) `test_analysis_text_preserved` had incorrect assumptions about regex boundary behaviour (text without a following `##` header meant "Post-analysis." was captured inside the trends section, not after it) — fixed by adding a `## Analysis` header in the test; (2) `test_pipeline_calls_save_state_after_send` used `send_if_empty=True` but then asserted `save_state` not called — mismatch between test intent and config. Root cause: tests written without thinking through all config interactions. Fix: add a comment explaining the expected behaviour explicitly.
- Pattern identified: test assertions about "what won't be called" require careful attention to config interactions. Adding comments to test setup that explain *why* a given config value leads to the expected outcome prevents this class of mistake.
- Skills submodule required manual `git submodule init` before `--remote` update would work — shallow clone from CI had no submodule HEAD. Note for next session: `git submodule init && git submodule update --remote` is the correct sequence.



### 2026-02-27 — Session 13

**Completed:**
- `.github/skills/` — 7 skills copied from `davidamitchell/Skills` and committed as project skills for the GitHub Copilot Coding Agent. Skills: `backlog-manager`, `citation-discipline`, `remove-ai-slop`, `research`, `speculation-control`, `strategic-persuasion`, `strategy-author`. GitHub Copilot discovers these automatically from `.github/skills/`.
- `.github/skills/remove-ai-slop/SKILL.md` — frontmatter updated from non-standard format (title/version/author) to standard `name` + `description` as required by GitHub Copilot's skills loader.
- `.github/workflows/sync-skills.yml` — workflow that checks out `davidamitchell/Skills`, copies all `skills/*/SKILL.md` files into `.github/skills/`, and commits if anything changed. Runs weekly (Monday 06:00 UTC) and via `workflow_dispatch`.
- `AGENTS.md` — new "Agent Skills" section documents the `.github/skills/` layout, which skill is loaded when, the sync workflow, and the relationship to Claude Code skills.
- `BACKLOG.md` — slice 0.10 marked `[x]`; notes updated to reflect that the GitHub Copilot half is done and the Claude Code submodule remains a manual step.

**Notes:**
- GitHub Copilot Coding Agent picks up `.github/skills/<name>/SKILL.md` automatically — no configuration required.
- `remove-ai-slop` frontmatter in the upstream Skills repo uses a non-standard format (title/version/author/etc.) without `name` or `description`. These are required for GitHub Copilot to load the skill automatically. The copy in `.github/skills/` has been corrected; a PR to the upstream Skills repo would make the formats consistent.
- Claude Code project skills use `.claude/skills/<name>/SKILL.md` (same format). The skills could be symlinked or copied there too; deferred as `.claude/commands/` submodule approach was the original plan for Claude Code.
- The sync workflow uses `actions/checkout@v4` twice (once for this repo, once for davidamitchell/Skills into `_skills_source/`) — no auth tokens needed as Skills repo is public.

**Mini-Retro:**
- Process worked: explored the Skills repo, researched GitHub Copilot's skills format, identified the format mismatch in `remove-ai-slop`, fixed it. No rework needed.
- The upstream Skills repo README doesn't mention GitHub Copilot's `.github/skills/` install path — that gap in the Skills repo is worth noting but can't be fixed from this repo.
- Pattern: the backlog item (0.10) was written before the GitHub Copilot skills feature existed (it targeted Claude Code submodules). Updating the item description and marking done is the right move — don't carry forward a stale implementation plan.

---

### 2026-02-27 — Session 12

**Completed:**
- `src/summariser.py` — `_DEFAULT_PROMPT` updated to request a `## Suggested Sources` section (2–3 AI-generated recommendations based on today's content themes) and a `## Item Themes` section at the end with structured `url | theme` format (slice 6.7 + 6.9)
- `src/summariser.py` — `_extract_item_themes()` added: parses the `## Item Themes` section, returns a `{url: theme}` dict, and strips the section from the displayed analysis text
- `src/summariser.py` — `_render_item_card()` updated to accept an optional `theme` argument; displays theme as a `.theme-badge` span in the card meta row
- `src/summariser.py` — `render_html_digest()` updated to extract themes before rendering, passing matched theme to each card
- `src/summariser.py` — CSS updated: added `.theme-badge` class (purple badge matching the palette)
- `config/sources.yaml` — `summary.prompt` updated to request `## Suggested Sources` and `## Item Themes` sections (matches updated `_DEFAULT_PROMPT`)
- `tests/test_summariser.py` — 10 new regression tests: 6 for `_extract_item_themes()` parsing + 4 for theme badge rendering in `render_html_digest()`
- `BACKLOG.md` — 6.7 and 6.9 marked `[x]`; Epic 6 is now fully complete (10/10 slices)
- `state/processed.json` — reset to empty (0 processed IDs) so next run fetches fresh content

**Notes:**
- `## Suggested Sources` renders automatically through the existing `_plain_to_html()` heading + bullet handling — no rendering code change required
- `## Item Themes` is stripped from the AI Analysis display (it is structural data for card labelling, not human-readable prose)
- Slice 0.10: the `git submodule add https://github.com/davidamitchell/Skills .claude/commands` command must be run manually from a machine with internet access, then pushed

### 2026-02-27 — Session 11

**Completed:**
- `BACKLOG.md` — Epic 6 rationalised: marked 6.1, 6.2, 6.3, 6.8 as `[x]` (all were already fully implemented in code); marked 6.7 and 6.9 as `[~]` (deferred) with rationale
- `src/summariser.py` — `_DEFAULT_PROMPT` updated to request a `## TL;DR` section as the first part of every response (3–5 bullets + one-sentence trend note)
- `src/summariser.py` — `_plain_to_html()` extended to render `- ` and `* ` bullet lines as `<ul><li>` lists, so TL;DR bullets (and any other bullets in Gemini output) render correctly in the HTML email
- `src/summariser.py` — CSS updated: added `ul li` styling inside `.analysis` block for consistent spacing
- `config/sources.yaml` — `summary.prompt` updated to request `## TL;DR` section and per-item `Theme:` labels (matches `_DEFAULT_PROMPT` structure)
- `tests/test_summariser.py` — 3 new regression tests for bullet-list HTML rendering (`test_bullet_list_rendered_as_ul`, `test_star_bullet_rendered_as_ul`, `test_bullets_closed_by_blank_line`)
- `.github/workflows/daily-digest.yml` — checkout step updated with `submodules: true` (prep for slice 0.10)
- `BACKLOG.md` — slice 0.10 updated: workflow prep done; manual `git submodule add` step flagged for user

**Notes:**
- 6.7 (Sources section): run summary already shows sources/counts; "suggested related sources" deferred — commented-out channels in `config/sources.yaml` serve as discovery list
- 6.9 (Theme labels): prompt requests `Theme:` per item and Gemini outputs them in the analysis section; per-item card display deferred (requires structured AI output)
- Slice 0.10: the actual `git submodule add https://github.com/davidamitchell/Skills .claude/commands` command must be run manually from a machine with internet access, then pushed

### 2026-02-27 — Session 10

**Completed:**
- `mcp/manifest.yaml` — source of truth for all MCP servers (fetch, sequential_thinking, time, memory, git, filesystem, github). Each server declares which environments it targets.
- `mcp/generate.py` — converts manifest to five target formats (GitHub Copilot Agent, VS Code, Claude Desktop, Claude Code, opencode). Supports `--deploy` to also write canonical repo locations. Pure Python; only dependency is PyYAML (already installed).
- `mcp/tests/test_generate.py` — 20 pytest tests covering all builders, format differences, deploy mode, and a smoke test on the real manifest. All passing.
- `mcp/requirements.txt` — minimal self-contained dep list (PyYAML).
- `mcp/README.md` — comprehensive guide: quick start, server table, manifest editing instructions, how to regenerate, how to run tests, environment variable notes.
- `.github/mcp.json` — deployed GitHub Copilot Agent config (fetch + sequential_thinking + time). Picked up automatically by the GitHub Copilot Coding Agent.
- `.vscode/mcp.json` — deployed VS Code config.
- `.mcp.json` — deployed Claude Code CLI config.
- `mcp/generated/*.json` — all five generated configs committed.
- `.github/workflows/mcp-generate.yml` — workflow that regenerates configs, runs tests, and commits on any change to the manifest.
- `docs/adr/0011-mcp-configuration-manifest.md` — ADR documenting the manifest approach.
- `docs/adr/README.md` — updated with ADR-0011.
- `BACKLOG.md` — added Epic 9 (MCP Tool Configuration) with all slices marked done.

**Notes:**
- `.github/mcp.json` is the copy-paste answer to the user's question about GitHub agent config.
- GitHub target intentionally excludes `filesystem`, `git`, `memory`, and `github` (redundant or not meaningful in the ephemeral Copilot Agent sandbox).
- All 20 tests pass: `pytest mcp/tests/ -v`

---

## Work Log

### 2026-02-26 — Session 9

**Completed:**
- `config/sources.yaml` — Added 7 new YouTube channels from the "new sources" issue:
  - **Wes Roth** (`UCqcbQf6yw5KzRoDDcZ_wBSw`) — **activated** as second active channel; daily AI news, closest competitor to Nate Jones in posting frequency
  - **Matthew Berman** (`UCawZsQWqfGSbCI5yjkdVkTA`) — commented out; go-to for open-source AI and live model testing
  - **The AI Daily Brief** (Nathaniel Whittemore, @AIDailyBrief) — commented out; professional daily briefing style; channel ID still needed (view source on youtube.com/@AIDailyBrief)
  - **AI Explained** (`UCNJ1Ymd5yFuUPtn21xtRbbw`) — commented out; best for technical model deep-dives (was previously listed)
  - **Yannic Kilcher** (`UCZHmQk67mSJgfCCTn7xBfew`) — commented out; academic paper walkthroughs (was previously listed)
  - **Two Minute Papers** (`UCbfYPyITQ-7l4upoX8nvctg`) — commented out; visual/generative AI focus
  - **David Shapiro** (`UCvKRFNawVcuz4b9ihUTApCg`) — commented out; post-labor economics and autonomous agents
- `config/sources.yaml` — Added token budget guidance note: use `max_videos: 2–3` when enabling new channels; enable incrementally
- `BACKLOG.md` — Added slice 1.7 tracking the new sources expansion

**Notes:**
- Wes Roth activated immediately per the issue's recommendation ("closest competitor to Nate Jones for daily frequency")
- All other channels are added as commented-out entries with verified channel IDs — enable one at a time monitoring Gemini token usage
- AI Daily Brief channel ID (`UCKelCK4ZaO6HeEI1KQjqzWA`) confirmed via YouTube Music URL
- Token safety: 2 active channels × 3 max_videos = 6 max items per run ≈ ~18,000 input tokens (well within free tier)

### 2026-02-26 — Session 8

**Completed:**
- `AGENTS.md` — merged working methodology from `.claude/CLAUDE.md` into new "Working Methodology" section; `AGENTS.md` is now the single source of truth for all agents
- `.claude/CLAUDE.md` — replaced with `@AGENTS.md` stub; Claude Code auto-includes the canonical file
- `.github/copilot-instructions.md` — created; points GitHub Copilot to `AGENTS.md` as the canonical instructions file
- `BACKLOG.md` — added slice 0.11 (multi-agent DRY setup) marked done

**Notes:**
- All three agents (Claude Code, OpenAI Codex, GitHub Copilot) now share a single instruction source: `AGENTS.md`
- DRY enforced: working methodology lives only in `AGENTS.md`; agent-specific files are thin stubs

### 2026-02-26 — Session 7

**Completed:**
- `src/fetchers/rss.py` — Fix Substack HTTP 403: replaced RSS-specific `Accept` header with browser-like `text/html,...`; added `Accept-Language`, `Accept-Encoding`, `Connection`, `Upgrade-Insecure-Requests`, and `Sec-Fetch-*` headers. Cloudflare's bot-score checks these in addition to User-Agent.
- `src/fetchers/rss.py` — Added `fallback_url` support: when the primary feed URL returns a permanent HTTP error (4xx), the fetcher tries `fallback_url` if configured.
- `src/config.py` — Added optional `fallback_url` field to `RSSFeed` dataclass.
- `config/sources.yaml` — Documented `fallback_url` option with Substack 403 context.
- `src/main.py` — Added `--max-videos N` CLI argument that overrides `max_videos_per_channel` for a single run.
- `.github/workflows/daily-digest.yml` — Added `max_videos` `workflow_dispatch` input; threaded through to `--max-videos` CLI arg.
- `BACKLOG.md` — Added slice 3.5 for the max_videos workflow input.
- `src/fetchers/youtube.py` — switched from YouTube Data API (requires API key) to public RSS/Atom feed; no API key required.
- `tests/test_fetchers_youtube.py` — updated tests for RSS-based YouTube fetcher.

**Notes:**
- 0 videos in the last run was **not a bug** — state tracking is correct. All 5 most recent Nate Jones videos had already been processed. Use the new `max_videos` input (e.g. 15) on a manual trigger to catch up.
- The Substack 403 fix is live in this PR; the improved headers should bypass Cloudflare bot detection.

### 2026-02-22 — Session 6

**Completed:**
- `.claude/CLAUDE.md` — generic continuous-improvement instructions (loads automatically each session)
- `config/sources.yaml` — refocused on Nate Jones content: commented out Karpathy/Kilcher/AI Explained; added Nate Jones placeholder (channel ID still needed); added Nate's Newsletter as primary RSS source
- `AGENTS.md` — corrected stale Anthropic references to Gemini; updated branch naming convention
- `src/fetchers/rss.py` — RSS/Atom fetcher via `feedparser`; deduplicates by URL; reads from `config.blogs`
- `src/main.py` — wired RSS fetcher into pipeline
- `tests/test_fetchers_rss.py` — unit tests for RSS fetcher (mocked network)
- `PROGRESS.md`, `BACKLOG.md` — updated to reflect current state

**Notes:**
- @natebjones channel ID still needs manual lookup (open youtube.com/@natebjones → view source → search `"channelId"`)
- RSS fetcher uses `feedparser` (already in requirements.txt); `trafilatura` article extraction deferred to Epic 5

### 2026-02-21 — Session 5

**Completed:**
- `src/fetchers/youtube.py` — transcript fallback: when cloud IPs block transcript API, use `media:description` from Atom feed instead of dropping the item entirely
- `.github/workflows/daily-digest.yml` — three bug fixes from first live run:
  1. `ANTHROPIC_API_KEY` → `GEMINI_API_KEY`
  2. Added `RESEND_API_KEY` to env block
  3. Guard before `git add state/processed.json` when file doesn't exist
- `tests/test_fetchers_youtube.py` — updated: `_atom_feed()` now includes `media:description`; test renamed and added `test_uses_description_when_transcript_blocked`

**Notes:**
- First live dry-run confirmed the three bugs and their fixes
- YouTube transcripts are consistently blocked on GitHub Actions cloud IPs; description fallback ensures items still appear in digest

### 2026-02-21 — Session 4

**Completed:**
- `src/summariser.py` — switched from Anthropic to Google Gemini (`google-genai` SDK, not the deprecated `google-generativeai`)
- `src/config.py` — default model changed to `gemini-2.0-flash`
- `src/main.py` — API key check: `ANTHROPIC_API_KEY` → `GEMINI_API_KEY`
- `pyproject.toml`, `requirements.txt` — `anthropic>=0.40.0` → `google-genai>=1.0.0`
- `tests/test_summariser.py` — updated mocks for new `genai.Client` pattern
- `docs/adr/0009-switch-to-gemini-api.md` — new ADR documenting the decision
- `docs/adr/0002-use-anthropic-claude-for-summarisation.md` — status set to superseded

**Notes:**
- Used `google-genai` (current unified SDK) not `google-generativeai` (deprecated, end-of-life)
- Free tier via Google AI Studio: 1,500 req/day, 1M tokens/day — adequate for daily digest
- Model: `gemini-2.0-flash`

### 2026-02-21 — Session 3

**Completed:**
- `src/retry.py` — `with_backoff` with `no_retry` parameter for permanent errors
- `src/fetchers/youtube.py` — channel discovery via YouTube Atom feed (stdlib etree + httpx; no API key), transcript via `youtube-transcript-api`
- `src/summariser.py` — groups items by source, calls Claude, returns dated plain-text digest
- `src/emailer.py` — Gmail SMTP and SendGrid; credentials from env vars
- `src/main.py` — wired: YouTube → summarise → email (or print on `--dry-run`)
- Tests: `test_retry.py` (5), `test_fetchers_youtube.py` (12), `test_summariser.py` (6), `test_emailer.py` (5) — 37 total passing

**Notes:**
- Dropped feedparser from YouTube fetcher (feedparser's `sgmllib` dep is broken on Python 3.11); stdlib etree handles the well-structured Atom format cleanly

### 2026-02-21 — Session 2

**Completed:**
- `pyproject.toml` — project metadata, dependencies, ruff and pytest config
- `requirements.txt` — pinned production deps for CI
- `.devcontainer/devcontainer.json` — Codespaces setup
- `Makefile` — `dev-install`, `test`, `lint`, `format`, `check`, `run`, `dry-run` targets
- `.python-version`, `.env.example`
- `src/logger.py`, `src/config.py`, `src/state.py`, `src/fetchers/__init__.py`, `src/main.py` skeleton
- `tests/conftest.py`, `tests/test_state.py`, `tests/test_config.py`
- README, AGENTS, BACKLOG, ADRs — initial versions

### 2026-02-21 — Session 1

**Completed:**
- `README.md`, `AGENTS.md`, `BACKLOG.md`, `PROGRESS.md`
- `docs/adr/` — ADR index + ADRs 0001–0007
- `config/sources.yaml` — annotated configuration schema
- `.gitignore`, `.github/workflows/daily-digest.yml`

---

## Next Steps

1. Epic 1.5 — run pipeline end-to-end (non-dry-run) to confirm email delivery
2. Epic 2.3 — run pipeline twice; confirm second run skips all items
3. Epic 3.4 — verify schedule fires at 07:00 UTC and email arrives
4. Epic 5.2 — fetch linked article text with `trafilatura` (best-effort)
5. Epic 7.6 — smoke tests for full pipeline (`test_smoke.py`)
6. Epic 8 — history archiving and trend analysis

---

## Key Metrics (updated each run once pipeline is live)

| Metric | Value |
|---|---|
| Sources configured | 2 YouTube (Nate Jones + Wes Roth), 1 Substack, 1 HN |
| Items processed (lifetime) | — |
| Last successful run | — (dry-run only so far) |
| Last email sent | — |
| Consecutive days without failure | — |

---

## 2026-03-07

Standardisation pass: expanded `.github/copilot-instructions.md` from stub to full content (merged from `AGENTS.md`). Deleted `AGENTS.md` and `.claude/` directory (including `.claude/CLAUDE.md` and `.claude/skills` submodule). Updated `.gitmodules` to remove `.claude/skills` entry. Updated `.github/workflows/sync-skills.yml` to only advance `.github/skills` (removed `.claude/skills` steps). Updated `README.md` to remove `AGENTS.md` references and direct AI agents to `.github/copilot-instructions.md`. Added W-0001 to `BACKLOG.md`. Created `CHANGELOG.md`. Added ADR-0015 documenting the decision. Updated `docs/adr/README.md` index.

### Mini-Retro

1. **Did the process work?** Yes — documentation-only changes; no code paths affected. No test failures expected.
2. **What slowed down or went wrong?** The existing `docs/adr/0001-*.md` was already taken (Python language ADR), so the new ADR was numbered 0015.
3. **What change would prevent this next time?** Nothing to change — checking existing ADR numbers before assigning is standard practice.
4. **Is this a pattern?** No — one-off structural alignment.

## 2026-03-07 — Continuous Improvement & Learning framework

**Completed:**
- `.github/copilot-instructions.md` — replaced old "Mini-Retro — After Each Piece of Work" and "Continuous Improvement — Always On" sections with the unified **Continuous Improvement & Learning** framework (Identity as Architect, Every Session Ends with a Mini-Retro, Improvement Classes table, Knowledge Graphing, Proactive Maintenance, Improvement Flywheel, What "Done" Means).
- `.github/copilot-instructions.md` — added new **Chain-of-Thought Reasoning** section with 7 pipeline-specific reasoning steps (data-flow trace, code vs config lever, dry-run validation, test coverage, digest quality signal, deduplication integrity, improvement implication).
- `CHANGELOG.md` — added entries under `## [Unreleased]` for this change.

### Mini-Retro

1. **Did the process work?** Yes — documentation-only change; replaced two superseded sections with the canonical unified framework.
2. **What slowed down or went wrong?** Nothing. The old sections were clearly identified and the replacement was a clean cut.
3. **What change would prevent this next time?** Nothing to change — structural updates to agent instructions should continue to follow the same pattern: find, remove superseded content, insert new canonical content.
4. **Is this a pattern?** No — first time standardising to this specific framework.

## 2026-03-07 — Align copilot-instructions.md with personal Copilot instructions

**Completed:**
- `.github/copilot-instructions.md` — fixed `remove-ai-slop` skill description ("Post-processing AI-generated text to reduce detection signals" → "Removing hollow language from prose before committing").
- `.github/copilot-instructions.md` — added missing `Missing skill` row to the signal table ("Add to backlog; do not synthesise a substitute").
- `.github/copilot-instructions.md` — added two missing items to the "What Done Means" checklist: `CHANGELOG.md updated if behaviour changed` and `remove-ai-slop run on committed prose`.
- `.github/copilot-instructions.md` — added action mandate after the four mini-retro questions ("Do not just answer — make the change...").
- `.github/copilot-instructions.md` — replaced hollow opening quote in "Identity as Architect" with direct instruction.
- `.github/copilot-instructions.md` — added skills fallback line after the Agent Skills table.

### Mini-Retro

1. **Did the process work?** Yes — documentation-only changes; six targeted edits aligned cross-repo standard sections without touching repo-specific content.
2. **What slowed down or went wrong?** Nothing. All six changes were straightforward textual edits.
3. **What change would prevent this next time?** Nothing to change — the problem statement was precise and the target locations were unambiguous.
4. **Is this a pattern?** No — first alignment pass against personal Copilot instructions.

## 2026-04-29 — CodeQL fixes + dark mode GitHub Pages site

**Completed:**
- Fixed all 8 CodeQL security alerts: removed unused imports from `src/credibility.py`, `src/fetchers/arxiv.py`, `src/models.py`, `src/trends.py`, `tests/test_fetchers_arxiv.py`; removed unused globals `_NS_ATOM`/`_ARXIV_NS` from `src/fetchers/arxiv.py`; replaced empty `except: pass` with `contextlib.suppress` + comment.
- Extended ruff cleanup to 3 additional files not in CodeQL alerts but failing the linter: `src/fetchers/huggingface.py`, `tests/test_fetchers_huggingface.py`, `src/summariser.py`.
- Converted GitHub Pages dashboard to dark mode: IBM Plex Mono font, `#0d0d0d` background, `#00C3A5` teal accent, `#E8A1A8` dusk accent, sharp corners, uppercase micro-labels. Inspired by davidamitchell.github.io/Research.
- Updated Chart.js global defaults in `charts.js` for dark canvas rendering.
- Created `learnings.md` to capture patterns and root causes.

### Mini-Retro

1. **Did the process work?** Yes — CodeQL fixes were straightforward once the pattern was identified. Dark mode CSS was a clean rewrite against known design tokens.
2. **What slowed down or went wrong?** Playwright browser was locked; couldn't take a live screenshot. Verified CSS correctness by inspection only.
3. **What change would prevent this next time?** Kill any leftover browser processes before attempting visual verification. Also: running `ruff check .` across the full project earlier would have caught all 6 lint errors in a single pass instead of iteratively.
4. **Is this a pattern?** Unused imports from new feature branches: **yes, recurring**. Should add `ruff check --fix` as a pre-commit step or make it part of the slice completion checklist.

## 2026-04-29 — Per-theme unique colour system (W-0017)

**Completed:**
- Added W-0017 to BACKLOG.md (done).
- Implemented `THEME_PALETTE` (20 high-contrast hues) and `buildThemeColorMap()` in `docs/js/app.js`. Theme names are sorted alphabetically before palette assignment so the same theme always gets the same colour regardless of JSON ordering.
- Threaded `colorMap` parameter through `renderTrendChart`, `renderHypeCharts`, `renderHeatmap` in `docs/js/charts.js`.
- Trend table: coloured circle swatch before each theme name.
- Theme cards: `border-left-color` and name text coloured per theme.
- Hype bar charts: per-bar colours instead of single teal/yellow.
- Heatmap: theme name column coloured.
- Source table theme pills: coloured border from theme colour.
- `learnings.md` updated.

### Mini-Retro

1. **Did the process work?** Yes — the architecture was clean: build colour map once from all theme names, share via module-level variable, pass as parameter to chart functions.
2. **What slowed down or went wrong?** Playwright browser locked again — no screenshot possible. Verified correctness via Node.js tests of the colour logic.
3. **What change would prevent this next time?** Take screenshots at the very start of the session before any tool opens the browser.
4. **Is this a pattern?** Playwright lock is a recurring environment issue. Added note to learnings.

