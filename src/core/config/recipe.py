"""Replayable Workflow Recipe Schema and Validation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.config.yaml_loader import YamlDiagnosticError, load_yaml_file, parse_yaml_text


class CorridorConfig(BaseModel):
    """Configuration specific to Highway Route Corridor mode."""

    waypoints: list[str] = Field(default_factory=list, min_length=2)
    corridor_width_miles: float = Field(default=25.0, gt=0.0)


class ProximityConfig(BaseModel):
    """Configuration specific to Radial Proximity Search mode."""

    center_location: str = Field(..., min_length=1)
    radius_miles: float = Field(default=50.0, gt=0.0)


class AviationConfig(BaseModel):
    """Configuration specific to Local Aviation Planner mode."""

    center_location: str = Field(..., min_length=1)
    radius_miles: float = Field(default=35.0, gt=0.0)


class RadioTargetConfig(BaseModel):
    """Target radio selection and filtering configuration."""

    radio_id: str | None = Field(default=None)
    programmer_format: str | None = Field(default=None)
    include_simplex: bool = Field(default=True)
    bands: list[str] = Field(default_factory=lambda: ["2m", "70cm", "WX"])
    modes: list[str] = Field(default_factory=lambda: ["FM", "AM"])
    repeater_access: list[str] = Field(default_factory=lambda: ["OPEN"])
    naming_format: str = Field(default="CITY_FREQ")


class ExportConfig(BaseModel):
    """CSV output destination and naming configuration."""

    output_dir: str = Field(default="./exports")
    filename_pattern: str | None = Field(default=None)


class RadioPlannerRecipe(BaseModel):
    """Complete, self-contained replayable configuration recipe."""

    model_config = ConfigDict(extra="ignore")

    version: str = Field(default="1.0")
    mode: Literal["ROUTE_CORRIDOR", "PROXIMITY_SEARCH", "AVIATION_PLANNER", "PRESET_TEMPLATES"]
    name: str = Field(default="RadioPlanner-Run")
    description: str = Field(default="")
    corridor: CorridorConfig | None = None
    proximity: ProximityConfig | None = None
    aviation: AviationConfig | None = None
    radio_target: RadioTargetConfig = Field(default_factory=RadioTargetConfig)
    sequence_order: list[str] = Field(
        default_factory=lambda: [
            "TEMPLATE:builtin_calling_channels",
            "ROUTE_PLAN",
            "TEMPLATE:builtin_noaa_wx_channels",
        ]
    )
    export: ExportConfig = Field(default_factory=ExportConfig)

    def validate_for_execution(self) -> list[str]:
        """Validate logical consistency before execution and return list of validation errors."""
        errors: list[str] = []
        if self.mode == "ROUTE_CORRIDOR":
            if not self.corridor or len(self.corridor.waypoints) < 2:
                errors.append("ROUTE_CORRIDOR requires 'corridor' section with at least 2 waypoints.")
        elif self.mode == "PROXIMITY_SEARCH":
            if not self.proximity or not self.proximity.center_location:
                errors.append("PROXIMITY_SEARCH requires 'proximity' section with 'center_location'.")
        elif self.mode == "AVIATION_PLANNER":
            if not self.aviation or not self.aviation.center_location:
                errors.append("AVIATION_PLANNER requires 'aviation' section with 'center_location'.")
        return errors

    @classmethod
    def from_yaml_file(cls, path: Path | str) -> RadioPlannerRecipe:
        """Load and validate recipe from a YAML file with line-level diagnostics."""
        data = load_yaml_file(path)
        try:
            return cls.model_validate(data)
        except ValidationError as err:
            # Map Pydantic validation errors into clean diagnostics
            field_errors = []
            for item in err.errors():
                loc = " -> ".join(str(x) for x in item["loc"])
                msg = item["msg"]
                field_errors.append(f"- Field '{loc}': {msg}")
            raise YamlDiagnosticError(
                message="Schema validation error in configuration recipe:\n" + "\n".join(field_errors),
                file_path=Path(path),
                suggestion="Verify that the configuration fields match the required schema for this mode.",
            ) from err

    @classmethod
    def from_yaml_text(cls, text: str, source_name: str | None = None) -> RadioPlannerRecipe:
        """Load and validate recipe from YAML string."""
        data = parse_yaml_text(text)
        try:
            return cls.model_validate(data)
        except ValidationError as err:
            field_errors = [f"- Field '{' -> '.join(str(x) for x in e['loc'])}': {e['msg']}" for e in err.errors()]
            raise YamlDiagnosticError(
                message="Schema validation error:\n" + "\n".join(field_errors),
                suggestion="Verify configuration keys against the schema.",
            ) from err

    def to_yaml_file(self, path: Path | str) -> Path:
        """Serialize recipe to YAML file without binding to a specific target radio."""
        dest = Path(path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dump_data = self.model_dump(exclude_none=True)
        if "radio_target" in dump_data and isinstance(dump_data["radio_target"], dict):
            dump_data["radio_target"].pop("radio_id", None)
            dump_data["radio_target"].pop("programmer_format", None)
        with open(dest, "w", encoding="utf-8") as f:
            yaml.dump(dump_data, f, sort_keys=False, default_flow_style=False)
        return dest
