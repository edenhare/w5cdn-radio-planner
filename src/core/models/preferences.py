"""User Preferences and Credentials Model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserPreferences(BaseModel):
    """User preferences, default radio IDs, and settings."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    callsign: str = Field(default="N0CALL", description="Amateur radio callsign")
    operatorName: str = Field(default="Radio Operator", description="Operator name")
    primaryDmrId: str | None = Field(
        default=None, description="Official 7-digit DMR Radio ID"
    )
    timeFormat: str = Field(
        default="TWELVE_HOUR", description="TWELVE_HOUR or TWENTY_FOUR_HOUR"
    )
    distanceUnit: str = Field(default="MILES", description="MILES or KILOMETERS")
    language: str = Field(
        default="ENGLISH", description="ENGLISH, SPANISH, FRENCH, GERMAN"
    )
    defaultRadioId: str = Field(
        default="chirp_standard", description="Default target radio spec ID"
    )


class ApiTokens(BaseModel):
    """Secure API tokens stored separately in ~/.config/radioplanner/tokens."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    repeaterBookApiKey: str | None = Field(
        default=None, description="RepeaterBook REST API Key"
    )
    radioIdUsername: str | None = Field(
        default=None, description="RadioID.net Callsign/Username"
    )
    radioIdApiKey: str | None = Field(
        default=None, description="RadioID.net API Key/Token"
    )
