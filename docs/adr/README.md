# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Latest Developments project.

ADRs document significant design decisions, the context in which they were made, and the trade-offs considered. They are immutable history — when a decision changes, a new ADR is written that supersedes the old one.

Format: [MADR (Markdown Architectural Decision Records)](https://adr.github.io/madr/)

---

## Index

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001](0001-use-python-as-primary-language.md) | Use Python as primary language | Accepted | 2026-02-21 |
| [0002](0002-use-anthropic-claude-for-summarisation.md) | Use Anthropic Claude for summarisation | Superseded by ADR-0009 | 2026-02-21 |
| [0003](0003-use-github-actions-for-scheduling.md) | Use GitHub Actions for scheduling | Accepted | 2026-02-21 |
| [0004](0004-use-youtube-transcript-api.md) | Use youtube-transcript-api for YouTube content | Accepted | 2026-02-21 |
| [0005](0005-url-based-deduplication-with-json-state-file.md) | URL-based deduplication with JSON state file | Accepted | 2026-02-21 |
| [0006](0006-email-delivery-via-smtp-with-sendgrid-option.md) | Email delivery via SMTP with SendGrid option | Accepted | 2026-02-21 |
| [0007](0007-yaml-for-source-configuration.md) | YAML for source configuration | Accepted | 2026-02-21 |
| [0008](0008-optional-ai-summarisation.md) | Optional AI summarisation with link-digest fallback | Accepted | 2026-02-21 |
| [0009](0009-switch-to-gemini-api.md) | Switch AI summarisation to Google Gemini | Accepted | 2026-02-21 |
| [0010](0010-resilient-rss-fetching.md) | Resilient RSS fetching — browser-like headers and fallback URL | Accepted | 2026-02-26 |
| [0011](0011-mcp-configuration-manifest.md) | MCP configuration manifest — single source of truth for all AI agent tool configs | Accepted | 2026-02-27 |
| [0012](0012-agent-skills-via-git-submodules.md) | Agent skills via git submodules — single upstream, two discovery paths | Accepted | 2026-02-27 |
| [0013](0013-switch-to-youtube-data-api.md) | Switch YouTube channel discovery to YouTube Data API v3 | Accepted | 2026-03-01 |
| [0014](0014-history-archiving-and-trend-analysis.md) | Digest history archiving and trend analysis | Accepted | 2026-03-02 |
| [0015](0015-standardise-agent-instructions.md) | Standardise agent instruction files | Accepted | 2026-03-07 |
| [0016](0016-youtube-transcript-proxy-support.md) | YouTube transcript proxy support | Accepted | 2026-03-17 |

---

## How to Add an ADR

1. Copy the template below into a new file `NNNN-short-title.md` (zero-padded, sequential)
2. Fill in all sections
3. Update the index table above
4. Commit with message: `docs: add ADR-NNNN <short title>`

### Template

```markdown
# ADR-NNNN: Title

Date: YYYY-MM-DD
Status: proposed | accepted | superseded by [ADR-XXXX] | deprecated

## Context

What is the problem or situation forcing a decision?

## Decision

What have we decided to do?

## Consequences

### Positive
- ...

### Negative / Trade-offs
- ...

### Neutral
- ...
```
