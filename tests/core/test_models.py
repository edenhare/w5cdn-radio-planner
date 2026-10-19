"""Tri-state unit tests for CIR models (RadioChannel, Codeplug, TargetRadioSpec)."""

import pytest
from pydantic import ValidationError

from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug


def test_radio_channel_good_data():
    """Good Data: Valid repeater channel creation, frequency band identification, and simplex check."""
    ch = RadioChannel(
        number=1,
        name="TYLER 146.94",
        callsign="W5ETX",
        rxFreq=146.94000,
        txFreq=146.34000,
        offset=0.60000,
        offsetDir="-",
        mode="FM",
        toneMode="Tone",
        ctcss="136.5",
        city="Tyler",
        state="TX",
        lat=32.3513,
        lon=-95.3011,
    )
    assert ch.band == "2m"
    assert not ch.is_simplex
    assert ch.name == "TYLER 146.94"

    # Simplex channel
    simplex_ch = RadioChannel(
        number=2,
        name="2m CALL",
        rxFreq=146.52000,
        txFreq=146.52000,
        offset=0.0,
        offsetDir="off",
    )
    assert simplex_ch.is_simplex
    assert simplex_ch.band == "2m"


def test_radio_channel_band_classification():
    """Test frequency band classification logic across all amateur & airband ranges."""
    bands = [
        (29.600, "10m"),
        (52.525, "6m"),
        (121.500, "Airband"),
        (146.520, "2m"),
        (162.400, "WX"),
        (223.500, "1.25m"),
        (446.000, "70cm"),
        (462.675, "GMRS"),
        (900.000, "Other"),
    ]
    for freq, expected_band in bands:
        ch = RadioChannel(number=1, name="TEST", rxFreq=freq, txFreq=freq)
        assert ch.band == expected_band, f"Frequency {freq} should be {expected_band}, got {ch.band}"


def test_radio_channel_bad_data_validation():
    """Bad Data: Out-of-range color codes or invalid types raise ValidationError."""
    with pytest.raises(ValidationError):
        RadioChannel(number=1, name="BAD_CC", rxFreq=146.94, txFreq=146.34, colorCode=99)

    with pytest.raises(ValidationError):
        RadioChannel(number=1, name="BAD_TS", rxFreq=146.94, txFreq=146.34, timeSlot=5)


def test_radio_channel_missing_data():
    """Missing Data: Minimal channel attributes populate default values without error."""
    ch = RadioChannel(name="MIN", rxFreq=146.52, txFreq=146.52)
    assert ch.number == 1
    assert ch.mode == "FM"
    assert ch.ctcss == "None"
    assert ch.comment == ""


def test_codeplug_renumbering():
    """Test codeplug channel renumbering to continuous 1-indexed slots."""
    ch1 = RadioChannel(number=10, name="CH1", rxFreq=146.52, txFreq=146.52)
    ch2 = RadioChannel(number=50, name="CH2", rxFreq=446.00, txFreq=446.00)
    cp = Codeplug(name="TestPlug", channels=[ch1, ch2])

    assert cp.total_channels == 2
    renumbered = cp.renumbered()
    assert renumbered.channels[0].number == 1
    assert renumbered.channels[1].number == 2


def test_user_preferences_callsign_always_uppercase():
    """Verify callsign is automatically converted to uppercase regardless of user input format."""
    from core.models.preferences import UserPreferences

    # Lowercase input
    p1 = UserPreferences(callsign="w5cdn")
    assert p1.callsign == "W5CDN"

    # Mixed case with whitespace
    p2 = UserPreferences(callsign="  k5shv  ")
    assert p2.callsign == "K5SHV"

    # Update settings with lowercase
    p3 = p1.update_settings(callsign="n0call")
    assert p3.callsign == "N0CALL"
