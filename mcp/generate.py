#!/usr/bin/env python3
"""Generate MCP server configuration files for all supported agent environments.

The manifest (mcp/manifest.yaml) is the single source of truth.
Run this script whenever the manifest changes, or trigger the `mcp-generate`
GitHub Actions workflow — it regenerates all configs and commits them.

Usage
-----
    python mcp/generate.py
    python mcp/generate.py --manifest mcp/manifest.yaml --out mcp/generated

Generated files
---------------
    mcp/generated/github.mcp.json        -> copy to .github/mcp.json
    mcp/generated/vscode.mcp.json        -> copy to .vscode/mcp.json
    mcp/generated/claude_desktop.json    -> merge into claude_desktop_config.json
    mcp/generated/claude_code.mcp.json   -> copy to .mcp.json (project root)
    mcp/generated/opencode.json          -> merge into ~/.config/opencode/opencode.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Target metadata
# ---------------------------------------------------------------------------

TARGETS: dict[str, dict[str, str]] = {
    "github": {
        "description": "GitHub Copilot Agent (.github/mcp.json)",
        "filename": "github.mcp.json",
        "deploy_to": ".github/mcp.json",
    },
    "vscode": {
        "description": "VS Code GitHub Copilot (.vscode/mcp.json)",
        "filename": "vscode.mcp.json",
        "deploy_to": ".vscode/mcp.json",
    },
    "claude_desktop": {
        "description": "Claude Desktop (merge into claude_desktop_config.json)",
        "filename": "claude_desktop.json",
    },
    "claude_code": {
        "description": "Claude Code CLI (.mcp.json at project root)",
        "filename": "claude_code.mcp.json",
        "deploy_to": ".mcp.json",
    },
    "opencode": {
        "description": "opencode CLI (merge into ~/.config/opencode/opencode.json)",
        "filename": "opencode.json",
    },
}

# ---------------------------------------------------------------------------
# Per-server format converters
# ---------------------------------------------------------------------------


def _to_github(server: dict[str, Any]) -> dict[str, Any]:
    """GitHub Copilot Agent format — type + command + args + optional env."""
    entry: dict[str, Any] = {
        "type": server.get("type", "stdio"),
        "command": server["command"],
        "args": server.get("args", []),
    }
    if server.get("env"):
        entry["env"] = server["env"]
    return entry


def _to_vscode(server: dict[str, Any]) -> dict[str, Any]:
    """VS Code format — command + args (no type key)."""
    entry: dict[str, Any] = {
        "command": server["command"],
        "args": server.get("args", []),
    }
    if server.get("env"):
        entry["env"] = server["env"]
    return entry


def _to_claude(server: dict[str, Any]) -> dict[str, Any]:
    """Claude Desktop / Claude Code format — command + args + optional env."""
    entry: dict[str, Any] = {
        "command": server["command"],
        "args": server.get("args", []),
    }
    if server.get("env"):
        entry["env"] = server["env"]
    return entry


def _to_opencode(server: dict[str, Any]) -> dict[str, Any]:
    """opencode format — type + command as a flat list."""
    cmd: list[str] = [server["command"]] + list(server.get("args", []))
    entry: dict[str, Any] = {"type": "local", "command": cmd}
    if server.get("env"):
        entry["environment"] = server["env"]
    return entry


_CONVERTERS: dict[str, Any] = {
    "github": _to_github,
    "vscode": _to_vscode,
    "claude_desktop": _to_claude,
    "claude_code": _to_claude,
    "opencode": _to_opencode,
}

# ---------------------------------------------------------------------------
# Per-target config builders
# ---------------------------------------------------------------------------


def _filter(servers: dict[str, Any], target: str) -> dict[str, Any]:
    """Return only the servers that list *target* in their targets list."""
    return {name: srv for name, srv in servers.items() if target in srv.get("targets", [])}


def build_github(servers: dict[str, Any]) -> dict[str, Any]:
    filtered = _filter(servers, "github")
    return {"mcpServers": {n: _to_github(s) for n, s in filtered.items()}}


def build_vscode(servers: dict[str, Any]) -> dict[str, Any]:
    filtered = _filter(servers, "vscode")
    return {"servers": {n: _to_vscode(s) for n, s in filtered.items()}}


def build_claude_desktop(servers: dict[str, Any]) -> dict[str, Any]:
    filtered = _filter(servers, "claude_desktop")
    return {"mcpServers": {n: _to_claude(s) for n, s in filtered.items()}}


def build_claude_code(servers: dict[str, Any]) -> dict[str, Any]:
    filtered = _filter(servers, "claude_code")
    return {"mcpServers": {n: _to_claude(s) for n, s in filtered.items()}}


def build_opencode(servers: dict[str, Any]) -> dict[str, Any]:
    filtered = _filter(servers, "opencode")
    return {"mcp": {n: _to_opencode(s) for n, s in filtered.items()}}


_BUILDERS: dict[str, Any] = {
    "github": build_github,
    "vscode": build_vscode,
    "claude_desktop": build_claude_desktop,
    "claude_code": build_claude_code,
    "opencode": build_opencode,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and return the YAML manifest."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid manifest: expected a YAML mapping, got {type(data)}")
    return data


def generate_all(
    manifest_path: Path,
    out_dir: Path,
    *,
    deploy: bool = False,
    repo_root: Path | None = None,
) -> list[Path]:
    """Generate all target configs; return the list of written files.

    Parameters
    ----------
    manifest_path:
        Path to ``manifest.yaml``.
    out_dir:
        Directory to write generated ``*.json`` files into.
    deploy:
        When True, also copy each generated file to its canonical repo location
        (e.g. ``.github/mcp.json``).  ``repo_root`` must be provided.
    repo_root:
        Repo root used when ``deploy=True``.
    """
    manifest = load_manifest(manifest_path)
    servers: dict[str, Any] = manifest.get("servers", {})
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for target, meta in TARGETS.items():
        config = _BUILDERS[target](servers)
        out_file = out_dir / meta["filename"]
        _write_json(out_file, config)
        written.append(out_file)

        if deploy and "deploy_to" in meta:
            if repo_root is None:
                raise ValueError("repo_root must be provided when deploy=True")
            dest = repo_root / meta["deploy_to"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            _write_json(dest, config)
            written.append(dest)

    return written


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--manifest",
        default="mcp/manifest.yaml",
        help="Path to manifest.yaml (default: mcp/manifest.yaml)",
    )
    parser.add_argument(
        "--out",
        default="mcp/generated",
        help="Output directory for generated configs (default: mcp/generated)",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Also copy configs to their canonical repo locations",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo root used with --deploy (default: .)",
    )
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    repo_root = Path(args.repo_root)

    try:
        written = generate_all(
            manifest_path,
            out_dir,
            deploy=args.deploy,
            repo_root=repo_root,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for f in written:
        print(f"  wrote  {f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
