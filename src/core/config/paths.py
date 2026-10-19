"""Filesystem and configuration storage paths for RadioPlanner."""

from __future__ import annotations

import os
from pathlib import Path


def get_radioplanner_home() -> Path:
    """Return the root RadioPlanner user configuration directory.

    Defaults to ~/.config/radioplanner across all platforms,
    or overridden via RADIOPLANNER_HOME environment variable.
    """
    env_override = os.environ.get("RADIOPLANNER_HOME")
    if env_override:
        path = Path(env_override).expanduser().resolve()
    else:
        path = (Path.home() / ".config" / "radioplanner").resolve()
    return path


def get_preferences_file() -> Path:
    """Path to ~/.config/radioplanner/preferences.yaml"""
    return get_radioplanner_home() / "preferences.yaml"


def get_tokens_file() -> Path:
    """Path to ~/.config/radioplanner/tokens"""
    return get_radioplanner_home() / "tokens"


def get_radios_dir() -> Path:
    """Directory for custom/user radio specifications ~/.config/radioplanner/radios/"""
    return get_radioplanner_home() / "radios"


def get_recipes_dir() -> Path:
    """Directory for saved replayable run recipes ~/.config/radioplanner/recipes/"""
    return get_radioplanner_home() / "recipes"


def ensure_user_directories() -> None:
    """Ensure user configuration directories exist with appropriate permissions."""
    home = get_radioplanner_home()
    radios = get_radios_dir()
    recipes = get_recipes_dir()

    home.mkdir(parents=True, exist_ok=True)
    radios.mkdir(parents=True, exist_ok=True)
    recipes.mkdir(parents=True, exist_ok=True)
