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


def test_name_condenser_city_frequency_format():
    """Verify city + frequency formatting produces 'City x.xx' conforming to radio LCD constraints."""
    spec_10c = TargetRadioSpec(
        id="baofeng_5rm",
        brand="Baofeng",
        model="5RM",
        description="Baofeng test",
        maxChannels=999,
        maxNameLength=10,
        allowDots=True,
        allowSpaces=True,
        allowedSpecialChars="-_",
    )

    # Tyler 147.20000 -> Tyler 7.20 (len 10)
    res1 = NameCondenser.format_city_frequency("Tyler", 147.20000, spec_10c)
    assert res1 == "Tyler 7.20"
    assert len(res1) <= 10

    # Shreveport 146.76000 -> Shrev 6.76 (len 10)
    res2 = NameCondenser.format_city_frequency("Shreveport", 146.76000, spec_10c)
    assert res2 == "Shrev 6.76"
    assert len(res2) <= 10

    # 16-char radio allows full city name
    spec_16c = TargetRadioSpec(
        id="btech_dmr6x2",
        brand="BTECH",
        model="DMR-6X2",
        description="BTech test",
        maxChannels=4000,
        maxNameLength=16,
        allowDots=True,
        allowSpaces=True,
        allowedSpecialChars="-_",
    )
    res3 = NameCondenser.format_city_frequency("Shreveport", 146.76000, spec_16c)
    assert res3 == "Shreveport 6.76"
    assert len(res3) <= 16

    # Alinco DR-735T: 6-char limit, allowDots=False, allowSpaces=True, allowedSpecialChars=" -/"
    from core.managers.radio_manager import RadioManager

    rm = RadioManager()
    alinco_spec = rm.get_radio("alinco_dr735t")
    assert alinco_spec.maxNameLength == 6
    assert alinco_spec.allowDots is False
    assert alinco_spec.allowedSpecialChars == " -/"

    res_alinco_rpt = NameCondenser.format_city_frequency("Tyler", 147.20000, alinco_spec)
    assert len(res_alinco_rpt) <= 6
    assert "." not in res_alinco_rpt
    assert res_alinco_rpt == "Tyl720"

    res_alinco_air = NameCondenser.condense("KTYR ATIS", alinco_spec)
    assert len(res_alinco_air) <= 6
    assert res_alinco_air == "KTYRAT"
