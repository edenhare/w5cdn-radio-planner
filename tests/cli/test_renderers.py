"""Tests for Rich UI renderers."""

import io

from rich.console import Console

from cli.ui.renderers import (
    format_location,
    render_config_panel,
    render_header,
    render_review_table,
    render_split_summary,
    render_yaml_error,
)
from cli.ui.theme import make_channel_badges
from core.config.recipe import CorridorConfig, RadioPlannerRecipe
from core.config.yaml_loader import YamlDiagnosticError
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.providers.geocoding import GeoPoint


def test_renderers_output():
    """Verify all Rich renderers render to string console without exception."""
    output = io.StringIO()
    console = Console(file=output, width=120)

    # 1. Header
    render_header(console, title="TestApp", subtitle="Testing")

    # 2. Config Panel
    recipe = RadioPlannerRecipe(
        mode="ROUTE_CORRIDOR",
        name="TestPlan",
        corridor=CorridorConfig(waypoints=["Tyler, TX", "Jackson, MS"], corridor_width_miles=25.0),
    )
    render_config_panel(console, recipe)

    # 3. Split Summary
    render_split_summary(
        console=console,
        title="Test Summary",
        waypoints=[
            GeoPoint(lat=32.0, lon=-95.0, name="Tyler"),
            GeoPoint(lat=32.0, lon=-90.0, name="Jackson"),
        ],
        cumulative_miles=[0.0, 200.0],
        total_miles=200.0,
        band_counts={"2m": 5, "70cm": 2},
        total_channels=7,
    )

    # 4. Review Table
    ch = RadioChannel(
        number=1,
        name="TEST",
        rxFreq=146.52,
        txFreq=146.52,
        mode="FM",
        comment="Simplex",
    )
    cp = Codeplug(name="TestPlug", channels=[ch])
    render_review_table(console, cp, max_display=10)

    # 5. YAML Error
    err = YamlDiagnosticError(
        message="Test error",
        line=2,
        column=5,
        snippet="  key: val\n> bad: [unclosed",
        suggestion="Close bracket",
    )
    render_yaml_error(console, err)

    content = output.getvalue()
    assert "TestApp" in content
    assert "TestPlan" in content
    assert "Tyler" in content
    assert "146.52000" in content
    assert "Test error" in content


def test_render_review_table_formatting_and_constraints():
    """Verify render_review_table excludes Comments, formats Location City/ST, condenses names, and renders header."""
    output = io.StringIO()
    console = Console(file=output, width=120)

    spec = TargetRadioSpec(
        id="test_radio_10c",
        brand="Test",
        model="Pocket",
        description="Test pocket radio",
        maxChannels=100,
        maxNameLength=10,
        allowSpaces=False,
    )

    ch1 = RadioChannel(
        number=1,
        name="TYLER REPEATER 146.94",
        rxFreq=146.94,
        txFreq=146.34,
        mode="FM",
        band="2m",
        city="Tyler",
        state="Texas",
        comment="This comment should not appear in the table",
    )
    ch2 = RadioChannel(
        number=2,
        name="SHREVEPORT DMR",
        rxFreq=444.10,
        txFreq=449.10,
        mode="DMR",
        band="70cm",
        city="Shreveport",
        state="Louisiana",
        comment="Confidential Repeater Comment",
    )
    cp = Codeplug(name="Corridor_Test", channels=[ch1, ch2])

    render_review_table(console, cp, target_spec=spec)
    content = output.getvalue()

    # 1. Header rendered
    assert "Codeplug Channel Review" in content

    # 2. Comments excluded
    assert "This comment should not appear in the table" not in content
    assert "Confidential Repeater Comment" not in content
    assert "Comment" not in content

    # 3. Location formatted as City, ST
    assert "Tyler, TX" in content
    assert "Shreveport, LA" in content

    # 4. Channel name condensed according to spec (<= 10 chars, no spaces)
    assert "TYLER REPEATER 146.94" not in content


def test_format_location_and_badges_styling():
    """Verify format_location resolutions and make_channel_badges styling without backgrounds."""
    assert format_location("Tyler", "Texas") == "Tyler, TX"
    assert format_location("Shreveport", "LA") == "Shreveport, LA"
    assert format_location("Jackson, MS", None) == "Jackson, MS"
    assert format_location(None, None) == "-"

    ch = RadioChannel(
        number=1,
        name="WX1",
        rxFreq=162.55,
        txFreq=162.55,
        mode="FM",
        band="WX",
        specialType="WX",
    )
    badges = make_channel_badges(ch)
    # Ensure no 'on ' background style substring in badge styles
    for span in badges.spans:
        assert "on " not in str(span.style).lower()
