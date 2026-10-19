"""Manager for user preferences and secure API tokens."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from core.config.paths import (
    ensure_user_directories,
    get_preferences_file,
    get_tokens_file,
)
from core.config.yaml_loader import load_yaml_file
from core.models.preferences import ApiTokens, UserPreferences


class PreferencesManager:
    """Loads and saves user settings and API tokens."""

    def __init__(self, prefs_path: Path | None = None, tokens_path: Path | None = None):
        self.prefs_path = prefs_path or get_preferences_file()
        self.tokens_path = tokens_path or get_tokens_file()
        self.preferences = self.load_preferences()
        self.tokens = self.load_tokens()

    def load_preferences(self) -> UserPreferences:
        """Load preferences from YAML or return defaults."""
        if self.prefs_path.is_file():
            try:
                data = load_yaml_file(self.prefs_path)
                return UserPreferences.model_validate(data)
            except Exception:
                return UserPreferences()
        return UserPreferences()

    def save_preferences(self, prefs: UserPreferences) -> None:
        """Save preferences to preferences.yaml."""
        self.preferences = prefs
        ensure_user_directories()
        self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.prefs_path, "w", encoding="utf-8") as f:
            yaml.dump(prefs.model_dump(), f, sort_keys=False, default_flow_style=False)

    def load_tokens(self) -> ApiTokens:
        """Load API tokens from secure tokens file or return empty tokens."""
        if self.tokens_path.is_file():
            try:
                data = load_yaml_file(self.tokens_path)
                return ApiTokens.model_validate(data)
            except Exception:
                return ApiTokens()
        return ApiTokens()

    def save_tokens(self, tokens: ApiTokens) -> None:
        """Save API tokens with secure permissions."""
        self.tokens = tokens
        ensure_user_directories()
        self.tokens_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tokens_path, "w", encoding="utf-8") as f:
            yaml.dump(tokens.model_dump(), f, sort_keys=False, default_flow_style=False)
        # On POSIX, restrict token file permissions to 0600
        try:
            if hasattr(os, "chmod") and os.name != "nt":
                os.chmod(self.tokens_path, 0o600)
        except OSError:
            pass
