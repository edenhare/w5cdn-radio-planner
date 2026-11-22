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
    "Tone",
    "rToneFreq",
    "cToneFreq",
    "DtcsCode",
    "DtcsPolarity",
    "RxDtcsCode",
    "CrossMode",
    "Mode",
    "TStep",
    "Skip",
    "Power",
    "Comment",
    "URCALL",
    "RPT1CALL",
    "RPT2CALL",
    "DVCODE",
]


class ChirpExporter(BaseExporter):
    """Formats codeplug channels into CHIRP standard CSV format (chirp_common.Memory.CSV_FORMAT)."""

    def to_csv_string(self, codeplug: Codeplug, spec: TargetRadioSpec) -> str:
        prepared = self.prepare_channels(codeplug, spec)
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CHIRP_COLUMNS)

        for ch in prepared.channels:
            # Map Duplex ("", "+", "-", "split", "off")
            duplex = ch.offsetDir if ch.offsetDir in {"+", "-"} else ""
            if abs(ch.offset) < 1e-5:
                duplex = ""

            # Map Tone Mode ("", "Tone", "TSQL", "DTCS", "Cross")
            tone = ""
            r_tone = "88.5"
            c_tone = "88.5"
            dtcs_code = "023"
            rx_dtcs_code = "023"

            raw_ctcss = (ch.ctcss or "").strip()
            valid_ctcss: str | None = None
            if raw_ctcss and raw_ctcss != "None":
                try:
                    f_val = float(raw_ctcss)
                    if 50.0 < f_val < 300.0:
                        valid_ctcss = f"{f_val:.1f}"
                except (ValueError, TypeError):
                    pass

            tone_mode_upper = ch.toneMode.upper()
            if raw_ctcss.upper().startswith("D") and raw_ctcss[1:4].isdigit():
                # Handle DCS codes stored in ctcss field (e.g. "D205")
                tone = "DTCS"
                dtcs_code = f"{int(raw_ctcss[1:4]):03d}"
                rx_dtcs_code = dtcs_code
            elif tone_mode_upper == "TONE":
                if valid_ctcss:
                    tone = "Tone"
                    r_tone = valid_ctcss
            elif tone_mode_upper in {"TSQL", "CTCSS"}:
                if valid_ctcss:
                    tone = "TSQL"
                    c_tone = valid_ctcss
                    r_tone = valid_ctcss
            elif tone_mode_upper in {"DCS", "DTCS"}:
                tone = "DTCS"
                dtcs_code = f"{int(ch.dcs):03d}" if ch.dcs and ch.dcs != "None" and ch.dcs.isdigit() else "023"
                rx_dtcs_code = (
                    f"{int(ch.rxDcs):03d}" if ch.rxDcs and ch.rxDcs != "None" and ch.rxDcs.isdigit() else dtcs_code
                )

            # Power mapping: CHIRP generic_csv.py parse_power requires Watt format (e.g., "50W", "25W", "5.0W")
            pwr_raw = (ch.power or "High").strip().lower()
            if pwr_raw == "low":
                power = "5.0W"
            elif pwr_raw in {"mid", "medium", "med"}:
                power = "25W"
            elif pwr_raw == "high":
                power = "50W"
            elif pwr_raw.endswith("w") or pwr_raw.replace(".", "", 1).isdigit():
                power = ch.power.strip()
            else:
                power = "50W"

            mode = "AM" if ch.mode.upper() == "AM" else "FM"

            row = [
                ch.number,
                ch.name,
                f"{ch.rxFreq:.6f}",
                duplex,
                f"{ch.offset:.6f}",
                tone,
                r_tone,
                c_tone,
                dtcs_code,
                ch.dcsPolarity or "NN",
                rx_dtcs_code,
                "Tone->Tone",  # CrossMode (must be in chirp_common.CROSS_MODES)
                mode,
                "5.00",  # TStep (float in kHz)
                "",  # Skip ("" or "S" or "P")
                power,
                ch.comment,
                "",  # URCALL
                "",  # RPT1CALL
                "",  # RPT2CALL
                "",  # DVCODE
            ]
            writer.writerow(row)

        return output.getvalue()
