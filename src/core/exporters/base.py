"""Base Exporter interface for hardware-constrained codeplug generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.sanitizers.condenser import NameCondenser


class BaseExporter(ABC):
    """Abstract base exporter for radio codeplugs."""

    @abstractmethod
    def to_csv_string(self, codeplug: Codeplug, spec: TargetRadioSpec) -> str:
        """Render codeplug channels into hardware-compliant CSV text."""

    def export_to_file(self, codeplug: Codeplug, spec: TargetRadioSpec, output_path: Path | str) -> Path:
        """Write formatted CSV text to disk, creating parent directories if needed."""
        dest = Path(output_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = self.to_csv_string(codeplug, spec)
        dest.write_text(content, encoding="utf-8")
        return dest

    @staticmethod
    def prepare_channels(codeplug: Codeplug, spec: TargetRadioSpec) -> Codeplug:
        """Prepare channels by applying LCD name condensation and clamping to maxChannels."""
        channels = codeplug.channels[: spec.maxChannels]
        prepared = [ch.with_name(NameCondenser.condense(ch.name, spec)) for ch in channels]
        start_slot = getattr(spec, "startChannel", 1)
        return Codeplug(name=codeplug.name, channels=prepared).renumbered(start_slot=start_slot)
