# 0015 — Standardise agent instruction files

Date: 2026-03-07
Status: accepted

## Context

Agent instructions lived in `AGENTS.md` at the repo root, with thin stubs in `.github/copilot-instructions.md` (pointing to AGENTS.md) and `.claude/CLAUDE.md` (using `@AGENTS.md`). This created a split: the actual instructions were in one place, but different agents discovered them via different paths.

The organisation standard is `.github/copilot-instructions.md` as the sole source of truth, with no AGENTS.md. All major AI coding agents (GitHub Copilot, Copilot Workspace, Codex) discover `.github/copilot-instructions.md` automatically.

Claude Code was served via a `.claude/skills` submodule and `.claude/CLAUDE.md`. Now that Claude Code also respects `.github/copilot-instructions.md` via custom instruction injection, the separate `.claude/` setup is redundant.

## Decision

Expand `.github/copilot-instructions.md` with the full content from `AGENTS.md`. Delete `AGENTS.md` and the entire `.claude/` directory. Update `.gitmodules` to remove the `.claude/skills` entry. Update `sync-skills.yml` to only advance `.github/skills`. Add `BACKLOG.md` W-0001 item, `PROGRESS.md` entry, `CHANGELOG.md`, and this ADR.

## Consequences

- Consistent with all other repositories in the davidamitchell organisation
- All agents use the same well-known path (`.github/copilot-instructions.md`)
- No more sync required between `AGENTS.md` and the stub files
- `docs/adr/README.md` updated with this record
