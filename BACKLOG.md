# Backlog

Organised by **Epic** → **Slice**. Each slice is independently deployable, produces a user-visible result, and can be tested in isolation.

Status legend: `[ ]` Not started · `[→]` In progress · `[x]` Done · `[~]` Deferred

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
| 0.10 | Add `davidamitchell/Skills` as a git submodule so Claude Code picks up project-level custom skills | `[ ]` | Target path: `.claude/commands/` (Claude Code discovers skills there automatically). Run: `git submodule add https://github.com/davidamitchell/Skills .claude/commands` then `git submodule update --init`. Add `.gitmodules` to the workflow checkout step with `submodules: true`. |
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
| 6.1 | `summary.prompt` field in `config/sources.yaml` passed to Gemini | `[ ]` | Default prompt if field absent |
| 6.2 | `summary.max_items_per_source` and `summary.max_tokens` honoured | `[ ]` | |
| 6.3 | Digest email is HTML with sections per source | `[ ]` | |
| 6.4 | `--debug` mode writes structured JSON logs to stdout | `[x]` | Implemented in `src/logger.py` (`_JSONFormatter`); wired via `--debug` arg in `src/main.py` |
| 6.5 | `--dry-run` documented in README and AGENTS with examples | `[x]` | Documented in README under "Local development"; `make dry-run` target in Makefile |
| 6.6 | Email includes a **TL;DR** section at the top: 3–5 bullets covering the most significant items, each with a direct link, plus a one-sentence trend note for the current period (e.g. "recurring theme this week: agentic coding workflows") | `[ ]` | Written by Gemini as part of the summarisation prompt; placed before the per-source sections |
| 6.7 | Email includes a **Sources** section at the bottom: which sources were fetched, item counts per source, and 2–3 suggested related sources worth following | `[ ]` | Generated from fetch metadata, not Gemini; keeps the reader aware of coverage gaps |
| 6.8 | Each item rendered in the email includes its **source link** (clickable URL) and **publication date/time** | `[ ]` | Both fields already exist on `FetchedItem` (`url`, `published`); this slice wires them into the email template |
| 6.9 | Each item carries a short **theme label** (1–3 words, e.g. "agentic RAG", "fine-tuning", "inference cost") assigned by Gemini during summarisation and displayed alongside the item in the digest | `[ ]` | Requires prompt change to ask Gemini for a `theme:` field per item; theme is surfaced in the email and can feed Epic 8 trend analysis |
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
| 7.6 | Smoke tests in `tests/test_smoke.py`: exercise the full pipeline (`main()`) with mocked network; assert exit 0, no crash, digest contains expected structure even when fetchers or Gemini fail | `[ ]` | Catches integration-level regressions that unit tests miss |

---

## Epic 8 — History & Trend Analysis

Each digest is archived; history feeds back into future summaries.

| # | Slice | Status | Notes |
|---|---|---|---|
| 8.1 | Archive each digest to `history/YYYY-MM-DD.txt` after a successful send | `[ ]` | Plain-text file per day; committed to repo by workflow alongside `state/processed.json` |
| 8.2 | Workflow commits `history/` alongside state on each successful run | `[ ]` | Single bot commit: `[skip ci] chore: update state and history YYYY-MM-DD` |
| 8.3 | Summariser loads the last N digests from `history/` and passes them to Gemini as context | `[ ]` | Enables "compared to recent days, today's dominant theme is…" — N configurable in `sources.yaml` (default 7) |
| 8.4 | Email **Trends** section: Gemini compares current digest to history and surfaces recurring topics, emerging threads, and notable absences | `[ ]` | Depends on 8.3; placed between TL;DR and per-source sections |
| 8.5 | `history/` directory browsable as a digest archive (file-per-day, no UI needed) | `[ ]` | Acceptance: 7 consecutive days of files exist in `history/` |

**Acceptance criteria:** After 7 days the Trends section names at least one theme that genuinely recurs across multiple digests.

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
