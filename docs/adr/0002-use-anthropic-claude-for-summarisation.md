# ADR-0002: Use Anthropic Claude for Summarisation

Date: 2026-02-21
Status: Superseded by [ADR-0009](0009-switch-to-gemini-api.md)

## Context

The pipeline needs to summarise potentially long content (YouTube transcripts, blog posts, HN threads) into a concise daily digest. The summarisation must:
- Handle varied input lengths (short blog posts to hour-long transcripts)
- Follow a user-configurable prompt describing what is "important"
- Produce coherent, readable output suitable for an email

Options considered:
1. **Anthropic Claude** (claude-sonnet-4-5 or claude-haiku-3-5)
2. OpenAI GPT-4o
3. Local model via `ollama` (e.g., llama3)
4. Rule-based extractive summarisation (no LLM)

## Decision

Use the **Anthropic Claude API** via the official `anthropic` Python SDK.

Default model: `claude-haiku-3-5` (cost-efficient for daily batch).
Configurable: users can override the model in `config/sources.yaml`.

## Consequences

### Positive
- Claude has a 200k token context window — sufficient for long transcripts without chunking in most cases
- The `anthropic` SDK is well-maintained and includes prompt caching, which reduces cost for repeated system prompts
- Claude follows nuanced instructions well, making the configurable prompt feature viable
- Claude Haiku is highly cost-effective for batch summarisation workloads

### Negative / Trade-offs
- Requires an Anthropic API key and incurs per-token cost (mitigated by Haiku pricing and prompt caching)
- Not fully offline — the pipeline requires internet access to call the API
- Vendor lock-in to Anthropic; switching would require rewriting `src/summariser.py`

### Neutral
- The model is configurable in `sources.yaml` so users can choose Sonnet or Opus for higher quality at higher cost
- Future ADR can address local model fallback if offline operation becomes a requirement
