# ADR-0007: YAML for Source Configuration

Date: 2026-02-21
Status: Accepted

## Context

Users need to configure:
- Which YouTube channels to monitor
- Which RSS/blog feeds to include
- Hacker News filter keywords and minimum score
- The summarisation prompt
- Model and token settings

This configuration must be human-editable without touching Python code.

Options considered:
1. **YAML** — human-friendly, widely used for config files
2. **TOML** — similar readability; standard for Python tooling (`pyproject.toml`)
3. **JSON** — machine-friendly but verbose and no comments
4. **`.env` file** — only suitable for flat key/value pairs; not hierarchical
5. **Python file** — too dangerous (arbitrary code execution on load)

## Decision

Use **YAML** (`config/sources.yaml`) for all user-facing configuration.

The file is loaded and validated at startup by `src/config.py` using `PyYAML`. A `dataclasses`-based schema enforces required fields and provides type hints.

## Consequences

### Positive
- YAML supports comments (`#`), making inline documentation in the config file practical
- YAML handles nested structures (channels list, keywords list, prompt block) naturally
- Most developers are familiar with YAML from GitHub Actions, Kubernetes, etc.
- Single file is easy to find and edit

### Negative / Trade-offs
- YAML has some unintuitive parsing quirks (e.g., `yes`/`no` parsed as booleans, indent sensitivity)
- PyYAML's default `yaml.load()` is unsafe; must use `yaml.safe_load()` — enforced in `src/config.py`
- No schema validation out of the box — validation is done manually in `src/config.py` with clear error messages

### Neutral
- TOML was considered equally valid; YAML was chosen because the config file is meant to be edited by non-developers who are more familiar with YAML from CI/CD contexts
- A future ADR could supersede this with a validated schema using `pydantic` + `pydantic-settings` if validation becomes complex
