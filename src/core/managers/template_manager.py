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
from core.special_channels.calling import get_national_calling_channels
from core.special_channels.weather import get_noaa_wx_channels


class TemplateManager:
    """Manages built-in and user-defined codeplug channel templates."""

    def __init__(self, custom_templates_dir: Optional[Path] = None):
        self.templates_dir = custom_templates_dir or get_templates_dir()
        self._custom_templates: Dict[str, PresetTemplateFile] = {}
        self.reload()

    def reload(self) -> None:
        """Scan ~/.config/radioplanner/templates/ for custom JSON/CSV templates."""
        self._custom_templates.clear()
        if self.templates_dir.is_dir():
            for json_file in sorted(self.templates_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    tpl = PresetTemplateFile.model_validate(data)
                    self._custom_templates[tpl.id] = tpl
                except Exception:
                    pass

    def list_templates(self) -> List[PresetTemplateFile]:
        """Return list of all built-in and custom templates."""
        builtin_calling = PresetTemplateFile(
            id="builtin_calling_channels",
            name="National Calling Frequencies",
            description="Standard VHF, UHF, 1.25m, 6m, 10m, and GMRS national calling frequencies",
            tagText="CALLING",
            tagColorHex="#FFC107",
            fileName="calling_channels.csv",
        )
        builtin_wx = PresetTemplateFile(
            id="builtin_noaa_wx_channels",
            name="NOAA Weather Radio Channels",
            description="Standard 7 NOAA Weather Radio WX 1-7 channels (162.400-162.550 MHz)",
            tagText="WX",
            tagColorHex="#2196F3",
            fileName="noaa_wx_channels.csv",
        )
        templates = [builtin_calling, builtin_wx]
        templates.extend(self._custom_templates.values())
        return templates

    def get_template(self, template_id: str) -> PresetTemplateFile:
        """Retrieve template metadata by ID."""
        for t in self.list_templates():
            if t.id == template_id:
                return t
        raise KeyError(f"Template '{template_id}' not found.")

    def get_template_channels(self, template_id: str) -> List[RadioChannel]:
        """Return CIR RadioChannel items for the template."""
        if template_id == "builtin_calling_channels":
            return get_national_calling_channels()
        elif template_id == "builtin_noaa_wx_channels":
            return get_noaa_wx_channels()
        elif template_id in self._custom_templates:
            tpl = self._custom_templates[template_id]
            return self._parse_csv_channels(tpl.rawCsvContent, tag=tpl.tagText)
        raise KeyError(f"Unknown template ID: '{template_id}'")

    def save_template(self, template: PresetTemplateFile) -> Path:
        """Persist a new or modified custom template to JSON."""
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        dest = self.templates_dir / f"{template.id}.json"
        dest.write_text(json.dumps(template.model_dump(), indent=2), encoding="utf-8")
        self._custom_templates[template.id] = template
        return dest

    @staticmethod
    def _parse_csv_channels(raw_csv: str, tag: str = "PRESET") -> List[RadioChannel]:
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

            ch = RadioChannel(
                number=idx,
                name=name,
                rxFreq=rx_freq,
                txFreq=tx_freq,
                offset=abs(rx_freq - tx_freq),
                offsetDir="+" if tx_freq > rx_freq else "-" if tx_freq < rx_freq else "off",
                mode=mode,
                power=power,
                specialType="CUSTOM",
                comment=f"[{tag}] {comment}".strip(),
            )
            channels.append(ch)

        return channels
