# MCP Server Configuration

This directory is the **single source of truth** for all MCP (Model Context Protocol) server configurations used in this repository.

MCP is an open standard that lets AI assistants (GitHub Copilot, Claude, opencode, etc.) connect to external tools as first-class capabilities. See [modelcontextprotocol.io](https://modelcontextprotocol.io) for the full specification.

---

## Quick start — GitHub Copilot Agent

The `.github/mcp.json` file in this repo is picked up **automatically** by the GitHub Copilot Coding Agent. No action is needed beyond merging this PR.

To use the same configuration in your personal GitHub Copilot settings (GitHub.com → Settings → Copilot → MCP servers), paste the contents of [`generated/github.mcp.json`](generated/github.mcp.json).

---

## Quick start — other environments

| Environment | File to use | Where to put it |
|---|---|---|
| VS Code (Copilot) | [`generated/vscode.mcp.json`](generated/vscode.mcp.json) | `.vscode/mcp.json` in your project |
| Claude Desktop | [`generated/claude_desktop.json`](generated/claude_desktop.json) | Merge into `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows) |
| Claude Code CLI | [`generated/claude_code.mcp.json`](generated/claude_code.mcp.json) | `.mcp.json` at the project root (already deployed here) |
| opencode | [`generated/opencode.json`](generated/opencode.json) | Merge into `~/.config/opencode/opencode.json` |

All of these files are **auto-generated** from [`manifest.yaml`](manifest.yaml). Edit the manifest, not the generated files.

---

## Directory layout

```
mcp/
├── manifest.yaml          # Source of truth — edit this
├── generate.py            # Converts manifest → all target formats
├── requirements.txt       # Python deps for generate.py (PyYAML)
├── README.md              # This file
├── tests/
│   └── test_generate.py   # pytest tests for generate.py
└── generated/
    ├── github.mcp.json    # GitHub Copilot Agent  → .github/mcp.json
    ├── vscode.mcp.json    # VS Code               → .vscode/mcp.json
    ├── claude_desktop.json # Claude Desktop       → merge into config
    ├── claude_code.mcp.json # Claude Code CLI     → .mcp.json
    └── opencode.json      # opencode              → merge into config
```

---

## Servers included

| Server | What it does | GitHub | VS Code | Claude | opencode |
|---|---|:---:|:---:|:---:|:---:|
| **fetch** | Fetch any URL + extract readable text | ✓ | ✓ | ✓ | ✓ |
| **sequential_thinking** | Structured step-by-step reasoning | ✓ | ✓ | ✓ | ✓ |
| **time** | Current time + timezone conversion | ✓ | ✓ | ✓ | ✓ |
| **memory** | Persistent knowledge graph across sessions | — | ✓ | ✓ | ✓ |
| **git** | Local git log/diff/blame/show | — | ✓ | ✓ | ✓ |
| **filesystem** | Read/write local files | — | ✓ | ✓ | ✓ |
| **github** | GitHub issues/PRs/repos/CI (needs PAT) | — | ✓ | ✓ | ✓ |

`—` means excluded because it's not meaningful in that environment (e.g. `filesystem` inside the Copilot Agent's ephemeral sandbox, or `github` when the Agent already has built-in access).

All servers are from the official [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) repository and are installed on-demand via `npx -y`.

---

## Editing the manifest

Open [`manifest.yaml`](manifest.yaml) and add or modify a server entry:

```yaml
servers:
  my_new_server:
    description: What this server does
    package: "@scope/server-name"
    type: stdio
    command: npx
    args:
      - "-y"
      - "@scope/server-name"
    env:                              # optional — only include if needed
      MY_API_KEY: "${MY_API_KEY}"
    targets:
      - github                        # which environments get this server
      - vscode
      - claude_desktop
      - claude_code
      - opencode
```

Then regenerate (see below).

---

## Regenerating configs

### Locally

```bash
# Install the one dependency (already in the project's dev extras)
pip install -r mcp/requirements.txt

# Regenerate generated/ only
python mcp/generate.py

# Regenerate AND deploy canonical locations (.github/mcp.json etc.)
python mcp/generate.py --deploy

# Custom paths
python mcp/generate.py --manifest mcp/manifest.yaml --out mcp/generated --deploy --repo-root .
```

### Via GitHub Actions

Trigger the **MCP Generate** workflow from the Actions tab. It regenerates all configs, runs the tests, and commits the result:

1. Go to **Actions** → **MCP Generate**
2. Click **Run workflow**
3. A bot commit will appear with the updated files

The workflow also runs automatically on any push that changes `mcp/manifest.yaml`.

---

## Running the tests

The tests live in `mcp/tests/` and are independent of the main project test suite.

```bash
# From repo root (pytest is in dev extras)
pytest mcp/tests/ -v

# Or, if only the MCP deps are installed:
pip install -r mcp/requirements.txt pytest
pytest mcp/tests/ -v
```

The test suite covers:
- `load_manifest` — YAML loading and validation
- Per-target builders — correct JSON structure for each environment
- Key format differences (e.g. VS Code uses `servers` not `mcpServers`; opencode uses `command` as a flat list)
- `generate_all` — file creation, JSON validity, deploy mode
- Smoke test on the real `manifest.yaml` to catch manifest regressions

---

## Environment variable tokens

Servers that require API keys (e.g. `github`) use `${MY_VAR}` placeholder syntax in the manifest. This is intentional — **never put real secrets in the manifest**.

Set the variables in your shell or `.env` file before starting the AI tool:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
```

For VS Code, you can also add environment variables to your user settings or `launch.json`.

---

## How this fits with the project

| Backlog item | How MCP helps |
|---|---|
| 5.2 — fetch linked article text from HN | `fetch` server lets the AI retrieve and read article URLs directly |
| 8.3 — multi-day trend context | `memory` server persists facts across sessions, enabling multi-day theme tracking |
| General debugging | `git`, `filesystem`, and `sequential_thinking` make debugging the pipeline faster |

---

## ADR

The design decision behind this manifest system is documented in [ADR-0011](../docs/adr/0011-mcp-configuration-manifest.md).
