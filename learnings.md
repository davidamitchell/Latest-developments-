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
