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
