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

---

## Epic 1 — Proof of Life (YouTube → Claude → Email)

One end-to-end run, hardcoded source, proves the core pipeline works.

| # | Slice | Status | Notes |
|---|---|---|---|
| 1.1 | `src/fetchers/youtube.py` — fetch transcript for a single hardcoded video | `[ ]` | Uses YouTube RSS feed + `youtube-transcript-api`; print to stdout |
| 1.2 | `src/summariser.py` — send transcript to Claude, return summary string | `[ ]` | Model configurable via `sources.yaml` |
| 1.3 | `src/emailer.py` — send plain-text email via SMTP (Gmail) | `[ ]` | Reads creds from env vars |
| 1.4 | Wire 1.1 → 1.2 → 1.3 in `src/main.py`; `--dry-run` skips email | `[ ]` | |
| 1.5 | Manually run in Codespaces; confirm email received | `[ ]` | Acceptance: email arrives with coherent summary |

**Acceptance criteria:** `python -m src.main --dry-run` prints a summary to stdout without errors.

---

## Epic 2 — Deduplication

Items processed once are never processed again, across days.

| # | Slice | Status | Notes |
|---|---|---|---|
| 2.1 | YouTube fetcher uses state to skip already-processed videos | `[ ]` | `src/state.py` already implemented |
| 2.2 | State file committed back to repo by workflow after each run | `[ ]` | Enables persistence across Codespaces sessions |
| 2.3 | Test: run pipeline twice; confirm second run processes 0 new items | `[ ]` | |

**Acceptance criteria:** A second consecutive run produces "No new items" and sends no email.

---

## Epic 3 — Scheduled Automation

Workflow runs daily without manual intervention.

| # | Slice | Status | Notes |
|---|---|---|---|
| 3.1 | GitHub Actions workflow: `schedule: cron: '0 7 * * *'` | `[ ]` | Triggers at 07:00 UTC |
| 3.2 | Workflow commits updated `state/processed.json` after run | `[ ]` | Bot commit with `[skip ci]` |
| 3.3 | Workflow supports `workflow_dispatch` with `debug` input flag | `[ ]` | |
| 3.4 | Verify schedule fires and email arrives at expected time | `[ ]` | Acceptance test |

**Acceptance criteria:** No manual action required for 3 consecutive days; email arrives each day.

---

## Epic 4 — Blog / RSS Sources

RSS feeds ingested alongside YouTube.

| # | Slice | Status | Notes |
|---|---|---|---|
| 4.1 | `src/fetchers/rss.py` — fetch and parse RSS/Atom feed via `feedparser` | `[ ]` | Returns list of `FetchedItem` |
| 4.2 | Deduplication applied to RSS entries by URL | `[ ]` | |
| 4.3 | RSS fetcher reads feeds from `config/sources.yaml` | `[ ]` | |
| 4.4 | Summaries from multiple sources merged into single digest email | `[ ]` | |

**Acceptance criteria:** Digest email contains sections for both YouTube and blog sources.

---

## Epic 5 — Hacker News

Top AI/LLM stories from HN included in digest.

| # | Slice | Status | Notes |
|---|---|---|---|
| 5.1 | `src/fetchers/hackernews.py` — query HN Algolia API for top stories | `[ ]` | Filter by keyword list and min score from config |
| 5.2 | Fetch linked article text (best-effort; skip paywalled) | `[ ]` | Use `trafilatura` for article extraction |
| 5.3 | Deduplication by HN story ID | `[ ]` | |
| 5.4 | Include HN section in digest email | `[ ]` | |

**Acceptance criteria:** Digest email contains a Hacker News section with ≥1 story on most days.

---

## Epic 6 — Configurable Prompt & Polish

User can tune what "important" means without touching code.

| # | Slice | Status | Notes |
|---|---|---|---|
| 6.1 | `summary.prompt` field in `config/sources.yaml` passed to Claude | `[ ]` | Default prompt if field absent |
| 6.2 | `summary.max_items_per_source` and `summary.max_tokens` honoured | `[ ]` | |
| 6.3 | Digest email is HTML with sections per source | `[ ]` | |
| 6.4 | `--debug` mode writes structured JSON logs to stdout | `[ ]` | |
| 6.5 | `--dry-run` documented in README and AGENTS with examples | `[ ]` | |

---

## Epic 7 — Reliability & Observability

Pipeline degrades gracefully; failures are surfaced.

| # | Slice | Status | Notes |
|---|---|---|---|
| 7.1 | Per-source retry with exponential backoff (3 attempts) | `[ ]` | |
| 7.2 | Source failure logs error and continues; digest still sent | `[ ]` | |
| 7.3 | Workflow failure sends alert email | `[ ]` | Uses GitHub Actions failure notification |
| 7.4 | `pytest` suite with mocked network for all fetchers | `[ ]` | |
| 7.5 | `ruff` linting enforced in CI | `[ ]` | |

---

## Deferred / Ideas

| Idea | Notes |
|---|---|
| Twitter/X timeline ingestion | Requires API tier; deferred |
| Podcast RSS (audio → Whisper) | High compute cost; revisit post-MVP |
| Web UI for config editing | Out of scope for CLI-first approach |
| Vector store for semantic dedup | Overkill vs. URL-based dedup for now |
| Per-topic digest segmentation | Could be a future prompt template system |
