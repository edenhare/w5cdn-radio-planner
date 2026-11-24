"""Manager for loading, querying, and persisting TargetRadioSpec configurations."""

from __future__ import annotations

import sys
from pathlib import Path

from core.config.paths import get_radios_dir
from core.config.yaml_loader import load_yaml_file
from core.models.radio_spec import TargetRadioSpec


def _resolve_builtin_radios_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", str(Path(sys.executable).resolve().parent)))
        frozen_dir = meipass / "core" / "resources" / "radios"
        if frozen_dir.is_dir():
            return frozen_dir
    return Path(__file__).resolve().parent.parent / "resources" / "radios"


BUILTIN_RADIOS_DIR = _resolve_builtin_radios_dir()


class RadioManager:
    """Manages radio specifications loaded from factory defaults and user directory."""

    def __init__(self, user_radios_dir: Path | None = None, builtin_dir: Path | None = None):
        self.builtin_dir = builtin_dir or BUILTIN_RADIOS_DIR
        self.user_dir = user_radios_dir or get_radios_dir()
        self._specs: dict[str, TargetRadioSpec] = {}
        self.reload()

    def reload(self) -> None:
        """Scan and load all factory radio YAMLs, followed by user overrides."""
        self._specs.clear()

        # 1. Load factory radios
        if self.builtin_dir.is_dir():
            for yaml_file in sorted(self.builtin_dir.glob("*.yaml")):
                data = load_yaml_file(yaml_file)
                spec = TargetRadioSpec.model_validate(data)
                self._specs[spec.id] = spec

        # 2. Load user overrides from ~/.config/radioplanner/radios/
        if self.user_dir.is_dir():
            for yaml_file in sorted(self.user_dir.glob("*.yaml")):
                data = load_yaml_file(yaml_file)
                spec = TargetRadioSpec.model_validate(data)
                self._specs[spec.id] = spec

    def list_radios(self) -> list[TargetRadioSpec]:
        """Return list of all registered radio specifications."""
        return list(self._specs.values())

    def get_radio(self, radio_id: str) -> TargetRadioSpec:
        """Retrieve a specific radio specification by ID, or raise KeyError."""
        if radio_id not in self._specs:
            available = ", ".join(sorted(self._specs.keys()))
            raise KeyError(f"Target radio '{radio_id}' not found. Available radios: {available}")
        return self._specs[radio_id]

    def has_radio(self, radio_id: str) -> bool:
        """Check if a radio specification exists."""
        return radio_id in self._specs

    def save_user_radio(self, spec: TargetRadioSpec) -> Path:
        """Persist a radio specification to ~/.config/radioplanner/radios/<id>.yaml."""
        import yaml

        self.user_dir.mkdir(parents=True, exist_ok=True)
        dest = self.user_dir / f"{spec.id}.yaml"
        data = spec.model_dump()
        with open(dest, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, default_flow_style=False)
        self._specs[spec.id] = spec
        return dest

    def is_user_radio(self, radio_id: str) -> bool:
        """Check whether a radio ID has an override/custom definition in user directory."""
        return (self.user_dir / f"{radio_id}.yaml").is_file()

    def delete_user_radio(self, radio_id: str) -> bool:
        """Delete a custom user radio file from user directory and reload."""
        target = self.user_dir / f"{radio_id}.yaml"
        if target.is_file():
            target.unlink()
            self.reload()
            return True
        return False
