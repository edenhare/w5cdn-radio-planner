"""Target Radio Hardware Specification Model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TargetRadioSpec(BaseModel):
    """Hardware constraints and CSV exporter rules for a target radio model."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(..., description="Unique slug identifier (e.g. baofeng_5rm)")
    brand: str = Field(
        ..., description="Manufacturer brand name (e.g. Baofeng, BTECH, Wouxun)"
    )
    model: str = Field(..., description="Radio model name (e.g. 5RM, DMR-6X2)")
    description: str = Field(..., description="Human-readable description")
    maxChannels: int = Field(
        default=128, description="Maximum channel memory slots capacity"
    )
    maxNameLength: int = Field(default=10, description="LCD display character limit")
    allowDots: bool = Field(
        default=True, description="Whether LCD supports dot '.' characters"
    )
    allowSpaces: bool = Field(default=True, description="Whether LCD supports spaces")
    allowedSpecialChars: str = Field(
        default=" -_./#", description="Allowed special symbols on LCD"
    )
    programmerType: str = Field(
        default="CHIRP",
        description="Default programmer: CHIRP, RT_SYSTEMS, VENDOR_CPS, GENERIC_CSV",
    )
    supportedBands: list[str] = Field(
        default_factory=lambda: ["2m", "70cm"],
        description="Supported bands: 10m, 6m, 2m, 1.25m, 70cm, GMRS, Airband, WX",
    )
    supportedModes: list[str] = Field(
        default_factory=lambda: ["FM", "AM"],
        description="Supported modes: FM, AM, DMR, ANALOG, DIGITAL",
    )
    columns: list[str] = Field(
        default_factory=list, description="Ordered CSV column headers"
    )
