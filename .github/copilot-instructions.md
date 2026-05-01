# Copilot Instructions

For AI coding agents (GitHub Copilot, Copilot Workspace, Codex, etc.) working on this repository.

---

## Skills

Skills are available at `.github/skills/`. Load the relevant skill at the start of any task that matches its description — do not synthesise a substitute.

Key skill chains:
- **Research → Strategy → Delivery**: `research` → `strategy-author` → `backlog-manager` → `backlog-worker` → `swe` + `tdd` → `code-review`
- **Backlog execution**: `backlog-manager` (refine to `ready`) → `backlog-worker` (execute to `done`)
- **Implementation**: `swe` (design) → `tdd` (write test-first) → `code-review` (verify)
- **Writing**: `technical-writer` → `feedback` → `remove-ai-slop`

---

## Backlog Mandate

The backlog is `BACKLOG.md` at the repo root. Use the `backlog-manager` skill from `.github/skills/backlog-manager/SKILL.md`. Read it at the start of every session.

To **execute** backlog items, use the `backlog-worker` skill from `.github/skills/backlog-worker/SKILL.md`. It selects the next `ready` item, decomposes it, applies the appropriate sub-skills, reviews the output, and advances the item to `done`.

---

## ADR Mandate

Every non-trivial architectural or design decision must be recorded as an ADR in `docs/adr/`. Use the `decisions` skill from `.github/skills/decisions/SKILL.md`. Format is MADR. Files named `docs/adr/NNNN-short-title.md`.

---

## PROGRESS.md Mandate

Append a dated entry to `PROGRESS.md` after every meaningful session or PR. Never edit old entries — append only. Format: `## YYYY-MM-DD` then what changed and why. Append-only prevents merge conflicts.

---

## CHANGELOG.md Mandate

Record every user-facing change in `CHANGELOG.md`. Follow Keep-a-Changelog 1.0.0. New entries go under `## [Unreleased]` at the top.

---

## Project Overview

Python 3.11+ daily digest pipeline. Fetches AI/ML content from YouTube, RSS feeds, and Hacker News; summarises with Gemini; emails the result. GitHub Actions runs it on a schedule. Deduplication state persists as a JSON file committed back to the repo after each run.

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
- Use the `tdd` skill from `.github/skills/tdd/SKILL.md` when writing new production code or fixing bugs — write the failing test first, then the minimal code to pass it
- Mock all network calls and the Gemini API (`patch("src.summariser.genai.Client", ...)`)
- **Apply the full testing pyramid:** unit tests on all business logic; integration/smoke tests in `tests/test_smoke.py` to exercise the full pipeline end-to-end; unit tests are necessary but not sufficient.
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

history/
└── YYYY-MM-DD.txt      # Archived daily digests

docs/
└── adr/                # Architecture Decision Records
    ├── README.md        # ADR index
    └── NNNN-title.md

.github/
├── copilot-instructions.md  # Agent instructions (this file)
├── skills/                  # Agent skills submodule (davidamitchell/Skills)
└── workflows/
    └── daily-digest.yml

BACKLOG.md              # Planned and completed work items
PROGRESS.md             # Append-only session history
CHANGELOG.md            # User-facing change log (Keep-a-Changelog)
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

- Branch naming: `copilot/<description>` or `claude/<description>-<session-id>` — create a new branch per session/PR
- Commits: imperative mood, present tense (`Add YouTube fetcher`, not `Added`)
- Never force-push
- Push after each logical unit of work; do not batch unrelated changes
- Always open a PR rather than pushing directly to main

---

## Agent Skills

Skills are modular instruction files that agents load automatically when a task matches the skill's `description`. They extend agent behaviour without bloating the main instructions.

Skills live in `.github/skills/<name>/SKILL.md`. GitHub Copilot discovers them automatically.

| Skill | When to load it |
|---|---|
| `backlog-manager` | Managing `BACKLOG.md`, adding or refining work items |
| `backlog-worker` | Executing ready backlog items — selects, decomposes, acts, reviews, marks done |
| `citation-discipline` | Writing research or reports where every claim must be sourced |
| `code-review` | Reviewing code changes for correctness, style, and security |
| `decisions` | Writing ADRs using the MADR format |
| `feedback` | Structured critique of written work, plans, arguments, or decisions |
| `inline-citation` | Adding inline citations to prose as work is written |
| `peer-reviewer` | Peer review of research or technical outputs |
| `plain-language` | Rewriting complex text into clear, plain language |
| `remove-ai-slop` | Removing hollow language from prose before committing |
| `research` | Investigating a topic with recursive decomposition and verification |
| `research-question` | Formulating precise, answerable research questions |
| `research-reviewer` | Reviewing completed research for rigour and completeness |
| `skill-author` | Writing new skills in the canonical SKILL.md format |
| `speculation-control` | Producing factual writing that requires clear epistemic discipline |
| `strategic-persuasion` | Building audience-targeted persuasive content |
| `strategy-author` | Producing or reviewing strategy documents |
| `swe` | Software design and implementation using SOLID, GoF patterns, and REST constraints |
| `tdd` | Test-driven development — write failing test first, then minimal code to pass |
| `technical-writer` | Writing or improving technical documentation |

If no skill fits, note the gap in `BACKLOG.md` and proceed without synthesising a substitute.

`.github/skills` is a git submodule tracking [`davidamitchell/Skills`](https://github.com/davidamitchell/Skills). A weekly workflow (`.github/workflows/sync-skills.yml`) advances the submodule pointer to the latest commit. Run the workflow manually to pull immediately. To add a new skill, add it to the Skills repo first; it will be picked up on the next sync.

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
- [ ] Full testing pyramid applied: unit tests for business logic + smoke/integration tests where applicable
- [ ] `make dry-run` works end-to-end
- [ ] `PROGRESS.md` updated
- [ ] Any new ADRs written and indexed
- [ ] README updated if user-facing behaviour changed

---

## Working Methodology

These instructions describe how to think and work, not what to build.

### Skill Composability — Use the Right Tool for Each Phase

Every significant task maps to a skill chain. Apply skills in sequence rather than working from general reasoning alone.

| Task type | Skill chain |
|---|---|
| Research a topic before acting | `research` → findings → decide |
| Turn research into a plan | `research` → `strategy-author` → `backlog-manager` |
| Work the backlog | `backlog-manager` (refine to `ready`) → `backlog-worker` (execute to `done`) |
| Implement a feature or fix a bug | `swe` (design) → `tdd` (test-first code) → `code-review` (verify) |
| Write or improve documentation | `technical-writer` → `feedback` → `remove-ai-slop` |
| Write an ADR | `decisions` |
| Review research or writing | `research-reviewer` / `peer-reviewer` / `feedback` |

When the task is ambiguous, apply `research` first to narrow it, then select the next skill from the chain above.

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
- **Visual verification via Playwright:** The browser tool holds a persistent lock in this container environment. If you need to take a screenshot, do it as the **first** action in the session before anything else opens the browser. If the browser is already locked, verify UI correctness by code review and Node.js tests instead of screenshots.

---

## Continuous Improvement & Learning

> Complete the work. Improve the system. If something was hard, slow, or confusing — fix it, document it, or raise it.

### Identity as Architect

You are the **Architect** of this repository, not just a user.
Your role is to complete work *and* to improve the system doing the work.
If something was hard, slow, or confusing — fix it, document it, or raise it.
Always ask: *"Is this the best version of this system, or just a working one?"*

### Every Session Ends with a Mini-Retro

Before closing any session or completing any PR, append a **Mini-Retro** to `PROGRESS.md`.
It is **not optional**. It is how the system learns.

Answer these four questions — briefly, honestly:

1. **Did the process work?** Was the approach sound? Did the plan hold?
2. **What slowed down or went wrong?** No blame — just facts.
3. **What single change would prevent this next time?** If nothing: say so.
4. **Is this a pattern?** Have you seen this friction before? If yes, it deserves a fix, not just a note.

> Do not just answer — make the change. If the answer is "document it", document it now. If it is "add a backlog item", add it now.

### Improvement Comes in Classes — Look for the Class, Not Just the Instance

When something goes wrong or goes right, resist the urge to fix *just this case*.
Ask: **what class of problem is this?**

| Signal | Class to consider |
|---|---|
| You had to look something up that should be documented | → Add it to the agent instructions or a skill |
| A step was manual that could be automated | → Raise a backlog item or add a workflow |
| A decision was unclear or had to be re-made | → Write an ADR |
| A note or file was out of date | → Mark it `superseded_by`, don't delete it |
| The same friction appears in two retros | → It's a pattern. Prioritise fixing the root cause |
| Missing skill | → Add to backlog using `backlog-manager`; do not synthesise a substitute |
| Implementation produced bugs | → Apply `tdd` from the start next time; bug fixes need a failing test first |
| Strategy unclear, backlog items poorly defined | → Apply `strategy-author` then `backlog-manager` to produce `ready` items before executing |
| Research required before acting | → Apply `research` first; do not guess domain knowledge |

### Knowledge Graphing — Every Write Earns Its Place

Every time you create or significantly update a file:
1. Search for 3 related existing files and link them in a `## Related` section.
2. Check for contradictions — supersede, don't delete.
3. Tag accurately in ADRs and docs.

### Proactive Maintenance — Leave It Better

You are permitted — and expected — to improve structure, conventions, and these instructions.
You are **not** permitted to delete history or introduce new structure without documenting why.

### The Improvement Flywheel

```
Do the work → Run the retro (what class of problem appeared?) → Fix or raise the root cause → Next session starts with a slightly better system
```

### What "Done" Means

- [ ] The work is complete and all tests pass (`make test`)
- [ ] `PROGRESS.md` is updated with a Mini-Retro
- [ ] Any new decisions are recorded as ADRs
- [ ] Any structural improvements spotted are raised in the backlog
- [ ] `CHANGELOG.md` updated if behaviour changed
- [ ] `remove-ai-slop` run on committed prose

---

## Chain-of-Thought Reasoning

Before acting on any task in this repo, reason explicitly through these steps:

1. **Trace the data flow first** — Before changing any pipeline code, trace the full path: source fetch → deduplication → summarisation → email render → send → state commit. Ask: "Which stage does this change affect? Could it break any downstream stage?"

2. **Code vs config lever** — Ask: "Is this change best expressed as a code change or a config change in `sources.yaml`?" Prefer config changes for behaviour that the user might want to adjust; prefer code changes for correctness fixes and new capabilities.

3. **Dry-run validation** — Any pipeline change must be verified with `make dry-run` before merging. Ask: "What would a dry-run output look like if this change is correct? What would it look like if it's broken?"

4. **Test coverage** — Before closing a task, ask: "Is there a unit test that would catch a regression in this change?" If not, write one. Fetcher changes, summariser changes, and state changes all need tests.

5. **Digest quality signal** — When evaluating output, ask: "Does this digest add genuine value — is it surfacing new, relevant signals — or is it just passing data through?" A technically working pipeline that produces low-quality digests is not done.

6. **Deduplication integrity** — Any change that touches `state/processed.json` or the deduplication logic must be scrutinised. Ask: "Could this cause items to be re-sent, or cause new items to be silently skipped?"

7. **Improvement implication** — Does this session reveal a class of pipeline fragility, a missing test pattern, or a configuration gap? Raise it in the Mini-Retro.
