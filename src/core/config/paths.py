"""Filesystem and configuration storage paths for RadioPlanner."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

import yaml


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


def get_templates_dir() -> Path:
    """Directory for custom channel template files ~/.config/radioplanner/templates/"""
    return get_radioplanner_home() / "templates"


DEFAULT_STARTER_RECIPE = """# RadioPlanner Starter Highway Corridor Recipe
version: "1.0"
mode: "ROUTE_CORRIDOR"
name: "Tyler_TX-Jackson_MS-Corridor"

corridor:
  waypoints:
    - "Tyler, TX"
    - "Shreveport, LA"
    - "Jackson, MS"
  corridor_width_miles: 25.0

radio_target:
  radio_id: "chirp_standard"
  programmer_format: "CHIRP"
  include_simplex: true
  bands:
    - "2m"
    - "70cm"
    - "WX"
  modes:
    - "FM"

sequence_order:
  - "TEMPLATE:builtin_calling_channels"
  - "ROUTE_PLAN"
  - "TEMPLATE:builtin_noaa_wx_channels"

export:
  output_dir: "./exports"
  filename_pattern: "tyler_jackson_corridor.csv"
"""


def ensure_user_directories() -> None:
    """Ensure user configuration directories exist with appropriate permissions."""
    home = get_radioplanner_home()
    radios = get_radios_dir()
    recipes = get_recipes_dir()
    templates = get_templates_dir()

    home.mkdir(parents=True, exist_ok=True)
    radios.mkdir(parents=True, exist_ok=True)
    recipes.mkdir(parents=True, exist_ok=True)
    templates.mkdir(parents=True, exist_ok=True)


def initialize_startup_environment() -> Tuple[bool, List[str]]:
    """Inspect user's home directory for RadioPlanner startup files, creating them if missing.

    Returns:
        Tuple of (was_newly_initialized: bool, list_of_actions_taken: List[str])
    """
    home = get_radioplanner_home()
    prefs_file = get_preferences_file()
    tokens_file = get_tokens_file()
    radios_dir = get_radios_dir()
    recipes_dir = get_recipes_dir()
    templates_dir = get_templates_dir()

    actions: List[str] = []

    # 1. Create directories
    if not home.exists():
        home.mkdir(parents=True, exist_ok=True)
        actions.append(f"Created home configuration directory: {home}")
    if not radios_dir.exists():
        radios_dir.mkdir(parents=True, exist_ok=True)
        actions.append(f"Created custom radios directory: {radios_dir}")
    if not recipes_dir.exists():
        recipes_dir.mkdir(parents=True, exist_ok=True)
        actions.append(f"Created recipes directory: {recipes_dir}")
    if not templates_dir.exists():
        templates_dir.mkdir(parents=True, exist_ok=True)
        actions.append(f"Created templates directory: {templates_dir}")

    # 2. Seed preferences.yaml if missing
    if not prefs_file.is_file():
        default_prefs = {
            "callsign": "N0CALL",
            "operatorName": "Radio Operator",
            "primaryDmrId": None,
            "distanceUnit": "MILES",
            "language": "ENGLISH",
            "defaultRadioId": None,
            "colorTheme": "DARK",
        }
        with open(prefs_file, "w", encoding="utf-8") as f:
            yaml.dump(default_prefs, f, sort_keys=False, default_flow_style=False)
        actions.append(f"Created initial default preferences: {prefs_file}")

    # 3. Seed tokens file if missing
    if not tokens_file.is_file():
        default_tokens = {
            "repeaterBookApiKey": None,
            "radioIdUsername": None,
            "radioIdApiKey": None,
        }
        with open(tokens_file, "w", encoding="utf-8") as f:
            yaml.dump(default_tokens, f, sort_keys=False, default_flow_style=False)
        # Apply restricted permissions on POSIX
        if hasattr(os, "chmod") and os.name != "nt":
            try:
                os.chmod(tokens_file, 0o600)
            except OSError:
                pass
        actions.append(f"Created secure tokens store: {tokens_file}")

    # 4. Seed starter recipe if recipes directory is empty
    sample_recipe = recipes_dir / "sample_corridor_recipe.yaml"
    if not any(recipes_dir.glob("*.yaml")) and not sample_recipe.is_file():
        sample_recipe.write_text(DEFAULT_STARTER_RECIPE, encoding="utf-8")
        actions.append(f"Created starter sample recipe: {sample_recipe.name}")

    return len(actions) > 0, actions
