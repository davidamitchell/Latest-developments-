# ADR-0003: Use GitHub Actions for Scheduling

Date: 2026-02-21
Status: Accepted

## Context

The pipeline needs to run once per day without manual intervention. It must persist state (deduplication store) across runs and have access to secrets (API keys, email credentials).

Options considered:
1. **GitHub Actions** with a cron schedule
2. A cron job on a VPS / cloud VM
3. AWS Lambda + EventBridge
4. Fly.io machines with a scheduled runner

## Decision

Use **GitHub Actions** with a `schedule: cron` trigger, running inside the repository's default environment.

## Consequences

### Positive
- Zero infrastructure to manage — no servers, no cloud accounts beyond GitHub
- GitHub Secrets provides secure, encrypted storage for all credentials
- Free tier is sufficient: the pipeline runs in under 5 minutes, well within the 2,000 free minutes/month
- `workflow_dispatch` enables on-demand manual runs with optional debug flag
- State file (`state/processed.json`) can be committed back to the repo by the workflow bot, providing free persistent storage
- Native integration with the repository — PRs, issues, and runs are all in one place

### Negative / Trade-offs
- GitHub Actions cron schedules are not guaranteed to fire at exact times; there can be delays of up to ~15 minutes during high-load periods
- If the repository is inactive for 60 days, scheduled workflows are disabled automatically (GitHub policy)
- Committing state back to the repo creates bot commits in the history — mitigated by using `[skip ci]` in the commit message

### Neutral
- The pipeline is stateless beyond `state/processed.json` and environment variables, making it portable to other schedulers if needed
