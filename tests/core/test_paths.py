"""Unit tests for filesystem paths and startup initialization."""

from pathlib import Path
from unittest.mock import patch

from core.config.paths import (
    get_preferences_file,
    get_radioplanner_home,
    get_radios_dir,
    get_recipes_dir,
    get_shared_config_file,
    get_tokens_file,
    get_w5cdn_shared_dir,
    get_w5cdn_suite_root,
    initialize_startup_environment,
    read_shared_config,
)


def test_paths_override(tmp_path: Path):
    """Test RADIOPLANNER_HOME environment override."""
    with patch.dict("os.environ", {"RADIOPLANNER_HOME": str(tmp_path)}):
        assert get_radioplanner_home() == tmp_path.resolve()
        assert get_preferences_file() == tmp_path / "preferences.yaml"
        assert get_tokens_file() == tmp_path / "tokens"
        assert get_radios_dir() == tmp_path / "radios"
        assert get_recipes_dir() == tmp_path / "recipes"


def test_initialize_startup_environment(tmp_path: Path):
    """Test first-time startup file generation."""
    test_home = tmp_path / ".config" / "radioplanner"
    with patch.dict("os.environ", {"RADIOPLANNER_HOME": str(test_home)}):
        # 1. First run: should initialize all directories and seed files
        initialized, actions = initialize_startup_environment()
        assert initialized is True
        assert len(actions) >= 4
        assert test_home.is_dir()
        assert (test_home / "radios").is_dir()
        assert (test_home / "recipes").is_dir()
        assert (test_home / "preferences.yaml").is_file()
        assert (test_home / "tokens").is_file()
        assert (test_home / "recipes" / "sample_corridor_recipe.yaml").is_file()

        # 2. Second run: all files already exist, no new actions
        initialized2, actions2 = initialize_startup_environment()
        assert initialized2 is False
        assert actions2 == []


def test_w5cdn_suite_paths_and_shared_config(tmp_path: Path):
    """Test unified W5CDN Suite directory layout and shared config.txt seeding."""
    suite_root = tmp_path / "W5CDN"
    shared_dir = suite_root / "shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    (shared_dir / "config.txt").write_text('# Shared config\nOPERATOR_CALL="W5CDN"\nQRZ_USER=W5CDN\n', encoding="utf-8")

    with patch.dict("os.environ", {"W5CDN_SUITE_DIR": str(suite_root)}, clear=False):
        import os

        os.environ.pop("RADIOPLANNER_HOME", None)
        os.environ.pop("OPERATOR_CALL", None)
        assert get_w5cdn_suite_root() == suite_root.resolve()
        assert get_w5cdn_shared_dir() == shared_dir.resolve()
        assert get_shared_config_file() == (shared_dir / "config.txt").resolve()
        assert get_radioplanner_home() == (suite_root / "RadioPlanner").resolve()
        assert read_shared_config() == {"OPERATOR_CALL": "W5CDN", "QRZ_USER": "W5CDN"}

        initialized, _ = initialize_startup_environment()
        assert initialized is True
        prefs_text = get_preferences_file().read_text(encoding="utf-8")
        assert "callsign: W5CDN" in prefs_text
