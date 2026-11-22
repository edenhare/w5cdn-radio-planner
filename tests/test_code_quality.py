"""Static AST quality tests enforcing zero bare or overly broad exceptions in web modules."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_SOURCE_FILES = [
    PROJECT_ROOT / "src" / "web" / "app.py",
    PROJECT_ROOT / "src" / "web" / "desktop.py",
    PROJECT_ROOT / "src" / "web" / "security.py",
    PROJECT_ROOT / "src" / "web" / "state.py",
    PROJECT_ROOT / "src" / "core" / "updater.py",
    PROJECT_ROOT / "src" / "core" / "providers" / "callsign_lookup.py",
    PROJECT_ROOT / "src" / "core" / "providers" / "nws.py",
    PROJECT_ROOT / "scripts" / "build_standalone.py",
    PROJECT_ROOT / "scripts" / "generate_changelog.py",
]


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
