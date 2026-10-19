"""Unit tests for filesystem paths and startup initialization."""

from pathlib import Path
from unittest.mock import patch

from core.config.paths import (
    get_preferences_file,
    get_radioplanner_home,
    get_radios_dir,
    get_recipes_dir,
    get_tokens_file,
    initialize_startup_environment,
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
