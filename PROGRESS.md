# Progress

Last updated: 2026-02-27

---

## Current Status

**Phase:** Epic 0 — Foundation (all slices done)
**Active slice:** —
**Branch:** `copilot/investigate-github-agent-skills`

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
| 7 | Reliability & Observability | In Progress | 4 / 6 slices |
| 9 | MCP Tool Configuration | Done | 7 / 7 slices |

---

## Work Log

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
