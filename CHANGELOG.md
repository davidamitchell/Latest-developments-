# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- `.github/copilot-instructions.md` (full content, replaces AGENTS.md stub)
- `BACKLOG.md` work item W-0001 for the standardisation pass
- `PROGRESS.md` entry for 2026-03-07 session
- `CHANGELOG.md` (this file)
- `docs/adr/0015-standardise-agent-instructions.md`

### Removed
- `AGENTS.md` (content moved to `.github/copilot-instructions.md`)
- `.claude/` directory and `.claude/skills` submodule

### Changed
- `.gitmodules`: removed `.claude/skills` entry
- `.github/workflows/sync-skills.yml`: removed `.claude/skills` sync step; simplified to single submodule
- `README.md`: updated to reflect current structure; AI agents directed to `.github/copilot-instructions.md`
