# ADR-0014: Digest History Archiving and Trend Analysis

Date: 2026-03-02
Status: Accepted

## Context

Each digest run produces a rich plain-text summary of the day's AI/ML content.
Without archiving, this information is discarded after the email is sent. There
is no way to compare today's digest to previous days, identify recurring themes,
or surface topics that have disappeared. Epic 8 adds history archiving (persisting
each digest) and uses that history to enrich Gemini's context, enabling a
"Trends" section that compares the current digest to recent days.

A new persistent file format is introduced (`history/YYYY-MM-DD.txt`), a new
config schema section (`history:`) is added, and the summariser's public API
changes to accept optional history context — all of which require an ADR.

## Decision

### File format

Each successful digest (after email send) is archived as a plain-text file:

```
history/YYYY-MM-DD.txt
```

One file per day. Files are committed to the repository by the workflow alongside
`state/processed.json` (using the existing bot-commit pattern). Plain text was
chosen because:

- The summariser already produces plain text as its canonical output
- Files are human-readable and `git log`-browsable without tooling
- No deserialisation overhead; loading is `Path.read_text()`

### Configuration

A new top-level `history:` section in `config/sources.yaml`:

```yaml
history:
  enabled: true
  history_days: 7       # number of past digests to pass as Gemini context
  history_dir: "history"  # directory relative to project root
```

Defaults ensure backward compatibility (existing configs work unchanged).

### Summariser API extension

`summarise()` gains an optional `history: list[str] | None` parameter. When
provided, `_build_history_context()` constructs a context block appended to the
system prompt that:

1. Includes each historical digest (truncated to 3,000 characters each to limit
   token spend)
2. Instructs Gemini to output a `## Trends` section comparing today to history

The `## Trends` section is extracted from AI output by `_extract_trends()` (same
pattern as `_extract_tldr`) and rendered in the HTML email between the TL;DR
banner and the items grid.

### History loading

`load_recent_digests(n, history_dir)` in `src/history.py` returns the text of
the *n* most recent `.txt` files in `history_dir`, sorted newest-first by
ISO-8601 filename. Missing directory → empty list (graceful degradation).

### Archiving

`archive_digest(today, text, history_dir)` writes `history/YYYY-MM-DD.txt`.
Called from `main.py` only after a successful `send_digest()` call.
Not called on `--dry-run`.

## Consequences

### Positive

- Each digest is permanently archived; the `history/` directory is a
  human-browsable archive of AI/ML news (slice 8.5)
- Trend analysis becomes richer over time as the history directory grows
- Zero new external dependencies
- History is optional and disabled per-source via `history.enabled: false`

### Negative / Trade-offs

- Repository grows by one small text file per day (~3–10 KB each)
- Passing 7 days × 3,000 chars = ~21,000 additional tokens to Gemini on each run
  (within the free tier; monitor with `history_days: 3` initially)
- Trends section is only meaningful after 2+ days of history exist

### Neutral

- `history/` is tracked in git alongside `state/` — same commit strategy,
  same bot author (`[skip ci]` tag prevents CI re-runs)
- `history/.gitkeep` ensures the directory exists in fresh checkouts
