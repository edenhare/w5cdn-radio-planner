"""CHIRP Standard CSV Exporter (21 Columns)."""

from __future__ import annotations

import csv
import io

from core.exporters.base import BaseExporter
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec

CHIRP_COLUMNS = [
    "Location",
    "Name",
    "Frequency",
    "Duplex",
    "Offset",
    "Mode",
    "Tone",
    "rToneFreq",
    "cToneFreq",
    "DtcsCode",
    "DtcsPolarity",
    "RxDtcsCode",
    "CrossMode",
    "Mode2",
    "Power",
    "Skip",
    "Comment",
    "URCALL",
    "RPT1CALL",
    "RPT2CALL",
    "Digital Code",
]


class ChirpExporter(BaseExporter):
    """Formats codeplug channels into CHIRP standard CSV format."""

    def to_csv_string(self, codeplug: Codeplug, spec: TargetRadioSpec) -> str:
        prepared = self.prepare_channels(codeplug, spec)
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CHIRP_COLUMNS)

        for ch in prepared.channels:
            # Map Duplex
            duplex = ch.offsetDir if ch.offsetDir in {"+", "-"} else ""
            if duplex == "off":
                duplex = "off"
            elif abs(ch.offset) < 1e-5:
                duplex = ""

            # Map Tone Mode
            tone = ""
            r_tone = "88.5"
            c_tone = "88.5"
            dtcs_code = "023"
            rx_dtcs_code = "023"

            tone_mode_upper = ch.toneMode.upper()
            if tone_mode_upper == "TONE":
                tone = "Tone"
                r_tone = ch.ctcss if ch.ctcss != "None" else "88.5"
            elif tone_mode_upper in {"TSQL", "CTCSS"}:
                tone = "TSQL"
                c_tone = ch.ctcss if ch.ctcss != "None" else "88.5"
                r_tone = c_tone
            elif tone_mode_upper == "DCS":
                tone = "DTCS"
                dtcs_code = ch.dcs if ch.dcs != "None" else "023"
                rx_dtcs_code = ch.rxDcs if ch.rxDcs != "None" else dtcs_code

            # Power mapping
            power = ch.power.capitalize() if ch.power else "High"
            mode = "AM" if ch.mode.upper() == "AM" else "FM"

            row = [
                ch.number,
                ch.name,
                f"{ch.rxFreq:.5f}",
                duplex,
                f"{ch.offset:.5f}",
                mode,
                tone,
                r_tone,
                c_tone,
                dtcs_code,
                ch.dcsPolarity,
                rx_dtcs_code,
                "None",  # CrossMode
                "",  # Mode2
                power,
                "",  # Skip
                ch.comment,
                "",  # URCALL
                ch.callsign or "",  # RPT1CALL
                "",  # RPT2CALL
                ch.colorCode if ch.colorCode is not None else "0",
            ]
            writer.writerow(row)

        return output.getvalue()
