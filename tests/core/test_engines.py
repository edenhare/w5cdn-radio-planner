"""Tri-state tests for Synthesis and Planning Engines."""

import pytest

from core.engines.aviation import AviationEngine
from core.engines.proximity import ProximityEngine
from core.engines.route_corridor import RouteCorridorEngine
from core.engines.sequence import SequenceOrganizer
from core.managers.radio_manager import RadioManager
from core.models.channel import RadioChannel
from core.providers.airports import AirportsProvider
from core.providers.geocoding import GeocodingProvider
from core.providers.repeaterbook import RepeaterBookProvider


def test_route_corridor_engine_good_data():
    """Good Data: Calculate travel corridor repeaters from Tyler, TX -> Shreveport, LA -> Jackson, MS."""
    geocoder = GeocodingProvider()
    repeater_provider = RepeaterBookProvider()
    all_repeaters = repeater_provider.get_repeaters_near(
        32.0, -94.0, radius_miles=500.0
    )

    engine = RouteCorridorEngine(geocoder=geocoder)
    result = engine.plan_route(
        waypoint_names=["Tyler, TX", "Shreveport, LA", "Jackson, MS"],
        candidate_channels=all_repeaters,
        corridor_width_miles=30.0,
        include_simplex=True,
    )

    assert len(result.waypoints) == 3
    assert result.total_distance_miles > 150.0
    assert len(result.channels) > 0

    # Ensure chronological order: Tyler repeaters should appear before Jackson repeaters
    first_ch_city = result.channels[0].city or ""
    last_ch_city = result.channels[-1].city or ""
    assert first_ch_city.lower() in {"tyler", "longview"}
    assert last_ch_city.lower() in {"jackson", "vicksburg", "monroe"}


def test_route_corridor_engine_bad_data():
    """Bad Data: Insufficient waypoints raises ValueError."""
    engine = RouteCorridorEngine()
    with pytest.raises(ValueError, match="at least 2 waypoints"):
        engine.plan_route(waypoint_names=["OnlyOneCity, TX"], candidate_channels=[])


def test_proximity_engine_good_data():
    """Good Data: 5 concentric distance bands around Dallas, TX."""
    geocoder = GeocodingProvider()
    repeater_provider = RepeaterBookProvider()
    all_repeaters = repeater_provider.get_repeaters_near(
        32.7, -96.8, radius_miles=100.0
    )

    engine = ProximityEngine(geocoder=geocoder)
    result = engine.search_proximity(
        center_location="Dallas, TX",
        candidate_channels=all_repeaters,
        radius_miles=50.0,
        include_simplex=True,
    )

    assert result.radius_miles == 50.0
    assert len(result.rings) == 5
    assert len(result.channels) > 0
    # Dallas repeaters should be in Ring 1 or 2
    dallas_in_ring_1 = any(
        "dallas" in (ch.city or "").lower() for ch in result.rings[1]
    )
    assert dallas_in_ring_1


def test_aviation_engine_good_data():
    """Good Data: Local airport frequencies around Tyler, TX (KTYR)."""
    geocoder = GeocodingProvider()
    airports_provider = AirportsProvider()

    engine = AviationEngine(geocoder=geocoder, airports_provider=airports_provider)
    result = engine.plan_aviation(center_location="Tyler, TX", radius_miles=35.0)

    assert len(result.matched_airports) >= 1
    ktyr = next((a for a in result.matched_airports if a.ident == "KTYR"), None)
    assert ktyr is not None
    assert len(result.channels) > 0
    for ch in result.channels:
        assert ch.band == "Airband"
        assert ch.mode == "AM"


def test_sequence_organizer():
    """Good Data: Assemble channels in sequence position order with deduplication and filtering."""
    mgr = RadioManager()
    spec = mgr.get_radio("btech_dmr6x2")

    primary_ch = RadioChannel(
        number=1,
        name="CORRIDOR 146.94",
        rxFreq=146.94000,
        txFreq=146.34000,
        mode="FM",
        specialType="REPEATERS",
    )

    codeplug = SequenceOrganizer.assemble(
        codeplug_name="TestSequence",
        sequence_keys=[
            "TEMPLATE:builtin_calling_channels",
            "ROUTE_PLAN",
            "TEMPLATE:builtin_noaa_wx_channels",
        ],
        primary_channels=[primary_ch],
        target_spec=spec,
        deduplicate=True,
    )

    # Calling channels (filtered to 2m and 70cm for dual band) + corridor channel + 7 WX channels
    assert codeplug.total_channels > 5
    # Verify continuous 1-indexed numbering
    for idx, ch in enumerate(codeplug.channels, start=1):
        assert ch.number == idx
