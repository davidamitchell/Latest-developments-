# ADR-0005: URL-Based Deduplication with JSON State File

Date: 2026-02-21
Status: Accepted

## Context

The pipeline must not process the same item (video, blog post, HN story) more than once across multiple daily runs. Items need to be tracked persistently between runs.

Options considered:
1. **JSON file committed to the repo** — a set of processed URLs/IDs stored as `state/processed.json`
2. **SQLite database** — more structured, supports queries
3. **GitHub Gist** — external storage, no repo pollution
4. **Redis / cloud KV store** — requires external infrastructure
5. **Item publish date check only** — only fetch items newer than the last run timestamp

## Decision

Use a **JSON file (`state/processed.json`)** containing a set of processed item identifiers (video IDs for YouTube, URLs for blogs/HN). The file is committed back to the repository by the GitHub Actions workflow after each run.

Identifier strategy:
- YouTube: video ID (e.g., `dQw4w9WgXcQ`)
- RSS: entry URL / GUID
- Hacker News: story ID (integer)

## Consequences

### Positive
- Zero infrastructure — the repo itself is the database
- Human-readable; can be inspected, edited, or reset manually
- Survives Codespaces session restarts (committed to git)
- Simple to implement (`json.load` / `json.dump` with a set)
- The workflow commits with `[skip ci]` to avoid triggering another run

### Negative / Trade-offs
- State file grows indefinitely over time (one entry per processed item); should be pruned after ~90 days
- Git history accumulates bot commits; acceptable for a personal project
- Race condition if two workflow runs overlap — mitigated by GitHub Actions concurrency groups
- Not suitable if the pipeline scales to millions of items

### Neutral
- The state module (`src/state.py`) encapsulates all read/write logic; switching to SQLite later is a one-file change
- A future slice (Epic 7+) will add state file pruning (remove entries older than 90 days)
