"""Tests for RadioID provider and DMR Talkgroup expansion."""

from core.models.channel import RadioChannel
from core.providers.radio_id import RadioIdProvider


def test_radio_id_callsign_lookup():
    """Verify callsign lookup for operator identity (Spec 4)."""
    provider = RadioIdProvider()
    assert provider.lookup_callsign("W5CDN") == "3224901"
    assert provider.lookup_callsign("w5cdn") == "3224901"
    assert provider.lookup_callsign("UNKNOWN_CALL") is None


def test_dmr_talkgroup_duplication():
    """Verify duplicating a DMR repeater channel for individual talkgroups."""
    provider = RadioIdProvider()
    base_ch = RadioChannel(
        number=1,
        name="SHV DMR",
        callsign="K5SHV",
        rxFreq=444.10000,
        txFreq=449.10000,
        offset=5.0,
        offsetDir="+",
        mode="DMR",
        colorCode=1,
        timeSlot=1,
        comment="Shreveport DMR Repeater",
    )

    tgs = [
        {"name": "Local 9", "tg": "9", "ts": 1},
        {"name": "Texas Statewide", "tg": "3148", "ts": 2},
    ]

    duplicated = provider.duplicate_channel_for_talkgroups(base_ch, talkgroups=tgs)
    assert len(duplicated) == 2
    assert duplicated[0].name == "SHV DMR Local 9"
    assert duplicated[0].dmrId == "9"
    assert duplicated[0].timeSlot == 1

    assert duplicated[1].name == "SHV DMR Texas Statewide"
    assert duplicated[1].dmrId == "3148"
    assert duplicated[1].timeSlot == 2
