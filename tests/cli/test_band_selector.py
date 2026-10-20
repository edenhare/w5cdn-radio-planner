"""Unit tests for the target radio band selector."""

from __future__ import annotations

from unittest.mock import patch

from rich.console import Console

from cli.wizard.band_selector import select_bands_for_radio
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
