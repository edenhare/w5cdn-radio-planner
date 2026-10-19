"""Tests for Rich UI renderers."""

import io

from rich.console import Console

from cli.ui.renderers import (
    render_config_panel,
    render_header,
    render_review_table,
    render_split_summary,
    render_yaml_error,
)
from core.config.recipe import CorridorConfig, RadioPlannerRecipe
from core.config.yaml_loader import YamlDiagnosticError
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
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
        corridor=CorridorConfig(
            waypoints=["Tyler, TX", "Jackson, MS"], corridor_width_miles=25.0
        ),
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
