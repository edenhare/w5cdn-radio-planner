"""Tri-state tests for Special Channels and Hardware Band Filtering."""

from core.models.radio_spec import TargetRadioSpec
from core.special_channels import (
    filter_channels_for_radio,
    get_national_calling_channels,
    get_noaa_wx_channels,
)


def test_national_calling_channels():
    """Good Data: Verify standard calling channels (10m, 6m, 2m, 1.25m, 70cm, GMRS)."""
    calling = get_national_calling_channels()
    assert len(calling) == 6
    bands = {ch.band for ch in calling}
    assert "2m" in bands
    assert "70cm" in bands
    assert "GMRS" in bands
    for ch in calling:
        assert ch.is_simplex
        assert ch.specialType in {"CALLING", "GMRS"}


def test_noaa_weather_channels():
    """Good Data: Verify 7 standard NOAA weather radio channels."""
    wx = get_noaa_wx_channels()
    assert len(wx) == 7
    for ch in wx:
        assert ch.band == "WX"
        assert ch.specialType == "WX"
        assert 162.400 <= ch.rxFreq <= 162.550


def test_filter_channels_for_radio():
    """Test filtering channels according to radio supported bands and modes."""
    # Dual-band radio supporting 2m, 70cm, and WX
    dual_band_spec = TargetRadioSpec(
        id="dual_band",
        brand="Test",
        model="2M70CM",
        description="Dual band",
        supportedBands=["2m", "70cm", "WX"],
        supportedModes=["FM"],
    )

    calling = get_national_calling_channels()  # 10m, 6m, 2m, 1.25m, 70cm, GMRS
    wx = get_noaa_wx_channels()  # 7 WX channels

    all_channels = calling + wx
    filtered = filter_channels_for_radio(all_channels, dual_band_spec)

    # 10m, 6m, 1.25m, GMRS should be filtered out
    # 2m calling (1) + 70cm calling (1) + 7 WX channels = 9 channels
    assert len(filtered) == 9
    bands = {ch.band for ch in filtered}
    assert bands == {"2m", "70cm", "WX"}


def test_filter_channels_empty_or_unsupported():
    """Missing & Bad Data: Empty channels list or unsupported modes."""
    spec = TargetRadioSpec(
        id="am_only",
        brand="Test",
        model="AM-Radio",
        description="AM Only",
        supportedBands=["Airband"],
        supportedModes=["AM"],
    )
    # FM calling channels against AM-only radio
    calling = get_national_calling_channels()
    assert filter_channels_for_radio(calling, spec) == []
    assert filter_channels_for_radio([], spec) == []
