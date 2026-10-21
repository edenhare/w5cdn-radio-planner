"""User Preferences and Credentials Model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserPreferences(BaseModel):
    """User preferences, default radio IDs, and settings."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    callsign: str = Field(default="N0CALL", description="Amateur radio callsign")
    operatorName: str = Field(default="Radio Operator", description="Operator name")
    primaryDmrId: str | None = Field(default=None, description="Official 7-digit DMR Radio ID")
    distanceUnit: str = Field(default="MILES", description="MILES or KILOMETERS")
    language: str = Field(default="ENGLISH", description="ENGLISH, SPANISH, FRENCH, GERMAN")
    defaultRadioId: str | None = Field(default=None, description="Default target radio spec ID (or None)")
    colorTheme: str = Field(default="DARK", description="UI color theme: DARK, LIGHT, HIGH_CONTRAST")
    channelNamingFormat: str = Field(
        default="CITY_FREQ",
        description="Channel naming format: CITY_FREQ (e.g. 'Tyler 7.20'), CALLSIGN_FREQ, CALLSIGN, STANDARD",
    )

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
            elif val in {"k", "km", "kilometers", "kilometer"}:
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
        """Allow number selection 1-3 or uppercase theme names."""
        mapping = {
            "1": "DARK",
            "2": "LIGHT",
            "3": "HIGH_CONTRAST",
            1: "DARK",
            2: "LIGHT",
            3: "HIGH_CONTRAST",
        }
        if str(v).strip() in mapping:
            return mapping[str(v).strip()]
        val_upper = str(v).strip().upper()
        if val_upper in {"DARK", "LIGHT", "HIGH_CONTRAST"}:
            return val_upper
        return "DARK"

    @field_validator("channelNamingFormat", mode="before")
    @classmethod
    def normalize_channel_naming_format(cls, v: str | int) -> str:
        """Allow number selection 1-4 or uppercase format names."""
        mapping = {
            "1": "CITY_FREQ",
            "2": "CALLSIGN_FREQ",
            "3": "CALLSIGN",
            "4": "STANDARD",
            1: "CITY_FREQ",
            2: "CALLSIGN_FREQ",
            3: "CALLSIGN",
            4: "STANDARD",
        }
        if str(v).strip() in mapping:
            return mapping[str(v).strip()]
        val_upper = str(v).strip().upper()
        if val_upper in {"CITY_FREQ", "CALLSIGN_FREQ", "CALLSIGN", "STANDARD"}:
            return val_upper
        return "CITY_FREQ"


    def update_settings(self, **kwargs) -> UserPreferences:
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
