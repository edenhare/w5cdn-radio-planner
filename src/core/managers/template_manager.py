"""Preset and Custom Codeplug Template Manager (YAML-based)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml

from core.config.paths import get_templates_dir
from core.config.yaml_loader import load_yaml_file
from core.models.channel import RadioChannel
from core.models.template import PresetTemplateFile

APP_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "resources" / "templates"


class TemplateManager:
    """Manages application-provided and user-custom codeplug channel templates in YAML format."""

    def __init__(
        self,
        custom_templates_dir: Optional[Path] = None,
        app_templates_dir: Optional[Path] = None,
    ):
        self.app_dir = app_templates_dir or APP_TEMPLATES_DIR
        self.user_dir = custom_templates_dir or get_templates_dir()
        self._app_templates: Dict[str, PresetTemplateFile] = {}
        self._user_templates: Dict[str, PresetTemplateFile] = {}
        self.reload()

    def reload(self) -> None:
        """Scan application resources and user config directory for YAML templates."""
        self._app_templates.clear()
        self._user_templates.clear()

        # 1. Load application-provided templates from resources (*.yaml, *.yml)
        if self.app_dir.is_dir():
            for yaml_file in sorted(list(self.app_dir.glob("*.yaml")) + list(self.app_dir.glob("*.yml"))):
                try:
                    data = load_yaml_file(yaml_file)
                    if isinstance(data, dict):
                        tpl = PresetTemplateFile.model_validate(data)
                        self._app_templates[tpl.id] = tpl
                except Exception:
                    pass

        # 2. Load user templates from ~/.config/radioplanner/templates/ (overrides app templates)
        if self.user_dir.is_dir():
            for yaml_file in sorted(list(self.user_dir.glob("*.yaml")) + list(self.user_dir.glob("*.yml"))):
                try:
                    data = load_yaml_file(yaml_file)
                    if isinstance(data, dict):
                        tpl = PresetTemplateFile.model_validate(data)
                        self._user_templates[tpl.id] = tpl
                except Exception:
                    pass

    def list_templates(self) -> List[PresetTemplateFile]:
        """Return list of all templates. User templates take precedence over app templates."""
        merged = {**self._app_templates, **self._user_templates}
        return list(merged.values())

    def get_template(self, template_id: str) -> PresetTemplateFile:
        """Retrieve template by ID (supporting legacy builtin_ aliases)."""
        resolved_id = self._resolve_id(template_id)
        if resolved_id in self._user_templates:
            return self._user_templates[resolved_id]
        if resolved_id in self._app_templates:
            return self._app_templates[resolved_id]
        raise KeyError(f"Template '{template_id}' not found.")

    def has_template(self, template_id: str) -> bool:
        """Check if a template exists."""
        resolved_id = self._resolve_id(template_id)
        return resolved_id in self._user_templates or resolved_id in self._app_templates

    def is_user_template(self, template_id: str) -> bool:
        """Check if the template is stored in the user configuration directory."""
        resolved_id = self._resolve_id(template_id)
        return resolved_id in self._user_templates

    def is_core_template(self, template_id: str) -> bool:
        """Check if the template exists in the core application templates directory."""
        resolved_id = self._resolve_id(template_id)
        return resolved_id in self._app_templates

    def save_core_template(self, template: PresetTemplateFile) -> Path:
        """Persist a template directly into the core application templates directory (src/core/resources/templates/<id>.yaml)."""
        self.app_dir.mkdir(parents=True, exist_ok=True)
        dest = self.app_dir / f"{template.id}.yaml"
        dump_data = template.model_dump(exclude_none=True, exclude={"fileName", "rawCsvContent"})
        with open(dest, "w", encoding="utf-8") as f:
            yaml.dump(dump_data, f, sort_keys=False, default_flow_style=False)
        self._app_templates[template.id] = template

        # Remove any stale user override so the core template file is authoritative
        for ext in (".yaml", ".yml", ".json"):
            stale_override = self.user_dir / f"{template.id}{ext}"
            if stale_override.is_file():
                stale_override.unlink()
        self._user_templates.pop(template.id, None)
        return dest

    def save_template(self, template: PresetTemplateFile) -> Path:
        """Persist a template into user config directory as YAML (~/.config/radioplanner/templates/<id>.yaml)."""
        self.user_dir.mkdir(parents=True, exist_ok=True)
        dest = self.user_dir / f"{template.id}.yaml"
        dump_data = template.model_dump(exclude_none=True, exclude={"fileName", "rawCsvContent"})
        with open(dest, "w", encoding="utf-8") as f:
            yaml.dump(dump_data, f, sort_keys=False, default_flow_style=False)
        self._user_templates[template.id] = template
        return dest

    def copy_to_user_directory(self, template_id: str) -> PresetTemplateFile:
        """Copy an application template to the user config directory as YAML for customization."""
        import shutil

        self.user_dir.mkdir(parents=True, exist_ok=True)
        resolved_id = self._resolve_id(template_id)
        src_file = self.app_dir / f"{resolved_id}.yaml"
        dest_file = self.user_dir / f"{resolved_id}.yaml"
        if src_file.is_file():
            shutil.copy2(src_file, dest_file)
            tpl = self.get_template(resolved_id)
            self._user_templates[resolved_id] = tpl
            return tpl
        tpl = self.get_template(resolved_id)
        self.save_template(tpl)
        return tpl

    def delete_user_template(self, template_id: str) -> bool:
        """Delete a user-defined or overridden YAML template and reload."""
        resolved_id = self._resolve_id(template_id)
        candidates = [
            self.user_dir / f"{resolved_id}.yaml",
            self.user_dir / f"{resolved_id}.yml",
            self.user_dir / f"{resolved_id}.json",
        ]
        deleted = False
        for target in candidates:
            if target.is_file():
                target.unlink()
                deleted = True
        if deleted:
            self.reload()
            return True
        return False

    def delete_template(self, template_id: str) -> bool:
        """Delete a custom template from user_dir or app_dir (protecting built-in system templates)."""
        resolved_id = self._resolve_id(template_id)
        deleted = self.delete_user_template(resolved_id)
        if resolved_id not in {"calling_channels", "noaa_wx_channels", "gmrs_channels"}:
            for ext in (".yaml", ".yml"):
                app_target = self.app_dir / f"{resolved_id}{ext}"
                if app_target.is_file():
                    app_target.unlink()
                    deleted = True
            if deleted:
                self.reload()
        return deleted

    def get_template_channels(self, template_id: str) -> List[RadioChannel]:
        """Return CIR RadioChannel items for the requested template."""
        tpl = self.get_template(template_id)
        return tpl.to_radio_channels()

    @staticmethod
    def _resolve_id(template_id: str) -> str:
        """Resolve legacy built-in template IDs to current IDs."""
        if template_id == "builtin_calling_channels":
            return "calling_channels"
        if template_id == "builtin_noaa_wx_channels":
            return "noaa_wx_channels"
        return template_id
