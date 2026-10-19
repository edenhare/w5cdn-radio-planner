"""Tri-state tests for YAML parser and line-level diagnostics."""

from pathlib import Path

import pytest

from core.config.yaml_loader import YamlDiagnosticError, load_yaml_file, parse_yaml_text

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "configurations"


def test_yaml_loader_good_data():
    """Good Data: Successfully parse valid YAML document."""
    good_yaml = """
    version: "1.0"
    mode: "ROUTE_CORRIDOR"
    name: "Valid Test Route"
    corridor:
      waypoints:
        - "Tyler, TX"
        - "Shreveport, LA"
      corridor_width_miles: 25.0
    """
    data = parse_yaml_text(good_yaml)
    assert data["version"] == "1.0"
    assert data["mode"] == "ROUTE_CORRIDOR"
    assert len(data["corridor"]["waypoints"]) == 2


def test_yaml_loader_bad_data_syntax_diagnostic():
    """Bad Data: Syntax error triggers YamlDiagnosticError with line, column, and snippet."""
    bad_yaml_file = FIXTURES_DIR / "invalid_syntax_bad_indent.yaml"
    with pytest.raises(YamlDiagnosticError) as exc_info:
        load_yaml_file(bad_yaml_file)

    err = exc_info.value
    assert err.line is not None
    assert err.column is not None
    assert err.snippet is not None
    assert "^-- problem detected here" in err.snippet
    assert err.suggestion is not None
    assert "indentation" in err.suggestion.lower() or "colon" in err.suggestion.lower()


def test_yaml_loader_bad_data_unclosed_quotes():
    """Bad Data: Unclosed quote syntax error."""
    bad_quote_yaml = """
    name: "Unclosed string literal
    mode: ROUTE_CORRIDOR
    """
    with pytest.raises(YamlDiagnosticError) as exc_info:
        parse_yaml_text(bad_quote_yaml)

    err = exc_info.value
    assert err.line is not None
    assert err.snippet is not None


def test_yaml_loader_missing_data_empty_content():
    """Missing Data: Empty content returns empty dict without crashing."""
    assert parse_yaml_text("") == {}
    assert parse_yaml_text("   \n\n  ") == {}


def test_yaml_loader_missing_file():
    """Missing Data: Non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_yaml_file(Path("non_existent_file.yaml"))
