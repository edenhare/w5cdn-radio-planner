"""Robust YAML parser with line-level diagnostic error reporting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ruamel.yaml
from ruamel.yaml.error import MarkedYAMLError


@dataclass
class YamlDiagnosticError(Exception):
    """Detailed diagnostic information for YAML syntax and structural errors."""

    message: str
    file_path: Path | None = None
    line: int | None = None
    column: int | None = None
    snippet: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        loc = (
            f"Line {self.line}, Column {self.column}"
            if self.line is not None
            else "Unknown location"
        )
        file_info = f" in {self.file_path}" if self.file_path else ""
        res = [f"YAML Error{file_info} ({loc}): {self.message}"]
        if self.snippet:
            res.append("\nCode Snippet:\n" + self.snippet)
        if self.suggestion:
            res.append(f"\nRemediation Tip: {self.suggestion}")
        return "\n".join(res)


def _build_snippet(
    content: str, error_line: int, error_col: int | None = None, window: int = 2
) -> str:
    """Extract contextual lines around the error with a caret marker pointing to the column."""
    lines = content.splitlines()
    total_lines = len(lines)
    if not lines or error_line < 1:
        return ""

    start_idx = max(0, error_line - 1 - window)
    end_idx = min(total_lines, error_line + window)

    snippet_lines = []
    line_num_width = len(str(end_idx))

    for idx in range(start_idx, end_idx):
        current_line_num = idx + 1
        line_text = lines[idx]
        prefix = f"{current_line_num:>{line_num_width}} | "
        if current_line_num == error_line:
            snippet_lines.append(f"> {prefix}{line_text}")
            if error_col is not None and error_col > 0:
                # Add pointer
                pad = " " * (len(f"> {prefix}") + max(0, error_col - 1))
                snippet_lines.append(f"{pad}^-- problem detected here")
        else:
            snippet_lines.append(f"  {prefix}{line_text}")

    return "\n".join(snippet_lines)


def _generate_suggestion(problem: str, context: str | None) -> str:
    """Generate helpful actionable suggestion based on YAML error patterns."""
    prob_lower = (problem or "").lower()
    ctx_lower = (context or "").lower()

    if "mapping values are not allowed" in prob_lower:
        return "Check indentation or ensure colons ':' are followed by a space. E.g. 'key: value' not 'key:value'."
    if "could not find expected ':'" in prob_lower or "expected ':'" in prob_lower:
        return "A key seems to be missing its colon separator or quotes around a special character."
    if "found undefined alias" in prob_lower:
        return "Check your YAML anchor/alias references (e.g. '*anchor'). Ensure the anchor is defined earlier."
    if "while scanning a quoted scalar" in ctx_lower or "unexpected end" in prob_lower:
        return (
            "Ensure all opened quotes (' or \") are properly closed on the same line."
        )
    if "did not find expected key" in prob_lower:
        return "Check indentation alignment with preceding sibling keys."
    return "Check indentation (spaces only, no tabs) and YAML syntax structure."


def parse_yaml_text(content: str, file_path: Path | None = None) -> Any:
    """Parse YAML text and return Python data, with rich diagnostic errors on syntax failure."""
    if not content or not content.strip():
        return {}

    yaml = ruamel.yaml.YAML(typ="safe")
    try:
        return yaml.load(content)
    except MarkedYAMLError as err:
        line = None
        col = None
        problem = err.problem or "YAML syntax error"
        context = err.context

        if err.problem_mark:
            line = err.problem_mark.line + 1  # ruamel is 0-indexed
            col = err.problem_mark.column + 1
        elif err.context_mark:
            line = err.context_mark.line + 1
            col = err.context_mark.column + 1

        snippet = _build_snippet(content, line or 1, col)
        suggestion = _generate_suggestion(problem, context)

        full_message = f"{problem} ({context})" if context else problem

        raise YamlDiagnosticError(
            message=full_message,
            file_path=file_path,
            line=line,
            column=col,
            snippet=snippet,
            suggestion=suggestion,
        ) from err
    except Exception as exc:
        raise YamlDiagnosticError(
            message=str(exc),
            file_path=file_path,
            suggestion="Verify file is a valid UTF-8 encoded YAML document.",
        ) from exc


def load_yaml_file(file_path: Path | str) -> Any:
    """Read and parse a YAML file from disk with diagnostic error reporting."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"YAML configuration file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise YamlDiagnosticError(
            message=f"File encoding error: {exc}",
            file_path=path,
            suggestion="Ensure the file is encoded in UTF-8 format.",
        ) from exc

    return parse_yaml_text(text, file_path=path)
