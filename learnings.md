# Learnings

Session notes capturing patterns, friction, and root causes encountered during development.
Append-only — never edit old entries.

---

## 2026-04-29 — CodeQL fixes + dark mode site

### What was done
- Fixed 8 CodeQL security alerts (unused imports, empty except without comment, unused globals)
- Extended cleanup to 3 additional related files not flagged by CodeQL but failing `ruff check`:
  `src/fetchers/huggingface.py`, `tests/test_fetchers_huggingface.py`, `src/summariser.py`
- Converted GitHub Pages site to dark mode, inspired by davidamitchell.github.io/Research

### Design language extracted from Research site
- Background: `#0d0d0d` (body), `#0f1115` (surface/cards), `#161b22` (surface-2/headers)
- Border: `#252b33` (all dividers and card outlines)
- Text: `#e6e6e6` (main), `#666` (muted)
- Accent teal: `#00C3A5` (links, active states, primary indicators)
- Accent dusk/pink: `#E8A1A8` (secondary, declining state, media)
- Font: `IBM Plex Mono` via Google Fonts — monospace is core to the design identity
- No border-radius — sharp corners throughout (`border-radius: 0`)
- Uppercase micro-labels with `letter-spacing: 0.05em` for section heads and metadata

### Patterns

**CodeQL "Unused import" alerts = ruff F401.** The alerts listed specific files but ruff
catches more. Always run `ruff check .` across the whole codebase after fixing security
alerts — the set of files affected is broader than CodeQL reports.

**`try-except-pass` needs a comment or `contextlib.suppress`.** CodeQL flags the bare
`pass` as "empty except" (alert 26). The fix that satisfies both CodeQL *and* ruff SIM105
is `contextlib.suppress(ExceptionType)`. This is cleaner and self-documenting.

**`_UPPERCASE` locals inside functions trigger N806.** Ruff's N806 rule flags `ALLCAPS`
names inside function scope (they look like module-level constants but aren't). Use
`lowercase_with_underscores` for local constants instead.

**`Chart.defaults` in Chart.js 4.x is the correct place for global dark-mode config.**
Setting `Chart.defaults.color`, `Chart.defaults.borderColor`, and
`Chart.defaults.backgroundColor` at the top of `charts.js` before any chart instances
are created propagates dark colours to all charts without per-chart config repetition.

### What slowed down
- The Playwright browser was locked (another session held the lock), so couldn't take
  a screenshot of the rendered site. Committed the design based on CSS inspection only.
  Next time: kill any lingering browser processes before visual verification.

### Single change that would prevent this next time
- Add `make lint` as a pre-commit check so CodeQL-class issues are caught locally before
  the PR. The CI workflow already runs `ruff check` but a local Makefile target makes it
  easier to run the full check before pushing.

### Is this a pattern?
- Unused imports accumulating in new feature code: **yes, recurring**. The trend/credibility
  features introduced several stale imports. Running `ruff check --fix` at the end of any
  feature branch would clean these before they reach PR review.

---

## 2026-04-29 — Per-theme unique colour system (W-0017)

### What was done
- Added `THEME_PALETTE` (20 hues, evenly spaced across the wheel at high saturation)
- `buildThemeColorMap(allNames)` in `app.js` — sorts alphabetically before assigning palette slots for stable, deterministic mapping
- `themeColor(name)` helper used in every render function
- Threaded `colorMap` through `renderTrendChart`, `renderHypeCharts`, `renderHeatmap`
- Theme cards: `border-left-color` from `themeColor(t.name)`, name text coloured
- Trend table: 8×8 px coloured circle swatch before theme name
- Hype bar charts: per-bar `backgroundColor`/`borderColor` arrays keyed to theme colour
- Heatmap: theme name column coloured
- Source table: theme pills coloured with low-opacity border

### Patterns

**Alphabetical sort before palette assignment = deterministic colour.** Without sorting, themes in different order (e.g., trends.json vs themes.json) would receive different colours. Sorting first means the map is stable regardless of which file's theme list is processed first.

**Test arrays use `.length`, not `.size`.** Arrays in JavaScript have `.length`; only `Set` and `Map` have `.size`. When writing test assertions over arrays, use `.length`. The production code was correct; only the inline test script had this bug.

**Playwright browser lock persists across invocations.** Second session in the same environment still sees "Browser is already in use". The browser tool appears to hold a persistent lock in the container. Screenshots must be taken on first use or not at all. Document that visual confirmation has been done by code review / CI screenshot instead.

**`color + '1a'` and `color + '55'` for hex alpha.** Appending a 2-digit hex suffix to a 6-digit hex colour produces an 8-digit CSS colour with alpha. `0x1a ≈ 10%`, `0x55 ≈ 33%`. Works in all modern browsers. Cleaner than maintaining separate rgba() strings.

### What slowed down
- Playwright browser locked again — cannot take a live screenshot. Design verified by code review.

### Single change that would prevent this next time
- The container should restart the browser process between agent sessions. As a workaround: place any visual verification step as the first action in a session, before other tools have a chance to open the browser.

### Is this a pattern?
- Playwright lock: **yes, recurring** — noted in previous learnings and happened again. Add a note to copilot-instructions.md that visual verification in this environment must happen at the start of the session.


---

## 2026-04-30

### Mock target for fetchers with internal helpers

**Pattern:** Several fetchers (RSS, Substack) wrap `httpx.get` in an internal `_fetch_url` / `_fetch_json` function. Tests must patch the *wrapper*, not `httpx.get`, because `httpx.get` is not the outermost call visible to the test.

- `src.fetchers.rss._fetch_url` — returns `bytes`
- `src.fetchers.substack._fetch_json` — returns `list[dict]`
- `src.fetchers.arxiv` — uses `httpx.get` directly, so patch `httpx.get`
- `src.fetchers.huggingface` — uses `httpx.get` directly, so patch `src.fetchers.huggingface.httpx.get`

**Check before writing mocks:** `grep "patch" tests/test_fetchers_<target>.py | head -5`

### YouTube fetcher _api_key is set in __init__

`YouTubeFetcher._api_key` is read from `os.environ.get("YOUTUBE_API_KEY", "")` in `__init__`, not in `fetch()`. The patch must be active when the fetcher is *instantiated*, not only when `fetch()` is called.

```python
with patch("src.fetchers.youtube.os.environ.get", return_value="fake-key"):
    fetcher = YouTubeFetcher(config=cfg)
    ...  # then call fetch() inside here too, or set fetcher._api_key = "fake-key"
```

### W-0005: os import inside run() to avoid circular import risk

The `import os as _os` inside `run()` avoids polluting the module namespace with a redundant `os` import when `os` is already imported at the top. A cleaner alternative is just to add `import os` to the top-level imports — but the inline import is acceptable for a small guard block.

---

## 2026-05-01 — Instructions must be validated by use, not just written

### Pattern

Instructions written in isolation reliably develop gaps that only appear when you try to follow them. The three gaps found this session (backlog format ambiguity, invisible learnings.md, over-prescriptive skill chain mandate) were all invisible until the first step of actual execution failed.

### Rule

**Write instructions → immediately simulate the first action they describe → if you can't proceed, fix the gap before committing.**

Applied to agent instructions: after writing any new mandate section, ask "if I read only this section, what is the first concrete action I would take?" If the answer is "I don't know" or "I'd fail", the section has a gap.

### Applied fix

- Backlog Mandate: now documents both W-XXXX (status-based, for `backlog-worker`) and Epic slice tables (`[ ]`/`[x]`/`[→]`, worked directly).
- `learnings.md` Mandate: new section added — this file was invisible to new sessions.
- Skill chain table: added "guidance for non-trivial work" qualifier to prevent over-engineering minor tasks.

### Is this a pattern?

Yes — and it's not unique to this repo. Agent instructions written as prose mandates tend to overprescribe and underdocument. The fix is: write, simulate, fix gaps, commit.

---

## 2026-05-03 — Workflow YAML committed without validating entrypoints

### What happened

`daily-digest.yml` was committed with a daily schedule that called `python -m src.main` — a module that had been deleted when the pipeline was split into three concerns. This ran silently for however many days it was active.

### Root cause

Workflow YAML was treated as configuration, not code. No verification was done that the Python entrypoints referenced actually exist, accept the CLI args the workflow passes, or have the required env vars wired up.

### Rule — before committing any workflow YAML change

1. **Entrypoint exists:** `python -m <module>` — verify the file exists at `src/<module path>.py` with an `if __name__ == "__main__"` block or `main()`.
2. **Args are accepted:** every `--flag` the workflow passes must appear in the module's `_parse_args()` / `argparse` setup. Argparse silently drops unknown args — this is how `--max-videos` was ignored for weeks.
3. **Env vars are wired:** every `os.environ.get("KEY")` the module reads must appear in the workflow's `env:` block, sourced from `secrets.KEY`.
4. **Reusable workflow permissions:** if a caller uses `workflow_call` to call workflows that commit back to the repo, the caller must declare `permissions: contents: write` — called workflows inherit the caller's token and cannot escalate permissions.

### Is this a pattern?

Yes. The same failure mode recurs because YAML changes feel low-risk. They are not. Treat every workflow change as a code change: trace the execution path end-to-end before committing.

---

## 2026-05-07 — Retry wrappers require sleep stubbing in failure-path tests

### Pattern

When a previously single-shot path is wrapped with `with_backoff()`, existing tests that assert fallback behavior on exceptions can become slow because retries now sleep by default.

### Applied fix

Patch `src.retry.time.sleep` in tests that intentionally trigger retry exhaustion (`cluster_themes` fallback tests) so behavior is exercised without wall-clock delays.

### Why this matters

Without this, targeted test runs can appear hung or exceed CI time budgets even when logic is correct.

---

## 2026-05-09 — Data pipeline and site build learnings

**Use `uv run python -m pytest`, not bare `pytest`.** The `pytest` binary uses a separate tool venv that does not have project dependencies installed. `uv run python -m pytest` uses the project venv where all deps are present.

**`hist-` IDs are legacy migration pollution.** Items with `id` starting with `hist-` were written by the old `src/trends.py` history-parsing pipeline. They have empty URLs and single-word titles. They do not represent real FetchedItem records. `load_processed_items` in `src/site/build.py` now filters them permanently.

**`_build_source_list` must iterate `items`, not `entries`.** `entries` only contains AI-themed items. Sources with zero themed items (arXiv, HuggingFace, Matthew Berman when GEMINI_API_KEY is absent) become invisible in the Sources tab if you build the source list from `entries` only. The fix is a two-pass approach: count item_count from all items, then augment with theme data from entries.

**AI enrichment rate is an ops metric, not a code metric.** When `GEMINI_API_KEY` is absent or quota-exhausted, items are processed without themes. The pipeline continues normally (by design) but the site shows "all themes declining" because no new themed items arrive. The `log.json` `enrichment_rate` and `ai_note` fields surface this immediately. Target: enrichment_rate ≥ 0.95 per daily run.

**All themes declining = pipeline signal, not trend signal.** When every theme shows `state: declining`, the most likely cause is that no new AI-enriched items have been added in the last 14 days (the `_VOLUME_WINDOW_DAYS`). Check GEMINI_API_KEY and pipeline logs before interpreting declining states as genuine trend signals.


---

## 2026-05-09 — Lazy import wrapper pattern for google.genai in tests

### Pattern

Any module that does `from google.genai import types` at module level will fail to collect in the container's system Python test environment. The `cryptography` package has a broken native Rust extension (`pyo3_runtime.PanicException: Python API call failed`) in this environment.

### Fix

Wrap the google.genai-dependent call in a **module-level function** with a lazy inner import:

```python
def enrich(item, client, max_output_tokens=500):
    from src.pipeline.stages.enrich import enrich as _enrich  # lazy import
    return _enrich(item, client, max_output_tokens=max_output_tokens)
```

This means:
1. Importing the module does **not** trigger `google.genai` at import time.
2. Tests can patch `src.mymodule.enrich` cleanly (it is a module-level name).
3. The real import only fires when the function is actually called in production.

**Applied in:** `src/pipeline/backfill.py` (wraps `src.pipeline.stages.enrich.enrich`).

### Why module-level matters for patching

`patch("src.mymodule.enrich")` only works when `enrich` is a name in `mymodule`'s namespace. A lazy import *inside* a function body creates a local name that cannot be patched from outside. A module-level wrapper function makes the name patchable while still deferring the real import.

---

## 2026-05-09 — Error-path tests are mandatory for external API wrappers

### Pattern

`backfill.py` shipped with 9 tests but none covering quota exhaustion or programming-error propagation. Both paths had bugs (quota did not short-circuit; programming errors were swallowed). The tests covered the happy path and `ok=False`, which is insufficient for functions that wrap external APIs.

### Rule

Any function that calls the Gemini API must have tests for ALL five partitions:
1. **Success** — enrichment returns `(item, True)`
2. **ok=False** — enrichment returns `(item, False)`, item kept with defaults
3. **Transport error** — `ClientError`/`ServerError` retried by `with_backoff`
4. **Quota exhaustion** — `QuotaExhaustedEnrichError` stops the entire batch (no more API calls)
5. **Programming error** — `AttributeError`/`TypeError` propagates unchanged (not swallowed)

Partitions 4 and 5 were the ones that were missing and that had bugs.

### Shared implementations

Gemini quota and retry sentinel types live in `src/pipeline/_quota.py`. Always import from there — never re-implement locally. Local re-implementations diverge silently (this is exactly what happened).

### Why the import matters

`_quota.py` has no heavy transitive dependencies. Importing `run.py` pulls in `fetch.py → hackernews.py → trafilatura`, which breaks test collection in environments without that package. `_quota.py` avoids this.

---

## 2026-05-09 — Workflow git operations: three ordering and push gaps

Three bugs surfaced from the backfill workflow, all caused by the same class of mistake: treating workflow steps as independent when they share mutable git state.

### Gap 1 — git config must precede any step that calls git commit

`git config user.name/email` was set in the final "Commit" step. The Python script called `subprocess.run(["git", "commit", ...])` in an earlier step. The commit failed silently (caught by `except Exception`, logged as a warning). All progress landed in the safety-net commit instead.

**Rule:** If a Python script (or any step) runs `git commit`, `git config user.name/email` **must** be set in an earlier, dedicated step. Never assume it inherits from the environment.

### Gap 2 — local commits without push are lost if the job ends before the push step

`_git_commit_file` committed but did not push. The safety-net step only pushed inside the `else` branch (when there were uncommitted changes). If `--commit-progress` had already committed everything, the `git diff --cached` check exited clean → the `else` branch was skipped → no push → all per-file commits were silently discarded when the job ended.

**Rule:** Any workflow step responsible for pushing must do so **unconditionally** (outside any `if` guard), not only when it also creates a new commit. Separate the "commit if needed" logic from the "always push" action:

```bash
if ! git diff --cached --quiet; then
  git commit -m "..."
fi
git push origin HEAD   # always — picks up any locally-committed-but-not-pushed commits
```

### Gap 3 — no test for the git commit integration path

`commit_progress=True` in `backfill_all` had zero test coverage. Both gaps above went undetected because the test suite never exercised the code path. The fix was to add three tests: commit called per enriched file, not called by default, not called for already-enriched files.

**Rule:** Any workflow-integrated behaviour (subprocess git calls, flag-gated side effects) must have a unit test that mocks the subprocess and asserts call count and arguments. Workflow YAML cannot be unit-tested; the Python side can.

### Is this a pattern?

Yes. Every failure in this backfill sequence came from an untested side-effect path. The common theme: the happy path (enrich items, write files) was tested; the operational paths (git commit, git push, quota stop) were not. Operational paths are exactly where production failures hide.

---

## 2026-05-10 — Silent enrichment failure: GEMINI_API_KEY not set

### What happened

The site showed 35% enrichment. The backfill ran and reported "nothing to enrich". The daily pipeline was producing 78 items per run with `theme=""` for every item.

### Root cause

`GEMINI_API_KEY` was not set as a GitHub Secret.

- `src/pipeline/run.py` (the daily pipeline) intentionally skips enrichment when the key is absent: logs a WARNING and continues. Items are stored with `theme=""`. This is by design for dry-run/testing.
- `src/pipeline/backfill.py` checks for the key and exits with code 1 if absent.
- The backfill workflow had `continue-on-error: true` on the enrichment step, which silently swallowed the exit-1. The workflow showed green. The user saw "nothing to enrich".

### Fix applied

1. Added "Verify GEMINI_API_KEY is configured" as the FIRST step in `backfill-enrichment.yml` — fails immediately with a clear `::error::` annotation if the key is absent.
2. Removed `continue-on-error: true` from the enrichment step — failures are now visible as red workflow runs. The `if: always()` on the commit step already ensures partial progress is saved.
3. Added a `::warning::` annotation to the "process" job in `fetch-and-process.yml` when the key is absent — visible in the Actions UI on every pipeline run.

### Rule

**Any step where a missing secret causes silent degradation (not failure) must have an explicit check step that surfaces the absence before the degraded work runs.** The pipeline's graceful-skip design is correct for testing; the ops tool (backfill) must fail loudly.

**`continue-on-error: true` hides real failures.** Only use it when partial success is genuinely acceptable and you have a downstream step that checks and surfaces the outcome. If the step failing means the whole run is invalid, remove `continue-on-error` and let the step fail visibly.

### Is this a pattern?

Yes — the same class as the git-config-ordering bugs: a swallowed failure that looked like success. The pattern: `continue-on-error: true` + no downstream diagnostic step = invisible failures.
