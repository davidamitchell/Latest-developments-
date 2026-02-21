# ADR-0009: Switch AI Summarisation to Google Gemini

**Date:** 2026-02-21
**Status:** Accepted — supersedes [ADR-0002](0002-use-anthropic-claude-for-summarisation.md)

---

## Context

ADR-0002 chose the Anthropic Claude API for summarisation. The main trade-off noted at the time was "requires an Anthropic API key and incurs per-token cost". This proved to be a barrier: the pipeline couldn't be acceptance-tested at all without a paid account.

ADR-0008 added an optional link-digest fallback to work around this. That solved the zero-cost path but still left Anthropic as the AI path.

Google AI Studio offers a free Gemini API tier (no billing setup required):
- 1 500 requests/day
- 1 000 000 tokens/day
- Rate limit: 15 req/min

A daily digest run makes one request. The free tier covers this indefinitely.

---

## Decision

Replace the `anthropic` SDK with `google-generativeai` in `src/summariser.py`.

- Default model: `gemini-2.0-flash` (fast, capable, free tier)
- Env var: `GEMINI_API_KEY` (previously `ANTHROPIC_API_KEY`)
- `pyproject.toml` and `requirements.txt`: swap `anthropic>=0.40.0` → `google-generativeai>=0.8.0`
- Model remains configurable in `config/sources.yaml`; users can choose `gemini-1.5-pro` for higher quality at lower free quota

The `summary.enabled` fallback from ADR-0008 is preserved — setting `enabled: false` still skips any AI call and produces a plain link list.

---

## Consequences

### Positive
- Zero cost for typical usage — Google AI Studio free tier covers a daily digest indefinitely
- No billing account or credit card required to get started
- Gemini 2.0 Flash handles long transcripts well (1M token context window)
- `GEMINI_API_KEY` can be obtained in two clicks at aistudio.google.com

### Negative / Trade-offs
- Replaces one vendor dependency (Anthropic) with another (Google)
- `google-generativeai` SDK differs from `anthropic` — tests need re-mocking
- Gemini's free tier has a 15 req/min rate limit; a large run with many sources could hit it (unlikely for daily digest volumes)

### Neutral
- System prompt semantics are unchanged — the existing `summary.prompt` config still works verbatim
- Future switch to Vertex AI (Google Cloud hosted, higher quotas) requires only a client config change
