"""Filesystem and configuration storage paths for RadioPlanner."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


def get_w5cdn_suite_root() -> Path:
    """Return the unified W5CDN Suite user data root directory.

    Defaults to %APPDATA%\\W5CDN on Windows and ~/.config/W5CDN on Linux/macOS,
    or overridden via W5CDN_SUITE_DIR.
    """
    suite_override = os.environ.get("W5CDN_SUITE_DIR")
    if suite_override:
        return Path(suite_override).expanduser().resolve()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return (Path(appdata) / "W5CDN").resolve()
    return (Path.home() / ".config" / "W5CDN").resolve()


def get_w5cdn_shared_dir() -> Path:
    """Return the shared W5CDN Suite directory (shared across Net-Logger, NTS, RadioPlanner)."""
    return get_w5cdn_suite_root() / "shared"


def get_shared_config_file() -> Path:
    """Return path to optional shared W5CDN Suite config.txt."""
    return get_w5cdn_shared_dir() / "config.txt"


def read_shared_config(config_path: Path | None = None) -> Dict[str, str]:
    """Read KEY=VALUE pairs from W5CDN shared config.txt if present."""
    target = config_path or get_shared_config_file()
    out: Dict[str, str] = {}
    if not target.is_file():
        return out
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def get_radioplanner_home() -> Path:
    """Return the root RadioPlanner user configuration directory.

    Resolution order:
    1. RADIOPLANNER_HOME environment override
    2. W5CDN_SUITE_DIR/RadioPlanner if W5CDN_SUITE_DIR is set
    3. Unified suite folder (%APPDATA%\\W5CDN\\RadioPlanner on Windows, ~/.config/W5CDN/RadioPlanner on POSIX),
       seamlessly preserving an existing legacy ~/.config/radioplanner/preferences.yaml if present.
    """
    env_override = os.environ.get("RADIOPLANNER_HOME")
    if env_override:
        return Path(env_override).expanduser().resolve()
    suite_dir = (get_w5cdn_suite_root() / "RadioPlanner").resolve()
    if os.environ.get("W5CDN_SUITE_DIR"):
        return suite_dir
    legacy_dir = (Path.home() / ".config" / "radioplanner").resolve()
    if not (suite_dir / "preferences.yaml").is_file() and (legacy_dir / "preferences.yaml").is_file():
        return legacy_dir
    return suite_dir


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


def get_data_dir() -> Path:
    """Directory for cached third-party data files ~/.config/radioplanner/data/"""
    return get_radioplanner_home() / "data"


def get_exports_dir() -> Path:
    """Directory for exported codeplug CSVs ~/.config/radioplanner/exports/"""
    return get_radioplanner_home() / "exports"


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
  radio_id: "baofeng_5rm"
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
    data = get_data_dir()

    home.mkdir(parents=True, exist_ok=True)
    radios.mkdir(parents=True, exist_ok=True)
    recipes.mkdir(parents=True, exist_ok=True)
    templates.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)


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
    data_dir = get_data_dir()

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
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        actions.append(f"Created data cache directory: {data_dir}")

    # 2. Seed preferences.yaml if missing (inheriting shared W5CDN OPERATOR_CALL if configured)
    if not prefs_file.is_file():
        shared_cfg = read_shared_config() if not os.environ.get("RADIOPLANNER_HOME") else {}
        default_call = (
            os.environ.get("OPERATOR_CALL") or shared_cfg.get("OPERATOR_CALL") or "N0CALL"
        ).strip().upper() or "N0CALL"
        default_prefs = {
            "callsign": default_call,
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
