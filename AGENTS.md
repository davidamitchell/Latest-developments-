# Agent Instructions

Instructions for AI coding agents (Claude Code, Copilot Workspace, etc.) working on this repository.

---

## Project Overview

This is a **Python 3.11+** pipeline that:
1. Fetches content from YouTube channels, RSS blogs, and Hacker News
2. Summarises it with Anthropic Claude
3. Emails a daily digest
4. Runs on a GitHub Actions schedule inside GitHub Codespaces

---

## Non-Negotiable Constraints

- **Never commit secrets.** API keys, passwords, and email addresses live in GitHub Secrets / environment variables. The `.env` file is gitignored.
- **Never re-introduce processed items.** All state lives in `state/processed.json`. Do not delete or reset this file.
- **No breaking changes to the config schema** without updating `config/sources.yaml`, the relevant ADR, and the README.
- **Every slice must be end-to-end runnable** before being marked complete in `BACKLOG.md`.
- **Keep PROGRESS.md updated** after every meaningful commit.

---

## Coding Standards

### Language & Runtime
- Python 3.11+
- Type hints on all public functions and class methods
- `pyproject.toml` for project metadata; `requirements.txt` for pinned deps

### Style
- `ruff` for linting and formatting (line length 100)
- Run `ruff check . && ruff format --check .` before committing
- No unused imports; no bare `except:` clauses

### Logging
- Use the project logger (`src/logger.py`) — never `print()` in production code
- Log levels: `DEBUG` for per-item detail, `INFO` for pipeline stages, `WARNING` for skipped/degraded paths, `ERROR` for failures
- In `--debug` mode, emit structured JSON logs to stdout
- In normal mode, emit human-readable logs at `INFO` level

### Error Handling
- Fetcher failures for a single source must not abort the entire run — log the error and continue
- Network errors should be retried with exponential backoff (max 3 attempts)
- Email failure is fatal and must exit non-zero

### Testing
- Tests live in `tests/`
- Use `pytest`
- Mock all network calls and the Anthropic API in tests
- Aim for unit tests on all business logic; integration tests are optional

---

## Repository Layout

```
src/
├── main.py             # CLI entry point; orchestrates the pipeline
├── fetchers/
│   ├── __init__.py
│   ├── youtube.py      # YouTube transcript fetcher
│   ├── rss.py          # RSS/blog fetcher
│   └── hackernews.py   # Hacker News API fetcher
├── summariser.py       # Anthropic Claude summarisation
├── emailer.py          # Email delivery (Gmail / SendGrid)
├── state.py            # Deduplication: read/write processed.json
├── config.py           # Load and validate sources.yaml
└── logger.py           # Logging setup (debug vs. normal mode)

config/
└── sources.yaml        # User-facing configuration (sources + prompt)

state/
└── processed.json      # Runtime state — gitignored in .env, committed in CI

docs/
└── adr/                # Architecture Decision Records (Markdown)
    ├── README.md        # ADR index
    └── NNNN-title.md   # Individual ADRs

.github/
└── workflows/
    └── daily-digest.yml

tests/
BACKLOG.md
PROGRESS.md
```

---

## Adding a New Source Type

1. Create `src/fetchers/<source>.py` implementing the `Fetcher` protocol (see `src/fetchers/__init__.py`)
2. Add configuration schema to `config/sources.yaml` with inline comments
3. Register the fetcher in `src/main.py`
4. Write unit tests in `tests/test_fetchers_<source>.py`
5. Write an ADR in `docs/adr/` if the approach involves a significant design decision
6. Update `BACKLOG.md` (mark slice done) and `PROGRESS.md`

---

## Adding an ADR

ADRs follow the [MADR format](https://adr.github.io/madr/). File naming: `docs/adr/NNNN-short-title.md` (zero-padded 4 digits). Update `docs/adr/README.md` index after adding.

Status values: `proposed` → `accepted` → `superseded` / `deprecated`

---

## Git Workflow

- Branch: `claude/setup-summarizer-project-4UzIg` (current development branch)
- Commits: imperative mood, present tense (`Add YouTube fetcher`, not `Added`)
- Never force-push
- Push after each logical unit of work; do not batch unrelated changes

---

## GitHub Actions / Codespaces

- The workflow file is `.github/workflows/daily-digest.yml`
- Secrets are injected as environment variables — see README for the full list
- `state/processed.json` is committed back to the repo by the workflow after each run to persist deduplication state across days
- The workflow supports `workflow_dispatch` for manual runs with optional `--debug` flag

---

## Slice Completion Checklist

Before marking a backlog slice as `Done`:

- [ ] Code is merged to the development branch
- [ ] `ruff check` passes
- [ ] `pytest` passes (with mocked network)
- [ ] `--dry-run --debug` works end-to-end
- [ ] `PROGRESS.md` updated
- [ ] Any new ADRs written and indexed
- [ ] README updated if user-facing behaviour changed
