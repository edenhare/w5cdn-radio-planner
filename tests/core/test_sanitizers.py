"""Tri-state unit tests for DataSanitizer and NameCondenser."""

from pathlib import Path

import pytest

from core.models.radio_spec import TargetRadioSpec
from core.sanitizers.condenser import NameCondenser
from core.sanitizers.sanitizer import DataSanitizer


def test_data_sanitizer_good_data():
    """Good Data: Clean text, normal frequency, safe path."""
    text = " Tyler ARC Repeater 146.94 "
    assert DataSanitizer.sanitize_text(text) == "Tyler ARC Repeater 146.94"

    freq = DataSanitizer.sanitize_frequency("146.94000")
    assert freq == 146.94

    safe_path = DataSanitizer.validate_safe_path("exports/my_codeplug.csv")
    assert safe_path.name == "my_codeplug.csv"


def test_data_sanitizer_bad_data():
    """Bad Data: Control chars, out-of-range frequencies, path traversal."""
    # Control chars stripping
    dirty = "Test\x00Repeater\x1fName"
    assert DataSanitizer.sanitize_text(dirty) == "TestRepeaterName"

    # Out of range frequencies
    with pytest.raises(ValueError, match="out of valid operational range"):
        DataSanitizer.sanitize_frequency(0.5)

    with pytest.raises(ValueError, match="out of valid operational range"):
        DataSanitizer.sanitize_frequency(2500.0)

    with pytest.raises(ValueError, match="must be numeric"):
        DataSanitizer.sanitize_frequency("not_a_frequency")

    # Path traversal detection
    base_dir = Path(__file__).resolve().parent
    with pytest.raises(PermissionError, match="Path traversal detected"):
        DataSanitizer.validate_safe_path("../../../etc/passwd", base_dir=base_dir)

    with pytest.raises(ValueError, match="illegal null bytes"):
        DataSanitizer.validate_safe_path("file\x00name.csv")


def test_data_sanitizer_missing_data():
    """Missing Data: Empty string, null-like values."""
    assert DataSanitizer.sanitize_text("") == ""
    assert DataSanitizer.sanitize_filename("") == "export"


def test_name_condenser_intelligent_abbreviations():
    """Test standard radio abbreviation replacement and LCD limit truncation."""
    # Spec 3.2: "TYLER REPEATER NORTH" with 8 char limit (e.g. Wouxun)
    wouxun_spec = TargetRadioSpec(
        id="wouxun_kg_uv980p",
        brand="Wouxun",
        model="KG-UV980P",
        description="Wouxun test",
        maxChannels=999,
        maxNameLength=8,
        allowDots=False,
        allowSpaces=False,
        allowedSpecialChars="-_",
    )

    condensed = NameCondenser.condense("TYLER REPEATER NORTH", wouxun_spec)
    assert len(condensed) <= 8
    # REPEATER -> RPT, NORTH -> N, spaces removed
    assert "RPT" in condensed or "TYLER" in condensed
    assert " " not in condensed

    # Spec 10 char limit with spaces (e.g. Baofeng 5RM)
    baofeng_spec = TargetRadioSpec(
        id="baofeng_5rm",
        brand="Baofeng",
        model="5RM",
        description="Baofeng test",
        maxChannels=999,
        maxNameLength=10,
        allowDots=False,
        allowSpaces=True,
        allowedSpecialChars="-_",
    )
    condensed_5rm = NameCondenser.condense("DALLAS EMERGENCY", baofeng_spec)
    assert len(condensed_5rm) <= 10
    assert "EMG" in condensed_5rm


def test_name_condenser_empty_or_special_chars():
    """Test NameCondenser with empty name or unsupported characters."""
    spec = TargetRadioSpec(
        id="test_radio",
        brand="Test",
        model="Model",
        description="Test",
        maxNameLength=6,
        allowDots=False,
        allowSpaces=False,
        allowedSpecialChars="-",
    )
    assert NameCondenser.condense("", spec) == "CH"
    assert NameCondenser.condense("A.B.C", spec) == "ABC"
    assert NameCondenser.condense("TEST@#$", spec) == "TEST--"
