"""User Preferences and Credentials Model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_COCKPIT_THEMES: tuple[str, ...] = (
    "shack-dark",
    "night-red",
    "amber-crt",
    "forest-eoc",
    "daylight",
    "paper-warm",
    "eoc-light",
    "sky-breeze",
    "high-contrast",
)

LEGACY_THEME_TO_COCKPIT: dict[str, str] = {
    "DARK": "shack-dark",
    "LIGHT": "daylight",
    "HIGH_CONTRAST": "high-contrast",
}

VALID_UI_FONTS: tuple[str, ...] = ("system", "humanist", "geometric", "serif", "mono")
VALID_MONO_FONTS: tuple[str, ...] = ("cascadia", "consolas", "courier")
VALID_DOCK_POSITIONS: tuple[str, ...] = ("left", "right", "top", "bottom")

DEFAULT_PANEL_LAYOUT: dict[str, dict[str, Any]] = {
    "builder": {"visible": True, "position": "left"},
    "map": {"visible": True, "position": "right"},
    "summary": {"visible": True, "position": "right"},
    "templates": {"visible": False, "position": "right"},
    "radios": {"visible": False, "position": "right"},
    "vfo": {"visible": True},
    "footer": {"visible": True},
}


def sanitize_panel_layout(raw: Any) -> dict[str, dict[str, Any]]:
    """Normalize a panel_layout mapping to valid dockable panel definitions."""
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for key, defaults in DEFAULT_PANEL_LAYOUT.items():
        item = src.get(key) if isinstance(src.get(key), dict) else {}
        visible = item.get("visible")
        entry: dict[str, Any] = {
            "visible": visible if isinstance(visible, bool) else defaults["visible"],
        }
        if "position" in defaults:
            pos = str(item.get("position") or defaults["position"]).strip().lower()
            entry["position"] = pos if pos in VALID_DOCK_POSITIONS else defaults["position"]
        out[key] = entry
    return out


class UserPreferences(BaseModel):
    """User preferences, default radio IDs, and cockpit appearance settings."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    callsign: str = Field(default="N0CALL", description="Amateur radio callsign")
    operatorName: str = Field(default="Radio Operator", description="Operator name")
    primaryDmrId: str | None = Field(default=None, description="Official 7-digit DMR Radio ID")
    distanceUnit: str = Field(default="MILES", description="MILES or KILOMETERS")
    language: str = Field(default="ENGLISH", description="ENGLISH, SPANISH, FRENCH, GERMAN")
    defaultRadioId: str | None = Field(default=None, description="Default target radio spec ID (or None)")
    colorTheme: str = Field(
        default="shack-dark",
        description="UI color theme (9 cockpit themes or legacy DARK/LIGHT/HIGH_CONTRAST)",
    )
    fontFamily: str = Field(
        default="system",
        description="UI font family: system, humanist, geometric, serif, mono (or legacy SANS/MONO/SERIF/SYSTEM)",
    )
    monoFont: str = Field(
        default="cascadia",
        description="Monospace font for callsigns, frequencies, and LCD names: cascadia, consolas, courier",
    )
    fontSize: str = Field(
        default="MEDIUM",
        description="Legacy UI font size label: SMALL, MEDIUM, LARGE, XLARGE",
    )
    uiFontSize: int = Field(
        default=14,
        ge=11,
        le=22,
        description="Base cockpit UI font size in pixels (11-22)",
    )
    lcdFontSize: int = Field(
        default=15,
        ge=12,
        le=26,
        description="Channel LCD name & callsign font size in pixels (12-26)",
    )
    panelLayout: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: sanitize_panel_layout(DEFAULT_PANEL_LAYOUT),
        description="5-zone dockable panel visibility and positions",
    )
    channelNamingFormat: str = Field(
        default="CITY_FREQ",
        description="Channel naming format: CITY_FREQ (e.g. 'Tyler 7.20'), CALLSIGN_FREQ, CALLSIGN, CITY, STANDARD",
    )
    repeaterAccess: list[str] = Field(
        default_factory=lambda: ["OPEN"],
        description="Repeater access types to include: OPEN, CLOSED, PRIVATE",
    )
    repeaterMaxAgeDays: int = Field(
        default=30,
        ge=1,
        description="Maximum age in days for downloaded RepeaterBook state files before refreshing",
    )
    webPort: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Default TCP port for the FastAPI Web Studio interface",
    )

    @property
    def resolved_cockpit_theme(self) -> str:
        """Return canonical lowercase cockpit theme slug (mapping legacy DARK/LIGHT/HIGH_CONTRAST)."""
        upper = self.colorTheme.upper()
        if upper in LEGACY_THEME_TO_COCKPIT:
            return LEGACY_THEME_TO_COCKPIT[upper]
        low = self.colorTheme.lower()
        return low if low in VALID_COCKPIT_THEMES else "shack-dark"

    @property
    def resolved_ui_font(self) -> str:
        """Return canonical cockpit UI font key."""
        low = self.fontFamily.lower()
        legacy = {"sans": "system", "system": "system", "mono": "mono", "serif": "serif"}
        if low in VALID_UI_FONTS:
            return low
        return legacy.get(low, "system")

    @field_validator("callsign", mode="before")
    @classmethod
    def enforce_uppercase_callsign(cls, v: str) -> str:
        """Ensure amateur callsign is always stored in uppercase."""
        if isinstance(v, str):
            cleaned = v.strip().upper()
            return cleaned if cleaned else "N0CALL"
        return v

    @field_validator("distanceUnit", mode="before")
    @classmethod
    def normalize_distance_unit(cls, v: str) -> str:
        """Allow 'm' for miles, 'k' for kilometers, or standard full names."""
        if isinstance(v, str):
            val = v.strip().lower()
            if val in {"m", "miles", "mile"}:
                return "MILES"
            if val in {"k", "km", "kilometers", "kilometer"}:
                return "KILOMETERS"
        return "MILES"

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, v: str | int) -> str:
        """Allow number selection 1-4 or uppercase language names."""
        mapping = {
            "1": "ENGLISH",
            "2": "SPANISH",
            "3": "FRENCH",
            "4": "GERMAN",
            1: "ENGLISH",
            2: "SPANISH",
            3: "FRENCH",
            4: "GERMAN",
        }
        if str(v).strip() in mapping:
            return mapping[str(v).strip()]
        val_upper = str(v).strip().upper()
        if val_upper in {"ENGLISH", "SPANISH", "FRENCH", "GERMAN"}:
            return val_upper
        return "ENGLISH"

    @field_validator("colorTheme", mode="before")
    @classmethod
    def normalize_color_theme(cls, v: str | int) -> str:
        """Support legacy CLI themes (DARK/LIGHT/HIGH_CONTRAST) and all 9 cockpit themes."""
        mapping = {
            "1": "DARK",
            "2": "LIGHT",
            "3": "HIGH_CONTRAST",
            1: "DARK",
            2: "LIGHT",
            3: "HIGH_CONTRAST",
        }
        raw_str = str(v).strip()
        if raw_str in mapping:
            return mapping[raw_str]
        val_low = raw_str.lower()
        if val_low in VALID_COCKPIT_THEMES:
            return val_low
        val_upper = raw_str.upper()
        if val_upper in {"DARK", "LIGHT", "HIGH_CONTRAST"}:
            return val_upper
        return "shack-dark"

    @field_validator("fontFamily", mode="before")
    @classmethod
    def normalize_font_family(cls, v: str) -> str:
        """Normalize fontFamily to cockpit font keys or legacy uppercase names."""
        raw = str(v).strip()
        low = raw.lower()
        if low in VALID_UI_FONTS:
            return low
        upper = raw.upper()
        if upper in {"SANS", "MONO", "SERIF", "SYSTEM"}:
            return upper
        return "system"

    @field_validator("monoFont", mode="before")
    @classmethod
    def normalize_mono_font(cls, v: str) -> str:
        """Normalize monospace font key."""
        low = str(v).strip().lower()
        return low if low in VALID_MONO_FONTS else "cascadia"

    @field_validator("fontSize", mode="before")
    @classmethod
    def normalize_font_size(cls, v: str) -> str:
        """Normalize legacy fontSize to SMALL, MEDIUM, LARGE, or XLARGE."""
        val_upper = str(v).strip().upper()
        if val_upper in {"SMALL", "MEDIUM", "LARGE", "XLARGE"}:
            return val_upper
        return "MEDIUM"

    @field_validator("uiFontSize", mode="before")
    @classmethod
    def normalize_ui_font_size(cls, v: int | str) -> int:
        """Clamp UI base font size to 11..22px."""
        legacy = {"SMALL": 12, "MEDIUM": 14, "LARGE": 17, "XLARGE": 20}
        if isinstance(v, str) and v.strip().upper() in legacy:
            return legacy[v.strip().upper()]
        try:
            return max(11, min(22, int(v)))
        except (TypeError, ValueError):
            return 14

    @field_validator("lcdFontSize", mode="before")
    @classmethod
    def normalize_lcd_font_size(cls, v: int | str) -> int:
        """Clamp LCD/callsign font size to 12..26px."""
        try:
            return max(12, min(26, int(v)))
        except (TypeError, ValueError):
            return 15

    @field_validator("panelLayout", mode="before")
    @classmethod
    def normalize_panel_layout(cls, v: Any) -> dict[str, dict[str, Any]]:
        """Ensure panelLayout always has valid dockable keys and positions."""
        return sanitize_panel_layout(v)

    @field_validator("channelNamingFormat", mode="before")
    @classmethod
    def normalize_channel_naming_format(cls, v: str | int) -> str:
        """Allow number selection 1-5 or uppercase format names."""
        mapping = {
            "1": "CITY_FREQ",
            "2": "CALLSIGN_FREQ",
            "3": "CALLSIGN",
            "4": "CITY",
            "5": "STANDARD",
            1: "CITY_FREQ",
            2: "CALLSIGN_FREQ",
            3: "CALLSIGN",
            4: "CITY",
            5: "STANDARD",
        }
        if str(v).strip() in mapping:
            return mapping[str(v).strip()]
        val_upper = str(v).strip().upper()
        if val_upper in {"CITY_FREQ", "CALLSIGN_FREQ", "CALLSIGN", "CITY", "STANDARD"}:
            return val_upper
        return "CITY_FREQ"

    @field_validator("repeaterAccess", mode="before")
    @classmethod
    def normalize_repeater_access(cls, v: str | list[str]) -> list[str]:
        """Normalize repeater access list to valid uppercase values (OPEN, CLOSED, PRIVATE)."""
        valid = {"OPEN", "CLOSED", "PRIVATE"}
        if isinstance(v, str):
            val_upper = v.strip().upper()
            if val_upper == "ALL":
                return ["OPEN", "CLOSED", "PRIVATE"]
            items = [x.strip().upper() for x in v.split(",") if x.strip()]
        elif isinstance(v, (list, tuple, set)):
            items = [str(x).strip().upper() for x in v if str(x).strip()]
        else:
            return ["OPEN"]
        filtered = {x for x in items if x in valid}
        ordered = [k for k in ["OPEN", "CLOSED", "PRIVATE"] if k in filtered]
        return ordered if ordered else ["OPEN"]

    def update_settings(self, **kwargs: Any) -> UserPreferences:
        """Return a newly validated UserPreferences instance with updated fields."""
        data = self.model_dump()
        data.update(kwargs)
        return self.model_validate(data)


class ApiTokens(BaseModel):
    """Secure API tokens stored separately in ~/.config/radioplanner/tokens."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    repeaterBookApiKey: str | None = Field(default=None, description="RepeaterBook REST API Key")
    radioIdUsername: str | None = Field(default=None, description="RadioID.net Callsign/Username")
    radioIdApiKey: str | None = Field(default=None, description="RadioID.net API Key/Token")
    qrzUsername: str | None = Field(default=None, description="QRZ.com XML API Username/Callsign")
    qrzPassword: str | None = Field(default=None, description="QRZ.com XML API Password")
