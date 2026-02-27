"""Tests for mcp/generate.py.

Run via: pytest mcp/tests/
Or via the mcp-generate GitHub Actions workflow.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from mcp.generate import (
    build_claude_code,
    build_claude_desktop,
    build_github,
    build_opencode,
    build_vscode,
    generate_all,
    load_manifest,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_MANIFEST_YAML = textwrap.dedent(
    """\
    version: "1"
    servers:
      fetch:
        description: Fetch a URL
        type: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-fetch"]
        targets:
          - github
          - vscode
          - claude_desktop
          - claude_code
          - opencode
      memory:
        description: Persistent memory
        type: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-memory"]
        targets:
          - vscode
          - claude_desktop
          - claude_code
          - opencode
      github_api:
        description: GitHub API
        type: stdio
        command: npx
        args: ["-y", "@modelcontextprotocol/server-github"]
        env:
          GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_PERSONAL_ACCESS_TOKEN}"
        targets:
          - vscode
          - claude_desktop
          - claude_code
          - opencode
    """
)


@pytest.fixture()
def manifest_file(tmp_path: Path) -> Path:
    f = tmp_path / "manifest.yaml"
    f.write_text(MINIMAL_MANIFEST_YAML)
    return f


@pytest.fixture()
def servers(manifest_file: Path) -> dict:
    return load_manifest(manifest_file)["servers"]


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


def test_load_manifest_returns_dict(manifest_file: Path) -> None:
    result = load_manifest(manifest_file)
    assert isinstance(result, dict)
    assert "servers" in result
    assert "version" in result


def test_load_manifest_invalid_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="Invalid manifest"):
        load_manifest(bad)


# ---------------------------------------------------------------------------
# build_github
# ---------------------------------------------------------------------------


def test_build_github_only_includes_github_targets(servers: dict) -> None:
    result = build_github(servers)
    assert "mcpServers" in result
    assert "fetch" in result["mcpServers"]
    # memory has no github target
    assert "memory" not in result["mcpServers"]
    assert "github_api" not in result["mcpServers"]


def test_build_github_server_has_type(servers: dict) -> None:
    result = build_github(servers)
    fetch = result["mcpServers"]["fetch"]
    assert fetch["type"] == "stdio"
    assert fetch["command"] == "npx"
    assert "-y" in fetch["args"]


# ---------------------------------------------------------------------------
# build_vscode
# ---------------------------------------------------------------------------


def test_build_vscode_uses_servers_key(servers: dict) -> None:
    result = build_vscode(servers)
    assert "servers" in result
    assert "mcpServers" not in result


def test_build_vscode_includes_all_vscode_targets(servers: dict) -> None:
    result = build_vscode(servers)
    assert "fetch" in result["servers"]
    assert "memory" in result["servers"]
    assert "github_api" in result["servers"]


def test_build_vscode_no_type_key(servers: dict) -> None:
    result = build_vscode(servers)
    fetch = result["servers"]["fetch"]
    assert "type" not in fetch


def test_build_vscode_env_propagated(servers: dict) -> None:
    result = build_vscode(servers)
    gh = result["servers"]["github_api"]
    assert "env" in gh
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in gh["env"]


# ---------------------------------------------------------------------------
# build_claude_desktop / build_claude_code
# ---------------------------------------------------------------------------


def test_build_claude_desktop_uses_mcpservers_key(servers: dict) -> None:
    result = build_claude_desktop(servers)
    assert "mcpServers" in result


def test_build_claude_code_uses_mcpservers_key(servers: dict) -> None:
    result = build_claude_code(servers)
    assert "mcpServers" in result


def test_claude_server_no_type_key(servers: dict) -> None:
    result = build_claude_desktop(servers)
    fetch = result["mcpServers"]["fetch"]
    assert "type" not in fetch


# ---------------------------------------------------------------------------
# build_opencode
# ---------------------------------------------------------------------------


def test_build_opencode_uses_mcp_key(servers: dict) -> None:
    result = build_opencode(servers)
    assert "mcp" in result


def test_build_opencode_command_is_list(servers: dict) -> None:
    result = build_opencode(servers)
    fetch = result["mcp"]["fetch"]
    assert fetch["type"] == "local"
    assert isinstance(fetch["command"], list)
    assert fetch["command"][0] == "npx"
    assert "-y" in fetch["command"]


def test_build_opencode_env_becomes_environment(servers: dict) -> None:
    result = build_opencode(servers)
    gh = result["mcp"]["github_api"]
    assert "environment" in gh
    assert "env" not in gh


# ---------------------------------------------------------------------------
# generate_all
# ---------------------------------------------------------------------------


def test_generate_all_creates_all_files(manifest_file: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "generated"
    written = generate_all(manifest_file, out_dir)
    filenames = {p.name for p in written}
    assert "github.mcp.json" in filenames
    assert "vscode.mcp.json" in filenames
    assert "claude_desktop.json" in filenames
    assert "claude_code.mcp.json" in filenames
    assert "opencode.json" in filenames


def test_generate_all_files_are_valid_json(manifest_file: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "generated"
    written = generate_all(manifest_file, out_dir)
    for path in written:
        data = json.loads(path.read_text())
        assert isinstance(data, dict)


def test_generate_all_deploy_copies_to_repo(manifest_file: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "generated"
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    written = generate_all(manifest_file, out_dir, deploy=True, repo_root=fake_root)
    deployed_names = {p.name for p in written}
    assert "mcp.json" in deployed_names  # .github/mcp.json and .mcp.json
    github_mcp = fake_root / ".github" / "mcp.json"
    assert github_mcp.exists()
    data = json.loads(github_mcp.read_text())
    assert "mcpServers" in data


def test_generate_all_deploy_without_root_raises(manifest_file: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repo_root"):
        generate_all(manifest_file, tmp_path / "out", deploy=True, repo_root=None)


# ---------------------------------------------------------------------------
# Real manifest smoke test
# ---------------------------------------------------------------------------


def test_real_manifest_is_valid() -> None:
    """The checked-in manifest.yaml must load and generate without errors."""
    root = Path(__file__).parent.parent.parent
    manifest_path = root / "mcp" / "manifest.yaml"
    assert manifest_path.exists(), "mcp/manifest.yaml not found"
    manifest = load_manifest(manifest_path)
    assert "servers" in manifest
    servers = manifest["servers"]
    assert len(servers) >= 1

    # Every server must have command and targets
    for name, srv in servers.items():
        assert "command" in srv, f"server '{name}' missing 'command'"
        assert "targets" in srv, f"server '{name}' missing 'targets'"
        assert len(srv["targets"]) >= 1, f"server '{name}' has empty targets"


def test_real_manifest_generates_github_config(tmp_path: Path) -> None:
    """The real manifest must produce a valid .github/mcp.json."""
    root = Path(__file__).parent.parent.parent
    manifest_path = root / "mcp" / "manifest.yaml"
    out_dir = tmp_path / "generated"
    generate_all(manifest_path, out_dir)
    github_config = out_dir / "github.mcp.json"
    assert github_config.exists()
    data = json.loads(github_config.read_text())
    assert "mcpServers" in data
    assert len(data["mcpServers"]) >= 1
