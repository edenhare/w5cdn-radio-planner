"""Unit tests for the target radio band selector."""

from __future__ import annotations

from unittest.mock import patch

from rich.console import Console

from cli.wizard.band_selector import (
    select_bands_for_radio,
    select_channel_naming_format,
    select_repeater_access,
)
from core.models.radio_spec import TargetRadioSpec


def test_select_bands_for_radio_default_confirm():
    console = Console(record=True)
    spec = TargetRadioSpec(
        id="test_radio",
        brand="TestBrand",
        model="TestModel",
        description="Test radio description",
        maxChannels=128,
        maxNameLength=8,
        programmerType="CHIRP",
        supportedBands=["2m", "70cm", "Airband", "WX"],
        supportedModes=["FM", "AM"],
    )

    # In Route Corridor, Airband is excluded by default; user confirms default
    with patch("rich.prompt.Prompt.ask", return_value="C"):
        bands = select_bands_for_radio(console, spec, mode_name="Route Corridor")

    assert bands == ["2m", "70cm", "WX"]


def test_select_bands_for_radio_toggle_band():
    console = Console(record=True)
    spec = TargetRadioSpec(
        id="test_radio",
        brand="TestBrand",
        model="TestModel",
        description="Test radio description",
        maxChannels=128,
        maxNameLength=8,
        programmerType="CHIRP",
        supportedBands=["2m", "70cm", "WX"],
        supportedModes=["FM"],
    )

    # Toggle 70cm (index 2) off, then confirm
    with patch("rich.prompt.Prompt.ask", side_effect=["2", "C"]):
        bands = select_bands_for_radio(console, spec)

    assert bands == ["2m", "WX"]


def test_select_bands_for_radio_select_all():
    console = Console(record=True)
    spec = TargetRadioSpec(
        id="test_radio",
        brand="TestBrand",
        model="TestModel",
        description="Test radio description",
        maxChannels=128,
        maxNameLength=8,
        programmerType="CHIRP",
        supportedBands=["2m", "70cm", "Airband", "WX"],
        supportedModes=["FM", "AM"],
    )

    # Select all bands with 'A', then confirm
    with patch("rich.prompt.Prompt.ask", side_effect=["A", "C"]):
        bands = select_bands_for_radio(console, spec)

    assert bands == ["2m", "70cm", "Airband", "WX"]


def test_select_bands_for_radio_cancel_returns_none():
    console = Console(record=True)
    spec = TargetRadioSpec(
        id="test_radio",
        brand="TestBrand",
        model="TestModel",
        description="Test radio description",
        maxChannels=128,
        maxNameLength=8,
        programmerType="CHIRP",
        supportedBands=["2m", "70cm"],
        supportedModes=["FM"],
    )

    with patch("rich.prompt.Prompt.ask", return_value="B"):
        bands = select_bands_for_radio(console, spec)

    assert bands is None


def test_select_repeater_access_toggle_and_confirm():
    console = Console(record=True)
    # Default is ["OPEN"]; toggle 2 (CLOSED) on, then confirm with C
    with patch("rich.prompt.Prompt.ask", side_effect=["2", "C"]):
        access = select_repeater_access(console, default_access=["OPEN"])

    assert access == ["OPEN", "CLOSED"]


def test_select_repeater_access_all_and_open_only():
    console = Console(record=True)
    # Select all (A), then confirm (C)
    with patch("rich.prompt.Prompt.ask", side_effect=["A", "C"]):
        access_all = select_repeater_access(console)
    assert access_all == ["OPEN", "CLOSED", "PRIVATE"]

    # Reset to Open only (O), then confirm (C)
    with patch("rich.prompt.Prompt.ask", side_effect=["A", "O", "C"]):
        access_open = select_repeater_access(console)
    assert access_open == ["OPEN"]


def test_select_channel_naming_format_select_and_confirm():
    console = Console(record=True)
    spec = TargetRadioSpec(
        id="anytone_at778uv",
        brand="AnyTone",
        model="AT-778UV",
        description="5-char LCD mobile",
        maxChannels=127,
        maxNameLength=5,
        programmerType="CHIRP",
        supportedBands=["2m", "70cm"],
        supportedModes=["FM"],
    )

    # Select option 3 (CALLSIGN), then confirm with C
    with patch("rich.prompt.Prompt.ask", side_effect=["3", "C"]):
        fmt = select_channel_naming_format(console, spec, default_format="CITY_FREQ")

    assert fmt == "CALLSIGN"
    rendered = console.export_text()
    assert "W5ETX" in rendered
    assert "AT-778UV" in rendered


