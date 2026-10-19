"""Special channel templates and hardware filtering."""

from __future__ import annotations

from core.models.channel import RadioChannel
from core.models.radio_spec import TargetRadioSpec
from core.special_channels.calling import get_national_calling_channels
from core.special_channels.weather import get_noaa_wx_channels


def filter_channels_for_radio(
    channels: list[RadioChannel], spec: TargetRadioSpec
) -> list[RadioChannel]:
    """Filter channel list against target radio supported bands and modes."""
    filtered: list[RadioChannel] = []
    supported_bands_lower = {b.lower() for b in spec.supportedBands}
    supported_modes_lower = {m.lower() for m in spec.supportedModes}

    for ch in channels:
        ch_band_lower = ch.band.lower()
        ch_mode_lower = ch.mode.lower()

        # Check band
        if ch_band_lower not in supported_bands_lower:
            continue

        # Check mode (allow 'ANALOG' to match 'FM', 'AM')
        mode_match = (
            ch_mode_lower in supported_modes_lower
            or (
                "analog" in supported_modes_lower
                and ch_mode_lower in {"fm", "am", "nfm", "wfm"}
            )
            or ("fm" in supported_modes_lower and ch_mode_lower == "analog")
        )
        if not mode_match:
            continue

        filtered.append(ch)

    return filtered


__all__ = [
    "filter_channels_for_radio",
    "get_national_calling_channels",
    "get_noaa_wx_channels",
]
