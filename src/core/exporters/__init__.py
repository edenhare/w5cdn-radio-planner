"""Hardware Exporter registry and dispatcher."""

from __future__ import annotations

from pathlib import Path

from core.exporters.base import BaseExporter
from core.exporters.chirp import ChirpExporter
from core.exporters.generic import GenericExporter
from core.exporters.rt_systems import RtSystemsExporter
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec


def get_exporter(programmer_type: str) -> BaseExporter:
    """Select appropriate exporter based on programmer type."""
    ptype = programmer_type.upper()
    if ptype == "CHIRP":
        return ChirpExporter()
    elif ptype == "RT_SYSTEMS":
        return RtSystemsExporter()
    else:
        return GenericExporter()


def export_codeplug(codeplug: Codeplug, spec: TargetRadioSpec, output_path: Path | str) -> Path:
    """Helper to export a codeplug using the target radio spec's default exporter."""
    exporter = get_exporter(spec.programmerType)
    return exporter.export_to_file(codeplug, spec, output_path)


__all__ = [
    "BaseExporter",
    "ChirpExporter",
    "GenericExporter",
    "RtSystemsExporter",
    "export_codeplug",
    "get_exporter",
]
