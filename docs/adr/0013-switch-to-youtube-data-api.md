# ADR-0013: Switch YouTube Channel Discovery to YouTube Data API v3

Date: 2026-03-01
Status: Accepted

## Context

The pipeline discovers recent YouTube videos using the public RSS/Atom feed
(`https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`).  In
production this approach has two recurring failure modes:

1. **DNS block on `www.youtube.com`** — GitHub Actions runners and the Copilot
   coding-agent environment block direct connections to `www.youtube.com` via
   firewall rules, causing HTTP 500/404 errors on every run.
2. **Silent channel failures** — per-channel errors were caught inside
   `YouTubeFetcher.fetch()` and logged at `ERROR` level but never surfaced in
   the digest's run summary (`source_errors`), so broken channel IDs appeared
   as "0 items fetched" rather than as an actionable error.

## Decision

Replace the RSS feed with the **YouTube Data API v3 `search.list` endpoint**
(`https://www.googleapis.com/youtube/v3/search`) for channel video discovery.

Key design choices:

- Uses `httpx` (already a project dependency) to call the REST endpoint —
  no new library required.
- Requires a `YOUTUBE_API_KEY` environment variable (GitHub Secret in CI,
  `.env` entry locally).  Missing key raises `RuntimeError` immediately so
  the error is unambiguous.
- Remove the per-channel `try/except` inside `fetch()` so API errors propagate
  to `_safe_fetch` in `main.py` and appear in `source_errors` within the
  digest.  This fulfils the "no silent errors" requirement while preserving
  source-level isolation (YouTube failing does not abort the RSS or HN
  fetchers).
- A wrong or deleted `channel_id` now returns an empty result set (HTTP 200
  with `items: []`) rather than a 404, and logs a `WARNING` naming the channel
  and suggesting the user verify the ID — more actionable than a stack trace.
- `youtube-transcript-api` is retained for transcript fetching (no change).
  Transcripts remain best-effort: unavailable → falls back to API description.

## Consequences

### Positive

- `www.googleapis.com` is accessible from GitHub Actions and Copilot agent
  environments; the DNS block on `www.youtube.com` is no longer relevant for
  channel discovery.
- Channel failures propagate to `source_errors` and appear in every digest
  email, making broken configuration immediately visible.
- Stale channel IDs produce a clear `WARNING` log instead of a retried 404 /
  `RuntimeError`.
- Free tier quota (10,000 units/day) comfortably covers daily runs; each
  `search.list` call costs 100 units, so up to 100 channel queries per day.

### Negative / Trade-offs

- Requires a `YOUTUBE_API_KEY` GitHub Secret; the previous RSS approach needed
  no API key.  Operators must create a Google Cloud project and enable the
  YouTube Data API v3.
- `search.list` quota (100 units/call) is higher than RSS (free).  With many
  channels the daily quota could be exhausted; in that case switch to
  `playlistItems.list` (1 unit/call after an initial `channels.list` call).
- If one channel encounters an API error (e.g., quota exceeded), subsequent
  channels in the same run are skipped.  This is a deliberate trade-off for
  error visibility; operators can re-trigger the workflow after fixing the
  issue.

### Neutral

- Transcript fetching via `youtube-transcript-api` is unchanged (ADR-0004
  still applies for that layer).
- The `channel_id` field in `config/sources.yaml` is unchanged; no migration
  of existing configuration is needed.
- `_parse_date` already handles both `+00:00` and `Z` suffixes (Python 3.11+).
