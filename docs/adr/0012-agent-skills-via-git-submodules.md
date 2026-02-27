# ADR-0012: Agent Skills via Git Submodules

Date: 2026-02-27
Status: accepted

## Context

GitHub Copilot's Coding Agent and Claude Code both support *skills* — modular instruction files that the agent loads automatically when a task matches the skill's `description`. Skills allow domain-specific behaviour (e.g. "manage the backlog", "remove AI slop") to be separated from the core agent instructions.

The project uses two AI agents in parallel:

| Agent | Discovery path |
|---|---|
| GitHub Copilot Coding Agent | `.github/skills/<name>/SKILL.md` |
| Claude Code | `.claude/skills/<name>/SKILL.md` |

The skills themselves are maintained in a separate repository, [`davidamitchell/Skills`](https://github.com/davidamitchell/Skills), so they can be reused across projects without duplication.

### Options considered

**Option A — Copy files at sync time.** A workflow copies `SKILL.md` files from the upstream repo into `.github/skills/` on a schedule. Simple, but requires a bespoke sync script; skills for Claude Code would need a second copy or a second sync step; the local files diverge from upstream between syncs.

**Option B — Single submodule with symlinks.** Mount the Skills repo at `.github/skills-src`, then symlink individual skill directories into `.github/skills/` and `.claude/skills/`. Symlinks are fragile on Windows and in some CI environments; the approach is hard to explain and maintain.

**Option C — Two submodules, same upstream.** Mount the Skills repo as a submodule at both `.github/skills` and `.claude/skills`. Because the Skills repo stores skills at the repo root (`<name>/SKILL.md`), the submodule path resolves to exactly `<mount>/<name>/SKILL.md` — the correct discovery path for each agent. A single weekly workflow advances both submodule pointers together.

This approach mirrors the MCP manifest pattern (ADR-0011): one upstream source of truth, deployed automatically to all consumers.

## Decision

Use **two git submodules** pointing at the same upstream repository:

- `.github/skills` → `https://github.com/davidamitchell/Skills.git`
- `.claude/skills` → `https://github.com/davidamitchell/Skills.git`

A weekly GitHub Actions workflow (`sync-skills.yml`) runs `git submodule update --remote` on both paths and commits only if a pointer changed. The upstream Skills repo is structured with skill directories at the root (`<name>/SKILL.md`), so no path manipulation is needed.

## Consequences

### Positive
- Single source of truth: adding a skill to `davidamitchell/Skills` makes it available to both agents on the next sync.
- No bespoke copy/transform logic — git's native submodule machinery handles everything.
- Both agents always point at the same Skills commit, eliminating skew.
- Consistent with the MCP manifest pattern (ADR-0011): one upstream, multiple deployment targets.

### Negative / Trade-offs
- Cloning the repo requires `git clone --recurse-submodules` (or a subsequent `git submodule update --init`). CI workflows must use `submodules: true` in `actions/checkout`.
- Two submodule entries for the same upstream repo is unusual; the reason must be documented (it is — here, and in `AGENTS.md`).
- Advancing the submodule pointers requires a bot commit, which adds a weekly commit to `main` history.

### Neutral
- `.gitmodules` records both paths with the same URL. Git handles multiple submodules from the same remote without issues.
- The upstream Skills repo had to be restructured (skills moved from `skills/<name>/` to `<name>/`) before this approach could work. That was done in `davidamitchell/Skills` PR #4.
