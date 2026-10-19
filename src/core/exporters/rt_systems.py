"""RT Systems Programmer CSV Exporters."""

from __future__ import annotations

import csv
import io
from typing import Any

from core.exporters.base import BaseExporter
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec


class RtSystemsExporter(BaseExporter):
    """Formats codeplug channels according to target radio RT Systems column specifications."""

    def to_csv_string(self, codeplug: Codeplug, spec: TargetRadioSpec) -> str:
        prepared = self.prepare_channels(codeplug, spec)
        columns = spec.columns
        if not columns:
            columns = [
                "Receive Frequency",
                "Transmit Frequency",
                "Offset Frequency",
                "Offset direction",
                "Operating Mode",
                "Name",
                "Tone Mode",
                "CTCSS",
                "Rx CTCSS",
                "DCS",
                "Rx DCS",
                "DCS Polarity",
                "Tx Power",
                "Comment",
            ]

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(columns)

        for ch in prepared.channels:
            row_dict = self._map_channel_to_dict(ch, spec)
            row = [row_dict.get(col, "") for col in columns]
            writer.writerow(row)

        return output.getvalue()

    def _map_channel_to_dict(self, ch: RadioChannel, spec: TargetRadioSpec) -> dict[str, Any]:
        """Map CIR channel attributes to standard RT Systems column names."""
        offset_dir = ch.offsetDir if ch.offsetDir in {"+", "-", "off"} else "off"
        if abs(ch.offset) < 1e-5:
            offset_dir = "off"

        tone_mode = ch.toneMode
        if tone_mode.upper() in {"NONE", "OFF"}:
            tone_mode = "None"

        tx_power = ch.power.capitalize() if ch.power else "High"

        # Determine DMR vs Analog for DMR-6X2
        ch_type = "Digital" if ch.mode.upper() == "DMR" or ch.colorCode is not None else "Analog"

        return {
            "Channel Number": ch.number,
            "Receive Frequency": f"{ch.rxFreq:.5f}",
            "Transmit Frequency": f"{ch.txFreq:.5f}",
            "Offset Frequency": f"{ch.offset:.5f}",
            "Offset direction": offset_dir,
            "Operating Mode": ch.mode,
            "Show Name": "Yes",
            "Name": ch.name,
            "Channel Name": ch.name,
            "Channel Type": ch_type,
            "Tone Mode": tone_mode,
            "CTCSS": ch.ctcss if ch.ctcss != "None" else "88.5",
            "Rx CTCSS": ch.rxCtcss if ch.rxCtcss != "None" else "88.5",
            "CTCSS / DCS Decode": ch.rxCtcss if ch.rxCtcss != "None" else "None",
            "CTCSS / DCS Encode": ch.ctcss if ch.ctcss != "None" else "None",
            "DCS": ch.dcs if ch.dcs != "None" else "023",
            "Rx DCS": ch.rxDcs if ch.rxDcs != "None" else "023",
            "DCS Polarity": ch.dcsPolarity,
            "Tx Power": tx_power,
            "Transmit Power": tx_power,
            "Bandwidth": ch.bandwidth,
            "Scan Add": "On",
            "Compander": "Off",
            "Scrambler": "Off",
            "Busy Lock": "Off",
            "FHSS": "Off",
            "Signal Code": "1",
            "PTTID": "Off",
            "Contact": ch.contact or "Local 9",
            "Contact Call Type": "Group Call",
            "Contact TG/DMR ID": ch.dmrId or "3100",
            "Radio ID": "1",
            "Color Code": ch.colorCode if ch.colorCode is not None else 1,
            "Slot": f"Slot {ch.timeSlot}" if ch.timeSlot else "Slot 1",
            "Rx Group List": "None",
            "Tx Permit": "Always",
            "Scan List": "None",
            "Squelch": "Normal",
            "TOT": "180",
            "Standby Color": "Blue",
            "Rx Color": "Orange",
            "Tx Color": "Red",
            "Comment": ch.comment or "",
        }
