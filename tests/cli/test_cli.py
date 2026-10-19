"""Tests for CLI flags and commands."""

import sys
from pathlib import Path
from unittest.mock import patch

from cli.main import build_parser, main

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "configurations"


def test_cli_parser_flags():
    """Verify CLI parser options."""
    parser = build_parser()
    args = parser.parse_args(["--list-radios"])
    assert args.list_radios is True

    args = parser.parse_args(["--validate", "test.yaml"])
    assert args.validate == "test.yaml"

    args = parser.parse_args(["--config", "recipe.yaml"])
    assert args.config == "recipe.yaml"


def test_cli_list_radios():
    """Test --list-radios outputs hardware profiles and exits with 0."""
    with patch.object(sys, "argv", ["radioplanner", "--list-radios"]):
        ret = main()
        assert ret == 0


def test_cli_validate_valid_recipe():
    """Test --validate with a valid recipe returns 0."""
    valid_file = str(FIXTURES_DIR / "route_corridor_tx_la_ms.yaml")
    with patch.object(sys, "argv", ["radioplanner", "--validate", valid_file]):
        ret = main()
        assert ret == 0


def test_cli_validate_invalid_syntax():
    """Test --validate with broken syntax returns 1 and renders diagnostic panel."""
    invalid_file = str(FIXTURES_DIR / "invalid_syntax_bad_indent.yaml")
    with patch.object(sys, "argv", ["radioplanner", "--validate", invalid_file]):
        ret = main()
        assert ret == 1


def test_cli_run_config(tmp_path: Path):
    """Test --config executes the recipe directly and exits 0."""
    valid_file = str(FIXTURES_DIR / "aviation_tyler_regional.yaml")
    with patch.object(sys, "argv", ["radioplanner", "--config", valid_file]):
        ret = main()
        assert ret == 0
