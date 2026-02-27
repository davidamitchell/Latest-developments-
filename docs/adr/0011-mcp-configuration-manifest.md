# ADR-0011: MCP Configuration Manifest

Date: 2026-02-27
Status: accepted

## Context

AI coding agents (GitHub Copilot, Claude Code, VS Code Copilot, opencode) can be extended with MCP (Model Context Protocol) servers — external tools that give the AI access to capabilities such as web fetching, file access, persistent memory, and git operations.

Each agent environment uses a **different JSON format** for its MCP configuration:

| Environment | Config file | Root key | Server shape |
|---|---|---|---|
| GitHub Copilot Agent | `.github/mcp.json` | `mcpServers` | `{type, command, args}` |
| VS Code Copilot | `.vscode/mcp.json` | `servers` | `{command, args}` (no `type`) |
| Claude Desktop / Code | project `.mcp.json` | `mcpServers` | `{command, args}` |
| opencode | `~/.config/opencode/opencode.json` | `mcp` | `{type: "local", command: [...]}` |

Without a system to manage these, the configs diverge over time: a server added to one environment is not added to others; the configs become inconsistent.

The project also uses several AI tools in parallel (GitHub Copilot Agent, Claude Code, opencode), and having MCP parity across them reduces context loss when switching between agents.

## Decision

Maintain a single **manifest file** (`mcp/manifest.yaml`) that describes every MCP server once:

- What the server does
- What npm package provides it
- Which environments it applies to
- Any required environment variable tokens

A Python generator script (`mcp/generate.py`) reads the manifest and emits a correctly-shaped JSON config for each target environment. Generated files are committed to the repo under `mcp/generated/`. The canonical locations (`.github/mcp.json`, `.vscode/mcp.json`, `.mcp.json`) are also deployed automatically.

A GitHub Actions workflow (`mcp-generate.yml`) runs the generator and tests on every change to the manifest, committing updated configs automatically.

## Consequences

### Positive
- One place to add, remove, or update an MCP server.
- GitHub Copilot Agent picks up `.github/mcp.json` automatically — no manual copy-paste.
- Generated configs for other environments are always in sync.
- Tests (`mcp/tests/test_generate.py`) catch format regressions before they land.
- Self-contained: `mcp/` can be understood and used without knowledge of the wider project.

### Negative / Trade-offs
- An extra build step (run `python mcp/generate.py`) is required when the manifest changes.
- The generated files are committed to the repo, which adds noise to PRs that touch the manifest. (Mitigated by `[skip ci]` on the bot commit.)
- `npx -y` installs packages on first use. Environments without Node.js need Node installed separately.

### Neutral
- The manifest uses the YAML format consistent with the rest of the project (`PyYAML` already in dependencies).
- The `--deploy` flag is optional — CI uses it; local runs without it leave canonical files untouched.
