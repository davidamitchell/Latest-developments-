# Agent Instructions

For AI coding agents (Claude Code, Copilot Workspace, etc.) working on this repository.

---

## Project Overview

Python 3.11+ daily digest pipeline. Fetches AI/ML content from YouTube, RSS feeds, and Hacker News; summarises with Claude; emails the result. GitHub Actions runs it on a schedule. Deduplication state persists as a JSON file committed back to the repo after each run.

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
- `pyproject.toml` is the source of truth for dependencies and tool config

### Style
- `ruff` for linting and formatting (line length 100)
- Run `make check` before committing
- No unused imports; no bare `except:` clauses

### Logging
- Use the project logger (`src/logger.py`) — never `print()` in production code
- Log levels: `DEBUG` for per-item detail, `INFO` for pipeline stages, `WARNING` for skipped/degraded paths, `ERROR` for failures
- `--debug` emits structured JSON logs to stdout; normal mode emits human-readable `INFO`

### Error Handling
- Fetcher failures for a single source must not abort the entire run — log the error and continue
- Network errors must be retried with exponential backoff (max 3 attempts)
- Email failure is fatal and must exit non-zero

### Testing
- Tests live in `tests/`; use `pytest`
- Mock all network calls and the Gemini API (`patch("src.summariser.genai.Client", ...)`)
- Unit tests on all business logic; integration tests are optional
- **Bug fixes must start with a failing test.** Write a test that reproduces the bug first, confirm it fails, then apply the fix and confirm the test passes. Never commit a bug fix without a companion regression test.

---

## Repository Layout

```
src/
├── main.py             # CLI entry point; orchestrates the pipeline
├── fetchers/
│   ├── __init__.py     # Fetcher protocol and FetchedItem dataclass
│   ├── youtube.py      # YouTube fetcher (RSS feed + transcript API)
│   ├── rss.py          # RSS/blog fetcher
│   └── hackernews.py   # Hacker News Algolia API fetcher
├── summariser.py       # Gemini summarisation (google-genai SDK)
├── emailer.py          # Email delivery (Gmail / SendGrid)
├── state.py            # Deduplication: read/write processed.json
├── config.py           # Load and validate sources.yaml
└── logger.py           # Logging setup

config/
└── sources.yaml        # User-facing configuration (sources + prompt)

state/
└── processed.json      # Runtime state — committed by CI after each run

docs/
└── adr/                # Architecture Decision Records
    ├── README.md        # ADR index
    └── NNNN-title.md

.github/
└── workflows/
    └── daily-digest.yml

tests/
```

---

## Adding a New Source Type

1. Create `src/fetchers/<source>.py` implementing the `Fetcher` protocol (see `src/fetchers/__init__.py`)
2. Add config schema to `config/sources.yaml` with inline comments
3. Register the fetcher in `src/main.py`
4. Write unit tests in `tests/test_fetchers_<source>.py`
5. Write an ADR in `docs/adr/` if the approach involves a significant design decision
6. Update `BACKLOG.md` (mark slice done) and `PROGRESS.md`

---

## Adding an ADR

ADRs follow the [MADR format](https://adr.github.io/madr/). File naming: `docs/adr/NNNN-short-title.md` (zero-padded 4 digits). Update `docs/adr/README.md` after adding.

Status values: `proposed` → `accepted` → `superseded` / `deprecated`

### When an ADR is required

An ADR **must** be written any time a change involves one or more of the following:

- Introducing a new external dependency, service, or third-party API
- Choosing between two or more viable technical approaches (document what was rejected and why)
- Changing how agent configuration is delivered (MCP, skills, instructions files)
- Changing how the project is built, tested, or deployed
- Introducing a new persistent file format or state schema
- Any change that a future agent would need context on to understand *why* it was done this way

If you find yourself thinking "this is just config" or "this is just wiring" — stop and ask whether a future agent reading only the diff could reconstruct the reasoning. If not, write the ADR.

**The slice completion checklist item "Any new ADRs written and indexed" is a hard gate, not a suggestion.** Do not mark a slice done if an ADR was warranted and not written.

---

## Git Workflow

- Branch naming: `claude/<description>-<session-id>` — create a new branch per session/PR
- Commits: imperative mood, present tense (`Add YouTube fetcher`, not `Added`)
- Never force-push
- Push after each logical unit of work; do not batch unrelated changes
- Always open a PR rather than pushing directly to main

---

## Agent Skills

Skills are modular instruction files that agents load automatically when a task matches the skill's `description`. They extend agent behaviour without bloating the main instructions.

### GitHub Copilot (Coding Agent, VS Code Agent Mode)

Skills live in `.github/skills/<name>/SKILL.md`. GitHub Copilot discovers them automatically.

| Skill | When Copilot loads it |
|---|---|
| `backlog-manager` | Managing `BACKLOG.md`, adding or refining work items |
| `citation-discipline` | Writing research or reports where every claim must be sourced |
| `remove-ai-slop` | Post-processing AI-generated text to reduce detection signals |
| `research` | Investigating a topic with recursive decomposition and verification |
| `speculation-control` | Producing factual writing that requires clear epistemic discipline |
| `strategic-persuasion` | Building audience-targeted persuasive content |
| `strategy-author` | Producing or reviewing strategy documents |

`.github/skills` is a git submodule tracking [`davidamitchell/Skills`](https://github.com/davidamitchell/Skills). A weekly workflow (`.github/workflows/sync-skills.yml`) advances the submodule pointer to the latest commit. Run the workflow manually to pull immediately. To add a new skill, add it to the Skills repo first; it will be picked up on the next sync.

### Claude Code

`.claude/skills` is a git submodule tracking the same [`davidamitchell/Skills`](https://github.com/davidamitchell/Skills) repo. Claude Code discovers skills from `.claude/skills/<name>/SKILL.md`. The weekly sync workflow advances both submodule pointers together — a single source of truth serves both agents automatically.

---

## GitHub Actions / Codespaces

- Workflow: `.github/workflows/daily-digest.yml`
- Secrets are injected as environment variables — see README for the full list
- `state/processed.json` is committed back to the repo after each run; this persists deduplication state across days and Codespaces sessions
- The workflow supports `workflow_dispatch` with optional `--debug` and `--dry-run` flags

---

## Slice Completion Checklist

Before marking a backlog slice as done:

- [ ] Code merged to the development branch
- [ ] `make check` passes (ruff lint + format)
- [ ] `make test` passes (with mocked network)
- [ ] `make dry-run` works end-to-end
- [ ] `PROGRESS.md` updated
- [ ] Any new ADRs written and indexed
- [ ] README updated if user-facing behaviour changed

---

## Working Methodology

These instructions describe how to think and work, not what to build.

### Root cause before action

When something is broken or unclear, spend time on why before reaching for a fix.

Most problems fall into one of three categories:

**Context gap** — the information needed to do the right thing was never provided. The fix is to surface the missing information, not to guess or patch around it. If you find yourself assuming, write the assumption down and verify it.

**Model error** — the mental model of how the system works is wrong. The code or test was correct *given the model*, but the model didn't match reality. The fix is to update the model first, then re-derive the solution. Patching the code without fixing the model produces the next bug.

**Prompt/specification error** — the task was stated in a way that made the wrong solution look right. If a first attempt produced something reasonable but wrong, look at how the task was framed before retrying.

Treat repeated rework on the same problem as a signal that one of these is unresolved.

### Before writing code

- State what you understand the problem to be. If the statement is fuzzy, stop and sharpen it.
- Identify what you don't know. Missing information is better surfaced early than discovered mid-implementation.
- Note any assumptions explicitly. An assumption you write down can be checked; one you don't will bite you.

### When an attempt fails

- Do not retry the same thing. Understand why it failed first.
- "It didn't work" is not a diagnosis. "It didn't work because X was Y when I expected Z" is.
- If the failure is surprising — if it violated your expectation of how the system behaves — that surprise is the most valuable signal in the session. Investigate it.

### When you get it right on the second or third attempt

- Note what changed between attempts. That delta is the actual insight.
- If the change was adding context (a flag, a parameter, a piece of domain knowledge), ask why that context wasn't available on the first attempt and whether it should be persisted somewhere.

### Progress and documentation

Update documentation before context degrades, not after.

- After each meaningful unit of work: commit, update status, note what changed and why.
- Anything that would make the next session faster belongs in a persistent file, not just in the conversation.
- PROGRESS.md is the handoff document. A new session reading it should know exactly where to pick up and what not to redo.

### Improvement is about patterns, not incidents

A one-off error is noise. A pattern is signal.

When the same class of problem appears more than once — same type of misunderstanding, same missing constraint, same unexpected system behaviour — that is a process or context problem, not a code problem. Fix the process; don't just fix the latest instance.

Questions that surface patterns:

- Have I seen this failure mode before in this repo?
- Is there something about how work is specified here that consistently leads to this?
- What would need to be true for this class of error to not happen again?

### Defaults

- Do the smallest thing that could work and test it before going further.
- Prefer reversible actions over irreversible ones, especially when uncertain.
- When choosing between writing more code and gaining more understanding: gain understanding first.
- Leave the codebase in a state where the next session can start immediately.

---

## Mini-Retro — After Each Piece of Work

After completing any task or PR, take two minutes to ask:

1. **Did the process work?** Was there a test-first cycle, or was the fix applied before a test existed?
2. **What broke the process?** If the process didn't work, identify the exact moment — the assumption, the missing context, the skipped step.
3. **How can the instructions be improved?** If a convention or constraint would have prevented the problem, add it to this file *now*, not later.
4. **Is this a pattern?** Has this class of issue appeared before? If so, it is a process problem, not a one-off.

The goal is that the next agent working in this repository should not be able to make the same class of mistake. If that is not true after your session, update AGENTS.md before closing.
