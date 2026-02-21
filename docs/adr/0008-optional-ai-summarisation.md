# ADR-0008: Optional AI Summarisation with Link-Digest Fallback

**Date:** 2026-02-21
**Status:** Accepted

---

## Context

The original pipeline required an Anthropic API key to run at all. Two problems with that:

1. **Friction for first-time setup.** Someone evaluating the project has to provision a paid API account before they can confirm that email delivery even works.
2. **Cost for low-value runs.** If the only new content is a couple of blog posts, a Claude call is overkill — a link list is enough.

The pipeline already has a `SummaryConfig` dataclass with model and prompt settings. Adding an `enabled` flag costs one field and one branch.

---

## Decision

Add `summary.enabled` (boolean, default `true`) to `SummaryConfig` and `config/sources.yaml`.

**When `enabled: false`** (or when `ANTHROPIC_API_KEY` is absent and `enabled` is `true`):
- `summarise()` calls `format_link_digest()` instead of the Claude API.
- `format_link_digest()` groups items by source, caps at `max_items_per_source`, and formats each as `- Title (date)\n  URL`.
- `main()` logs a warning and flips `cfg.summary.enabled = False` at runtime if the key is missing.

**When `enabled: true` and the key is present:** existing behaviour, unchanged.

---

## Consequences

- Zero-cost dry runs: `make dry-run` works without any API credentials.
- Email delivery can be verified independently of AI summarisation.
- The link digest is a permanent option, not just a fallback — some users may prefer it.
- `format_link_digest()` shares the same source-grouping and `max_items_per_source` cap as the AI path, so behaviour is consistent.

---

## Alternatives considered

**Hard-fail when key missing** — the previous behaviour. Unhelpful for first-time setup; removed.

**Separate `--no-ai` CLI flag** — works for local use but can't be set per-run in the workflow without editing the YAML. Config-file toggle is easier to commit and review.

**Whisper transcription as fallback** — unrelated to this problem; deferred to a future ADR if caption quality proves insufficient.
