# 4. Build Tooling and Task Management

Date: 2026-10-19

## Status
Accepted

## Context
RadioPlanner must be easily sharable and executable across Windows, macOS, and Linux without fragile platform-specific shell scripts. Developers may use `just`, `make`, or standard Python tools.

## Decision
1. **Primary Platform-Agnostic Runner**:
   - Use `poethepoet` configured directly inside `pyproject.toml`. This allows any developer with Python / `uv` to execute tasks cross-platform without installing external binaries (`uv run poe test`, `uv run poe check`, `uv run poe run`).
2. **Justfile**:
   - Provide a top-level `Justfile` mapping common developer recipes (`just test`, `just lint`, `just run`) to the corresponding `uv run poe` tasks.
3. **Makefile**:
   - Provide a standard `Makefile` with POSIX targets for CI/CD pipelines and Unix developers.
4. **Package Management**:
   - Standardize on `pyproject.toml` with `uv` virtual environments for fast, reproducible dependency resolution.

## Consequences
- Guaranteed cross-platform execution on Windows without requiring GNU utilities.
- Flexible workflow options: developers can use `poe`, `just`, `make`, or raw `uv run`.
