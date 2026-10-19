"""Preset Template Models in YAML format."""

from __future__ import annotations

import csv
import io
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.models.channel import RadioChannel


class TemplateChannelItem(BaseModel):
    """Channel definition entry within a YAML template."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Channel memory display name tag")
    rxFreq: float = Field(..., description="Receive frequency in MHz")
    txFreq: Optional[float] = Field(default=None, description="Transmit frequency in MHz")
    offset: Optional[float] = Field(default=None, description="Frequency offset in MHz")
    offsetDir: str = Field(default="off", description="Offset direction: '+', '-', or 'off'")
    mode: str = Field(default="FM", description="Operating mode: FM, AM, DMR, etc.")
    power: str = Field(default="High", description="Power level: High, Mid, Low")
    toneMode: str = Field(default="None", description="Tone mode: None, Tone, TSQL, DCS")
    ctcss: str = Field(default="None", description="Transmit CTCSS tone in Hz or 'None'")
    rxCtcss: str = Field(default="None", description="Receive CTCSS tone in Hz or 'None'")
    dcs: str = Field(default="None", description="DCS code or 'None'")
    rxDcs: str = Field(default="None", description="Receive DCS code or 'None'")
    dcsPolarity: str = Field(default="NN", description="DCS polarity: NN, NR, RN, RR")
    bandwidth: str = Field(default="25KHz", description="Channel bandwidth: 25KHz or 12.5KHz")
    specialType: Optional[str] = Field(default=None, description="Special channel classification")
    comment: str = Field(default="", description="Explanatory comment")

    def to_radio_channel(self, number: int, default_special_type: str = "CUSTOM", tag: str = "") -> RadioChannel:
        """Convert template channel item to CIR RadioChannel."""
        tx_freq = self.txFreq if self.txFreq is not None else self.rxFreq
        offset = self.offset if self.offset is not None else abs(self.rxFreq - tx_freq)
        offset_dir = self.offsetDir
        if offset_dir == "off" and offset > 1e-5:
            offset_dir = "+" if tx_freq > self.rxFreq else "-"

        spec_type = self.specialType or default_special_type
        comment_str = self.comment
        if tag and f"[{tag}]" not in comment_str:
            comment_str = f"[{tag}] {comment_str}".strip()

        return RadioChannel(
            number=number,
            name=self.name,
            rxFreq=self.rxFreq,
            txFreq=tx_freq,
            offset=offset,
            offsetDir=offset_dir,
            mode=self.mode,
            power=self.power,
            toneMode=self.toneMode,
            ctcss=self.ctcss,
            rxCtcss=self.rxCtcss,
            dcs=self.dcs,
            rxDcs=self.rxDcs,
            dcsPolarity=self.dcsPolarity,
            bandwidth=self.bandwidth,
            specialType=spec_type,
            comment=comment_str,
        )


class PresetTemplateFile(BaseModel):
    """Preset or user-defined codeplug channel template definition in YAML."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Unique template identifier (e.g. calling_channels)")
    name: str = Field(..., description="Template title")
    description: str = Field(default="", description="Description of template purpose")
    tagText: str = Field(
        default="PRESET",
        description="Badge chip label text (e.g. CALLING, WX, SKYWARN)",
    )
    tagColorHex: str = Field(default="#00BCD4", description="Hex color for tag badge")
    channels: List[TemplateChannelItem] = Field(
        default_factory=list,
        description="List of structured channel definitions",
    )
    fileName: Optional[str] = None
    rawCsvContent: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_raw_csv(cls, data: Any) -> Any:
        """Gracefully migrate legacy CSV string input to structured channel items."""
        if isinstance(data, dict):
            raw_csv = data.get("rawCsvContent")
            channels = data.get("channels")
            if raw_csv and not channels:
                parsed_channels = []
                reader = csv.DictReader(io.StringIO(raw_csv.strip()))
                for row in reader:
                    name = row.get("Name") or row.get("Channel Name") or "CH"
                    rx_str = (
                        row.get("RX Frequency") or row.get("Frequency") or row.get("Receive Frequency") or "146.520"
                    )
                    tx_str = row.get("TX Frequency") or row.get("Transmit Frequency") or rx_str
                    mode = row.get("Mode") or row.get("Operating Mode") or "FM"
                    power = row.get("Power") or row.get("Tx Power") or "High"
                    comment = row.get("Comment") or ""
                    try:
                        rx = float(rx_str)
                        tx = float(tx_str)
                    except ValueError:
                        continue
                    parsed_channels.append({
                        "name": name,
                        "rxFreq": rx,
                        "txFreq": tx,
                        "mode": mode,
                        "power": power,
                        "comment": comment,
                    })
                data["channels"] = parsed_channels
        return data

    def to_radio_channels(self) -> List[RadioChannel]:
        """Convert all template channel items to CIR RadioChannel instances."""
        spec_type = "CUSTOM"
        if "calling" in self.id.lower() or self.tagText.upper() == "CALLING":
            spec_type = "CALLING"
        elif "wx" in self.id.lower() or self.tagText.upper() == "WX":
            spec_type = "WX"
        elif "gmrs" in self.id.lower():
            spec_type = "GMRS"

        return [
            item.to_radio_channel(number=idx, default_special_type=spec_type, tag=self.tagText)
            for idx, item in enumerate(self.channels, start=1)
        ]
