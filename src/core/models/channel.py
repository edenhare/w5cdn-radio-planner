"""Common Internal Representation (CIR) for Radio Channel."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RadioChannel(BaseModel):
    """Normalized Common Internal Representation of a radio channel."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    number: int = Field(default=1, description="1-indexed channel memory slot")
    name: str = Field(..., description="Alphanumeric memory display name tag")
    callsign: str | None = Field(
        default=None, description="Repeater or station callsign (e.g. W5ETX, KTYR)"
    )
    rxFreq: float = Field(..., description="Receive frequency in MHz")
    txFreq: float = Field(..., description="Transmit frequency in MHz")
    offset: float = Field(default=0.0, description="Frequency shift magnitude in MHz")
    offsetDir: str = Field(
        default="off", description="Offset direction: '+', '-', or 'off'"
    )
    mode: str = Field(
        default="FM", description="Operating mode: FM, AM, DMR, ANALOG, etc."
    )
    power: str = Field(default="High", description="Power level: High, Mid, Low")
    toneMode: str = Field(
        default="None", description="Tone mode: None, Tone, TSQL, DCS"
    )
    ctcss: str = Field(
        default="None", description="Transmit CTCSS tone in Hz (e.g. '88.5') or 'None'"
    )
    rxCtcss: str = Field(
        default="None", description="Receive CTCSS tone in Hz or 'None'"
    )
    dcs: str = Field(default="None", description="DCS code (e.g. '023') or 'None'")
    rxDcs: str = Field(default="None", description="Receive DCS code or 'None'")
    dcsPolarity: str = Field(default="NN", description="DCS polarity: NN, NR, RN, RR")
    bandwidth: str = Field(
        default="25KHz", description="Channel bandwidth: 25KHz or 12.5KHz"
    )
    city: str | None = Field(default=None, description="City or municipality")
    state: str | None = Field(default=None, description="State abbreviation (e.g. TX)")
    lat: float | None = Field(default=None, description="Latitude coordinate")
    lon: float | None = Field(default=None, description="Longitude coordinate")
    specialType: str = Field(
        default="REPEATERS",
        description="Classification: CALLING, WX, AVIATION, GMRS, CUSTOM, REPEATERS",
    )
    colorCode: int | None = Field(
        default=None, ge=0, le=15, description="DMR Color Code 0-15"
    )
    timeSlot: int | None = Field(
        default=None, ge=1, le=2, description="DMR TimeSlot 1 or 2"
    )
    dmrId: str | None = Field(default=None, description="7-digit DMR Radio ID")
    contact: str | None = Field(default=None, description="DMR Talkgroup Contact label")
    comment: str = Field(default="", description="Explanatory comment string")

    @property
    def is_simplex(self) -> bool:
        """Return True if rxFreq == txFreq or offset is 0."""
        return abs(self.rxFreq - self.txFreq) < 1e-5 or self.offsetDir == "off"

    @property
    def band(self) -> str:
        """Categorize channel into standard frequency band name."""
        freq = self.rxFreq
        if 161.0 <= freq <= 163.0:
            return "WX"
        if 108.0 <= freq <= 137.0:
            return "Airband"
        if 28.0 <= freq <= 29.7:
            return "10m"
        if 50.0 <= freq <= 54.0:
            return "6m"
        if 144.0 <= freq <= 148.0:
            return "2m"
        if 222.0 <= freq <= 225.0:
            return "1.25m"
        if 420.0 <= freq <= 450.0:
            return "70cm"
        if 462.0 <= freq <= 468.0:
            return "GMRS"
        return "Other"

    def with_slot_number(self, new_number: int) -> RadioChannel:
        """Return a copy of the channel with updated slot number."""
        return self.model_copy(update={"number": new_number})

    def with_name(self, new_name: str) -> RadioChannel:
        """Return a copy of the channel with updated name."""
        return self.model_copy(update={"name": new_name})
