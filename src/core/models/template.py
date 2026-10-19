"""Preset Template Models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PresetTemplateFile(BaseModel):
    """Preset or user-uploaded codeplug channel template definition."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(
        ..., description="Unique template identifier (e.g. builtin_calling_channels)"
    )
    name: str = Field(..., description="Template title")
    description: str = Field(default="", description="Description of template purpose")
    tagText: str = Field(
        default="PRESET",
        description="Badge chip label text (e.g. CALLING, WX, SKYWARN)",
    )
    tagColorHex: str = Field(default="#00BCD4", description="Hex color for tag badge")
    fileName: str = Field(default="template.csv", description="Original filename")
    rawCsvContent: str = Field(default="", description="CSV channel rows text")
