"""Built-in NOAA Weather Radio Channels Template."""

from __future__ import annotations

from core.models.channel import RadioChannel

NOAA_WX_CHANNELS: list[RadioChannel] = [
    RadioChannel(
        number=1,
        name="NOAA WX 1",
        callsign="WX1",
        rxFreq=162.55000,
        txFreq=162.55000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="Low",
        specialType="WX",
        comment="NOAA Weather Radio 162.550 MHz",
    ),
    RadioChannel(
        number=2,
        name="NOAA WX 2",
        callsign="WX2",
        rxFreq=162.40000,
        txFreq=162.40000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="Low",
        specialType="WX",
        comment="NOAA Weather Radio 162.400 MHz",
    ),
    RadioChannel(
        number=3,
        name="NOAA WX 3",
        callsign="WX3",
        rxFreq=162.47500,
        txFreq=162.47500,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="Low",
        specialType="WX",
        comment="NOAA Weather Radio 162.475 MHz",
    ),
    RadioChannel(
        number=4,
        name="NOAA WX 4",
        callsign="WX4",
        rxFreq=162.42500,
        txFreq=162.42500,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="Low",
        specialType="WX",
        comment="NOAA Weather Radio 162.425 MHz",
    ),
    RadioChannel(
        number=5,
        name="NOAA WX 5",
        callsign="WX5",
        rxFreq=162.45000,
        txFreq=162.45000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="Low",
        specialType="WX",
        comment="NOAA Weather Radio 162.450 MHz",
    ),
    RadioChannel(
        number=6,
        name="NOAA WX 6",
        callsign="WX6",
        rxFreq=162.50000,
        txFreq=162.50000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="Low",
        specialType="WX",
        comment="NOAA Weather Radio 162.500 MHz",
    ),
    RadioChannel(
        number=7,
        name="NOAA WX 7",
        callsign="WX7",
        rxFreq=162.52500,
        txFreq=162.52500,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="Low",
        specialType="WX",
        comment="NOAA Weather Radio 162.525 MHz",
    ),
]


def get_noaa_wx_channels() -> list[RadioChannel]:
    """Return a fresh list of standard 7 NOAA Weather channels."""
    return [ch.model_copy() for ch in NOAA_WX_CHANNELS]
