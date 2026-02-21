# ADR-0001: Use Python as Primary Language

Date: 2026-02-21
Status: Accepted

## Context

The pipeline needs to:
- Fetch YouTube transcripts
- Parse RSS feeds
- Call the Anthropic Claude API
- Send email
- Run inside GitHub Codespaces on a schedule

Multiple languages could accomplish this. The choice affects library availability, developer familiarity, and cold-start performance in CI.

## Decision

Use **Python 3.11+** as the sole implementation language.

## Consequences

### Positive
- The `anthropic` SDK, `youtube-transcript-api`, `feedparser`, and `smtplib` are all mature, well-documented Python libraries
- GitHub Actions Codespaces have Python 3.11 available by default — no custom runtime setup required
- The Anthropic official SDK is Python-first; feature parity is highest there
- Wide ecosystem for future extensions (e.g., `whisper` for audio, `trafilatura` for article extraction)
- Lowest barrier for most contributors to this kind of automation project

### Negative / Trade-offs
- Python is slower than compiled languages, but this is irrelevant for a daily batch job with negligible volume
- GIL limits true parallelism, but fetchers can use `asyncio` or `concurrent.futures` if needed

### Neutral
- Type hints (`mypy` / `pyright`) are used to compensate for Python's dynamic typing
