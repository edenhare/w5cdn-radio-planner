"""Generic CSV Exporter."""

from __future__ import annotations

import csv
import io

from core.exporters.base import BaseExporter
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.sanitizers.sanitizer import DataSanitizer


class GenericExporter(BaseExporter):
    """Formats codeplug channels into human-readable generic CSV format."""

    def to_csv_string(self, codeplug: Codeplug, spec: TargetRadioSpec) -> str:
        prepared = self.prepare_channels(codeplug, spec)
        columns = spec.columns or [
            "Channel Number",
            "Name",
            "Receive Frequency",
            "Transmit Frequency",
            "Offset",
            "Offset Direction",
            "Mode",
            "Power",
            "Tone Mode",
            "CTCSS",
            "Rx CTCSS",
            "DCS",
            "Rx DCS",
            "DCS Polarity",
            "Bandwidth",
            "City",
            "State",
            "Latitude",
            "Longitude",
            "Comment",
        ]

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(columns)

        for ch in prepared.channels:
            row_dict = {
                "Channel Number": ch.number,
                "Name": DataSanitizer.csv_safe_cell(ch.name),
                "Receive Frequency": f"{ch.rxFreq:.5f}",
                "Transmit Frequency": f"{ch.txFreq:.5f}",
                "Offset": f"{ch.offset:.5f}",
                "Offset Direction": ch.offsetDir,
                "Mode": ch.mode,
                "Power": ch.power,
                "Tone Mode": ch.toneMode,
                "CTCSS": ch.ctcss,
                "Rx CTCSS": ch.rxCtcss,
                "DCS": ch.dcs,
                "Rx DCS": ch.rxDcs,
                "DCS Polarity": ch.dcsPolarity,
                "Bandwidth": ch.bandwidth,
                "City": DataSanitizer.csv_safe_cell(ch.city or ""),
                "State": DataSanitizer.csv_safe_cell(ch.state or ""),
                "Latitude": f"{ch.lat:.5f}" if ch.lat is not None else "",
                "Longitude": f"{ch.lon:.5f}" if ch.lon is not None else "",
                "Comment": DataSanitizer.csv_safe_cell(ch.comment or ""),
            }
            row = [row_dict.get(col, "") for col in columns]
            writer.writerow(row)

        return output.getvalue()
