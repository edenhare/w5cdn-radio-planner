"""Common Internal Representation (CIR) for Codeplug."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.models.channel import RadioChannel


class Codeplug(BaseModel):
    """Synthesized hardware codeplug containing an ordered channel list."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str = Field(..., description="Title string for this codeplug")
    channels: list[RadioChannel] = Field(
        default_factory=list, description="Ordered list of channels"
    )

    @property
    def total_channels(self) -> int:
        """Total number of channels."""
        return len(self.channels)

    def renumbered(self, start_slot: int = 1) -> Codeplug:
        """Return a copy of the codeplug with continuous 1-indexed slot numbers."""
        renumbered_channels = [
            ch.with_slot_number(idx)
            for idx, ch in enumerate(self.channels, start=start_slot)
        ]
        return self.model_copy(update={"channels": renumbered_channels})
