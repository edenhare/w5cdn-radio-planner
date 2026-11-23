"""Static AST quality tests enforcing zero bare or overly broad exceptions in web modules."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

from cli.main import VERSION as CLI_VERSION
from core.version import APP_VERSION
from web.app import APP_VERSION as WEB_VERSION

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_SOURCE_FILES = [
    PROJECT_ROOT / "src" / "web" / "app.py",
    PROJECT_ROOT / "src" / "web" / "desktop.py",
    PROJECT_ROOT / "src" / "web" / "security.py",
    PROJECT_ROOT / "src" / "web" / "state.py",
    PROJECT_ROOT / "src" / "core" / "updater.py",
    PROJECT_ROOT / "src" / "core" / "version.py",
    PROJECT_ROOT / "src" / "core" / "providers" / "callsign_lookup.py",
    PROJECT_ROOT / "src" / "core" / "providers" / "nws.py",
    PROJECT_ROOT / "scripts" / "build_standalone.py",
    PROJECT_ROOT / "scripts" / "generate_changelog.py",
]


def test_version_single_source_of_truth() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pkg_version = pyproject["project"]["version"]
    assert APP_VERSION == pkg_version
    assert WEB_VERSION == pkg_version
    assert CLI_VERSION == pkg_version


def test_web_workspace_lazy_init_has_no_import_side_effects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from web.state import WebWorkspace

    isolated_home = tmp_path / "lazy_rp_home"
    monkeypatch.setenv("RADIOPLANNER_HOME", str(isolated_home))
    ws = WebWorkspace(lazy=True)
    assert not isolated_home.exists()

    # First attribute access initializes startup environment lazily
    assert ws.prefs_mgr.preferences.callsign == "N0CALL"
    assert isolated_home.is_dir()


def test_no_bare_or_broad_exception_handlers_in_web_modules() -> None:
    violations: list[str] = []
    for path in WEB_SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    violations.append(f"{path.name}:{node.lineno}: bare 'except:' found")
                elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
                    violations.append(
                        f"{path.name}:{node.lineno}: overly broad 'except {node.type.id}:' found"
                    )
    assert not violations, "\n".join(violations)
