# Progress

Last updated: 2026-02-26

---

## Current Status

**Phase:** Epic 1 — Expanding YouTube sources
**Active slice:** 1.7 — Add 7 new YouTube channels (new sources issue)
**Branch:** `copilot/add-new-sources-backlog`

---

| Epic | Title | Status | Complete |
|---|---|---|---|
| 0 | Foundation | Done | 9 / 9 slices |
| 1 | Proof of Life (YouTube → Gemini → Email) | In Progress | 5 / 7 slices |
| 2 | Deduplication | In Progress | 2 / 3 slices |
| 3 | Scheduled Automation | Done | 5 / 5 slices |
| 4 | Blog / RSS Sources | In Progress | 1 / 5 slices |
| 5 | Hacker News | Not started | 0 / 4 slices |
| 6 | Configurable Prompt & Polish | Not started | 0 / 5 slices |
| 7 | Reliability & Observability | Not started | 0 / 5 slices |

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

1. Epic 1.6 — get @natebjones channel ID (manual: view source on youtube.com/@natebjones, search `"channelId"`)
2. Epic 1.5 — run pipeline end-to-end (non-dry-run) to confirm email delivery once channel ID is set
3. Epic 2.3 — run pipeline twice; confirm second run skips all items
4. Epic 5.1 — Hacker News fetcher

---

## Key Metrics (updated each run once pipeline is live)

| Metric | Value |
|---|---|
| Sources configured | 1 YouTube (ID needed), 1 RSS |
| Items processed (lifetime) | — |
| Last successful run | — (dry-run only so far) |
| Last email sent | — |
| Consecutive days without failure | — |
