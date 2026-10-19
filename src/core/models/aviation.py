"""Aviation Airfield and Frequency Models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AviationFrequency(BaseModel):
    """An aeronautical radio frequency."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    type: str = Field(..., description="Frequency type: CTAF, TWR, GND, ATIS, AWOS, APP, DEP")
    description: str = Field(default="", description="Description (e.g. Tower, Common Traffic)")
    frequencyMhz: float = Field(..., description="Frequency in MHz (e.g. 120.100)")


class AirfieldRecord(BaseModel):
    """OurAirports airfield record."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    ident: str = Field(..., description="ICAO or FAA identifier (e.g. KTYR, KDAL)")
    name: str = Field(..., description="Official airport title")
    latitude: float = Field(..., description="Airfield latitude")
    longitude: float = Field(..., description="Airfield longitude")
    municipality: str = Field(default="", description="Associated city or municipality")
    frequencies: list[AviationFrequency] = Field(default_factory=list, description="Frequencies at this field")
