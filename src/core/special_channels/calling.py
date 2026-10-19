"""Built-in National Calling Frequencies Template."""

from __future__ import annotations

from core.models.channel import RadioChannel

CALLING_CHANNELS: list[RadioChannel] = [
    RadioChannel(
        number=1,
        name="10m CALL",
        callsign="CALL10M",
        rxFreq=29.60000,
        txFreq=29.60000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="High",
        specialType="CALLING",
        comment="10m FM National Simplex Calling Frequency",
    ),
    RadioChannel(
        number=2,
        name="6m CALL",
        callsign="CALL6M",
        rxFreq=52.52500,
        txFreq=52.52500,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="High",
        specialType="CALLING",
        comment="6m FM National Simplex Calling Frequency",
    ),
    RadioChannel(
        number=3,
        name="2m CALL",
        callsign="CALL2M",
        rxFreq=146.52000,
        txFreq=146.52000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="High",
        specialType="CALLING",
        comment="2m VHF National Simplex Calling Frequency",
    ),
    RadioChannel(
        number=4,
        name="1.25m CALL",
        callsign="CALL220",
        rxFreq=223.50000,
        txFreq=223.50000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="High",
        specialType="CALLING",
        comment="1.25m 220MHz National Simplex Calling Frequency",
    ),
    RadioChannel(
        number=5,
        name="70cm CALL",
        callsign="CALL440",
        rxFreq=446.00000,
        txFreq=446.00000,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="High",
        specialType="CALLING",
        comment="70cm UHF National Simplex Calling Frequency",
    ),
    RadioChannel(
        number=6,
        name="GMRS CALL",
        callsign="GMRS20",
        rxFreq=462.67500,
        txFreq=462.67500,
        offset=0.0,
        offsetDir="off",
        mode="FM",
        power="High",
        specialType="GMRS",
        comment="GMRS Channel 20 / Emergency & Traveler Calling",
    ),
]


def get_national_calling_channels() -> list[RadioChannel]:
    """Return a fresh list of National Calling channels."""
    return [ch.model_copy() for ch in CALLING_CHANNELS]
