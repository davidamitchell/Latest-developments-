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

**Two formats co-exist in `BACKLOG.md`:**
- **W-XXXX items** — standalone work items with `status: ready | active | done | archived`. These are the target of `backlog-worker`.
- **Epic slice tables** — rows using `[ ]` (not started), `[→]` (in progress), `[x]` (done). These group small, related slices within an Epic. Work them by updating the table notation directly.

To **execute** W-XXXX items, use the `backlog-worker` skill from `.github/skills/backlog-worker/SKILL.md`. It selects the next `ready` item, decomposes it, applies the appropriate sub-skills, reviews the output, and advances the item to `done`.

To work **Epic slices**, find the first `[ ]` row in the relevant epic, implement the slice, then update the status to `[x]` and note the date in the Notes column.

---

## ADR Mandate

Every non-trivial architectural or design decision must be recorded as an ADR in `docs/adr/`. Use the `decisions` skill from `.github/skills/decisions/SKILL.md`. Format is MADR. Files named `docs/adr/NNNN-short-title.md`.

---

## PROGRESS.md Mandate

Append a dated entry to `PROGRESS.md` after every meaningful session or PR. Never edit old entries — append only. Format: `## YYYY-MM-DD` then what changed and why. Append-only prevents merge conflicts.

---

## learnings.md Mandate

`learnings.md` at the repo root records **patterns, root causes, and per-session technical discoveries** — things a future agent should know before touching related code. Read it at the start of any session involving pipeline code, tests, or the site. Append a new dated section when your session surfaces a new pattern or resolves a recurring friction point. The distinction from PROGRESS.md: `PROGRESS.md` records what was done; `learnings.md` records what was learned.

---

## CHANGELOG.md Mandate

Record every user-facing change in `CHANGELOG.md`. Follow Keep-a-Changelog 1.0.0. New entries go under `## [Unreleased]` at the top.

---

## Project Overview — Architecture (read this first)

Python 3.11+ AI content intelligence system built on strict SOLID separation of concerns.

```
LAYER 1 — FETCHING      Sources → Fetchers → FetchedItem[]
                         Persisted: data/raw/YYYY-MM-DD.jsonl  ← committed to git

LAYER 2 — PROCESSING    FetchedItem[] → Pipeline stages → ProcessedItem[]
                         Persisted: data/processed/YYYY-MM-DD.jsonl  ← committed to git

LAYER 3A — EMAIL        ProcessedItem[] → format → send → history/YYYY-MM-DD.txt
LAYER 3B — SITE BUILD   ProcessedItem[] → trend analysis → docs/data/*.json
```

**Each layer persists its own output.** `data/raw/` and `data/processed/` are the durable data stores — both committed to git. Do NOT gitignore them without an explicit ADR.

**`docs/` is entirely ephemeral.** It is a build artefact produced by the site build consumer. It can be deleted and rebuilt from `data/processed/` at any time without affecting email delivery, state, or history. Nothing outside `docs/` depends on it.

**Layers 3A and 3B are parallel consumers.** Both trigger from the same event (new `data/processed/` committed) and have zero dependency on each other. Neither consumer calls a fetcher or pipeline stage — both depend only on `ProcessedItem` from `data/processed/`.

**Schema Contract A — `FetchedItem`** (`src/fetchers/__init__.py`): the only output of fetchers; the only input to the processing pipeline. Fields: `id`, `title`, `url`, `content`, `source_name`, `source_type`, `source_class`, `author`, `published`, `has_code`, `evidence_type`. All fetchers must populate every field.

**Schema Contract B — `ProcessedItem`** (`src/models.py`): the only output of the processing pipeline; the only input to consumers. Carries all `FetchedItem` fields plus stage enrichments: `fetch_date`, `cleaned_content`, `concepts`, `actors`, `impact_vector`, `theme`, `domain`, `summary`, `is_marketing`, `marketing_confidence`, `hype_risk`, `credibility_score`.

**Deduplication** happens at the fetch boundary: `state/processed.json` holds previously processed item IDs. Items already in this set are not fetched again. State is updated by the email digest consumer after a successful send.

---

## Non-Negotiable Constraints

- **Never commit secrets.** API keys, passwords, and email addresses live in GitHub Secrets / environment variables. The `.env` file is gitignored.
- **Never re-introduce processed items.** All dedup state lives in `state/processed.json`. Do not delete or reset this file.
- **Respect the schema contracts.** `FetchedItem` is the only output of fetchers. `ProcessedItem` is the only input to consumers. Consumers must not call fetchers or pipeline stages directly.
- **Config schema (ADR-0018):** `sources.yaml` has two independent sections: `sources` (flat list with type discriminator) and `digest` (references only ProcessedItem fields — never source names or types). Any config change must update both the YAML and the relevant ADR.
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
├── fetchers/
│   ├── __init__.py     # Schema Contract A: FetchedItem + Fetcher protocol
│   ├── youtube.py      # YouTube fetcher (YouTube Data API v3)
│   ├── rss.py          # RSS/Atom fetcher
│   ├── substack.py     # Substack JSON API fetcher
│   ├── hackernews.py   # Hacker News Algolia API fetcher
│   ├── arxiv.py        # arXiv RSS fetcher
│   ├── huggingface.py  # HuggingFace model releases
│   └── ...             # All fetchers return FetchedItem — the only coupling is the contract
│
├── pipeline/           # Concern 2: processing pipeline (W-0026)
│   ├── fetch.py        # CLI: fetch all sources → data/raw/YYYY-MM-DD.jsonl
│   ├── run.py          # CLI: process raw data → data/processed/YYYY-MM-DD.jsonl
│   └── stages/
│       ├── ingest.py             # Validate FetchedItem → ProcessedItem
│       ├── clean.py              # Strip markup, normalise whitespace
│       ├── concept_extraction.py # AI: entities, techniques, impact vector
│       ├── theme_classification.py # AI: theme label, domain
│       ├── summary_extraction.py # AI: 2–3 sentence summary
│       ├── media_id.py           # AI+heuristic: marketing vs substantive
│       ├── hype_scoring.py       # Composite hype risk
│       └── credibility_scoring.py # 5-axis credibility score
│
├── digest/             # Concern 3A: email consumer (W-0027)
│   └── send.py         # Read ProcessedItem[] → select → format → send → write history/
│
├── site/               # Concern 3B: site build consumer (W-0028)
│   └── build.py        # Read ProcessedItem[] → trend analysis → docs/data/*.json
│
├── models.py           # Schema Contract B: ProcessedItem + TrendMetrics, ThemeNode, GraphEdge
├── summariser.py       # Gemini digest rendering (used by digest/send.py)
├── emailer.py          # Email delivery (Gmail / SendGrid / Resend)
├── state.py            # Deduplication: read/write state/processed.json
├── credibility.py      # Credibility scoring (used by pipeline stages)
├── themes.py           # Theme normalisation and Gemini clustering
├── trend_state.py      # Trend state machine (used by site/build.py)
├── config.py           # Load and validate config/sources.yaml
├── history.py          # Write/read history/YYYY-MM-DD.txt (email digest concern only)
└── logger.py           # Logging setup
│
├── history.py          # Archive digest to history/; load recent digests for context
├── config.py           # Load and validate config/sources.yaml
└── logger.py           # Logging setup

config/
└── sources.yaml        # Two independent sections: sources (flat list) + digest (ProcessedItem filters only)

state/
└── processed.json      # Deduplication state — committed by daily-digest workflow after each run

history/
└── YYYY-MM-DD.txt      # Digest archives — committed by daily-digest; read by site build

docs/
├── index.html          # GitHub Pages site (source file — committed)
├── css/style.css       # Site styles (source file — committed)
├── js/                 # Site JavaScript (source files — committed)
├── data/               # EPHEMERAL — generated by rebuild-site.yml from data/processed/
│   │                   # Can be deleted and rebuilt at any time without side effects.
│   │                   # Nothing outside docs/ depends on these files.
│   ├── meta.json       # Run metadata
│   ├── trends.json     # Per-theme trend state and metrics
│   ├── themes.json     # Theme cluster definitions
│   ├── items.json      # Item-level records
│   ├── graph.json      # Theme relationship graph
│   └── sources.json    # Per-source coverage stats
└── adr/                # Architecture Decision Records
    ├── README.md        # ADR index
    └── NNNN-title.md

.github/
├── copilot-instructions.md  # Agent instructions (this file)
├── skills/                  # Agent skills submodule (davidamitchell/Skills)
└── workflows/
    ├── daily-digest.yml     # Schedule: fetch → email → commit state+history
    ├── rebuild-site.yml     # Triggered after digest or manual: trends → docs/data → GH Pages
    └── ci.yml               # Lint + test on every push/PR

BACKLOG.md              # Planned and completed work items
PROGRESS.md             # Append-only session history
CHANGELOG.md            # User-facing change log (Keep-a-Changelog)
tests/
```

---

## Adding a New Source Type

1. Create `src/fetchers/<source>.py` implementing the `Fetcher` protocol (see `src/fetchers/__init__.py`)
2. Add config schema to `config/sources.yaml` with inline comments
3. Register the fetcher in `src/pipeline/fetch.py` → `_build_fetchers()`
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

Four workflows, each with one responsibility. Two data contracts passed between them.

| Workflow | Trigger | Commits | Responsibility |
|---|---|---|---|
| `fetch-and-process.yml` | Schedule (07:00 UTC) + `workflow_dispatch` | `data/raw/`, `data/processed/` | Fetch all sources; run pipeline |
| `email-digest.yml` | `workflow_run` (fetch-and-process success) + `workflow_dispatch` | `state/processed.json`, `history/` | Send digest; archive |
| `rebuild-site.yml` | `workflow_run` (fetch-and-process success) + `workflow_dispatch` | `docs/data/` | Build site from processed data |
| `ci.yml` | Every push + PR | — | Lint and test |

`email-digest` and `rebuild-site` both listen to `workflow_run: ["Fetch and Process"]`. They trigger in **parallel** and complete independently.

**fetch-and-process.yml** (primary pipeline):
- Job 1 `fetch`: instantiates all enabled fetchers, deduplicates, writes `data/raw/YYYY-MM-DD.jsonl`, commits
- Job 2 `process`: reads raw JSONL, runs all pipeline stages, writes `data/processed/YYYY-MM-DD.jsonl`, commits
- Supports `workflow_dispatch` with `--debug` and `--max-videos` flags

**email-digest.yml** (consumer A — parallel):
- Reads `data/processed/YYYY-MM-DD.jsonl` only
- Filters items by digest config, formats, sends email
- Writes `history/YYYY-MM-DD.txt` — this is part of the email flow, not the pipeline
- Updates `state/processed.json` after successful send
- Supports `workflow_dispatch` with `--dry-run`
- Does **not** run trend analysis; does **not** write `docs/data/`

**rebuild-site.yml** (consumer B — parallel):
- Reads `data/processed/*.jsonl` only
- Computes trend aggregates, writes `docs/data/*.json`, deploys GH Pages
- Does **not** send email; does **not** read `history/`
- `docs/data/` is a build artefact — only this workflow writes it


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

Every significant task maps to a skill chain. Apply skills in sequence rather than working from general reasoning alone. **These chains are guidance for non-trivial work — do not apply them to minor config changes, small fixes, or documentation updates where the overhead outweighs the value.**

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

8. **Concern boundary** — Before changing any code, identify which concern it belongs to: fetching, processing pipeline, email digest consumer, or site build consumer. A consumer must not call a fetcher. A pipeline stage must not call an emailer. Changes that cross concern boundaries without a schema contract change are architectural violations.
