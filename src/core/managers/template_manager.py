"""Preset and Custom Codeplug Template Manager."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Dict, List, Optional

from core.config.paths import get_templates_dir
from core.models.channel import RadioChannel
from core.models.template import PresetTemplateFile

APP_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "resources" / "templates"


class TemplateManager:
    """Manages application-provided and user-custom codeplug channel templates."""

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
        """Scan application resources and user config directory for JSON templates."""
        self._app_templates.clear()
        self._user_templates.clear()

        # 1. Load application-provided templates from resources
        if self.app_dir.is_dir():
            for json_file in sorted(self.app_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    tpl = PresetTemplateFile.model_validate(data)
                    self._app_templates[tpl.id] = tpl
                except Exception:
                    pass

        # 2. Load user templates from ~/.config/radioplanner/templates/ (overrides app templates)
        if self.user_dir.is_dir():
            for json_file in sorted(self.user_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
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

    def save_template(self, template: PresetTemplateFile) -> Path:
        """Persist a template into user config directory (~/.config/radioplanner/templates/)."""
        self.user_dir.mkdir(parents=True, exist_ok=True)
        dest = self.user_dir / f"{template.id}.json"
        dest.write_text(json.dumps(template.model_dump(), indent=2), encoding="utf-8")
        self._user_templates[template.id] = template
        return dest

    def copy_to_user_directory(self, template_id: str) -> PresetTemplateFile:
        """Copy an application template to the user config directory for customization."""
        tpl = self.get_template(template_id)
        self.save_template(tpl)
        return tpl

    def delete_user_template(self, template_id: str) -> bool:
        """Delete a user-defined or overridden template and reload."""
        resolved_id = self._resolve_id(template_id)
        target = self.user_dir / f"{resolved_id}.json"
        if target.is_file():
            target.unlink()
            self.reload()
            return True
        return False

    def get_template_channels(self, template_id: str) -> List[RadioChannel]:
        """Return CIR RadioChannel items for the requested template."""
        tpl = self.get_template(template_id)
        return self._parse_csv_channels(tpl.rawCsvContent, tag=tpl.tagText, tpl_id=tpl.id)

    @staticmethod
    def _resolve_id(template_id: str) -> str:
        """Resolve legacy built-in template IDs to current IDs."""
        if template_id == "builtin_calling_channels":
            return "calling_channels"
        if template_id == "builtin_noaa_wx_channels":
            return "noaa_wx_channels"
        return template_id

    @staticmethod
    def _parse_csv_channels(raw_csv: str, tag: str = "PRESET", tpl_id: str = "") -> List[RadioChannel]:
        """Parse raw CSV channel rows into CIR RadioChannel items."""
        channels: List[RadioChannel] = []
        if not raw_csv or not raw_csv.strip():
            return channels

        reader = csv.DictReader(io.StringIO(raw_csv.strip()))
        for idx, row in enumerate(reader, start=1):
            name = row.get("Name") or row.get("Channel Name") or f"CH{idx}"
            rx_str = row.get("RX Frequency") or row.get("Frequency") or row.get("Receive Frequency") or "146.520"
            tx_str = row.get("TX Frequency") or row.get("Transmit Frequency") or rx_str
            mode = row.get("Mode") or row.get("Operating Mode") or "FM"
            power = row.get("Power") or row.get("Tx Power") or "High"
            comment = row.get("Comment") or ""

            try:
                rx_freq = float(rx_str)
                tx_freq = float(tx_str)
            except ValueError:
                continue

            # Determine specialType
            special_type = "CUSTOM"
            if "calling" in tpl_id.lower() or tag.upper() == "CALLING":
                special_type = "CALLING"
            elif "wx" in tpl_id.lower() or tag.upper() == "WX":
                special_type = "WX"
            elif "gmrs" in tpl_id.lower():
                special_type = "GMRS"

            ch = RadioChannel(
                number=idx,
                name=name,
                rxFreq=rx_freq,
                txFreq=tx_freq,
                offset=abs(rx_freq - tx_freq),
                offsetDir="+" if tx_freq > rx_freq else "-" if tx_freq < rx_freq else "off",
                mode=mode,
                power=power,
                specialType=special_type,
                comment=f"[{tag}] {comment}".strip() if f"[{tag}]" not in comment else comment,
            )
            channels.append(ch)

        return channels
