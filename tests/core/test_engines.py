"""Tri-state tests for Synthesis and Planning Engines."""

import pytest

from core.engines.aviation import AviationEngine
from core.engines.proximity import ProximityEngine
from core.engines.route_corridor import RouteCorridorEngine
from core.engines.sequence import SequenceOrganizer
from core.managers.radio_manager import RadioManager
from core.models.channel import RadioChannel
from core.providers.airports import AirportsProvider
from core.providers.geocoding import (
    GeocodingProvider,
    GeoPoint,
    along_track_distance,
)
from core.providers.repeaterbook import RepeaterBookProvider


def test_route_corridor_engine_good_data(tmp_path):
    """Good Data: Calculate travel corridor repeaters from Tyler, TX -> Shreveport, LA -> Jackson, MS."""
    geocoder = GeocodingProvider()
    repeater_provider = RepeaterBookProvider(api_key="", cache_dir=tmp_path / "empty_cache")
    all_repeaters = repeater_provider.get_repeaters_near(32.0, -94.0, radius_miles=500.0)

    engine = RouteCorridorEngine(geocoder=geocoder)
    result = engine.plan_route(
        waypoint_names=["Tyler, TX", "Shreveport, LA", "Jackson, MS"],
        candidate_channels=all_repeaters,
        corridor_width_miles=30.0,
        include_simplex=True,
    )

    assert len(result.waypoints) == 3
    assert result.total_distance_miles > 150.0
    assert len(result.channels) >= 50

    # Ensure chronological order: Tyler repeaters should appear before Jackson repeaters
    first_ch_city = result.channels[0].city or ""
    last_ch_city = result.channels[-1].city or ""
    assert first_ch_city.lower() in {"tyler", "lindale", "hideaway", "kilgore", "longview"}
    assert last_ch_city.lower() in {"jackson", "vicksburg", "monroe", "pearl", "brandon", "madison", "shiloh"}
    corridor_cities = {c.city.lower() for c in result.channels if c.city}
    assert "vicksburg" in corridor_cities
    assert "ruston" in corridor_cities


def test_route_corridor_engine_bad_data():
    """Bad Data: Insufficient waypoints raises ValueError."""
    engine = RouteCorridorEngine()
    with pytest.raises(ValueError, match="at least 2 waypoints"):
        engine.plan_route(waypoint_names=["OnlyOneCity, TX"], candidate_channels=[])


def test_proximity_engine_good_data(tmp_path):
    """Good Data: 5 concentric distance bands around Dallas, TX."""
    geocoder = GeocodingProvider()
    repeater_provider = RepeaterBookProvider(api_key="", cache_dir=tmp_path / "cache")
    all_repeaters = repeater_provider.get_repeaters_near(32.7, -96.8, radius_miles=100.0)

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
    dallas_in_ring_1 = any("dallas" in (ch.city or "").lower() for ch in result.rings[1])
    assert dallas_in_ring_1


def test_aviation_engine_good_data():
    """Good Data: Local airport frequencies around Tyler, TX (KTYR and regional airfields within 35 mi)."""
    geocoder = GeocodingProvider()
    airports_provider = AirportsProvider()

    engine = AviationEngine(geocoder=geocoder, airports_provider=airports_provider)
    result = engine.plan_aviation(center_location="Tyler, TX", radius_miles=35.0)

    assert len(result.matched_airports) >= 8
    assert len(result.airport_distances) == len(result.matched_airports)
    # Closest airport should be KTYR (~5.8 mi), and distances must be sorted ascending and > 0
    assert result.matched_airports[0].ident == "KTYR"
    assert 4.0 <= result.airport_distances[0] <= 10.0
    assert result.airport_distances == sorted(result.airport_distances)

    matched_idents = {a.ident for a in result.matched_airports}
    assert {"KTYR", "7F3", "3F9", "KJDD", "F12", "F44", "KJSO", "KGGG"}.issubset(matched_idents)

    assert len(result.channels) > 15
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


def test_sequence_organizer_allowed_bands_filtering():
    """Verify SequenceOrganizer restricts channels to operator's selected bands."""
    mgr = RadioManager()
    spec = mgr.get_radio("btech_dmr6x2")

    ch_2m = RadioChannel(
        number=1,
        name="2m Rpt",
        rxFreq=146.940,
        txFreq=146.340,
        mode="FM",
        specialType="REPEATERS",
    )
    ch_70cm = RadioChannel(
        number=2,
        name="70cm Rpt",
        rxFreq=442.200,
        txFreq=447.200,
        mode="FM",
        specialType="REPEATERS",
    )

    # Allow 2m ONLY
    codeplug = SequenceOrganizer.assemble(
        codeplug_name="2mOnly",
        sequence_keys=["ROUTE_PLAN"],
        primary_channels=[ch_2m, ch_70cm],
        target_spec=spec,
        allowed_bands=["2m"],
    )

    assert codeplug.total_channels == 1
    assert codeplug.channels[0].name == "2m Rpt"
    assert codeplug.channels[0].band == "2m"


def test_along_track_distance_calculation():
    """Verify along_track_distance correctly measures progress along segment."""
    p_start = GeoPoint(lat=32.0, lon=-95.0, name="Start")
    p_end = GeoPoint(lat=32.0, lon=-90.0, name="End")
    p_mid = GeoPoint(lat=32.1, lon=-92.5, name="Mid")
    p_behind = GeoPoint(lat=32.0, lon=-96.0, name="Behind")

    atd_mid = along_track_distance(p_mid, p_start, p_end, unit="MILES")
    assert atd_mid > 100.0

    atd_behind = along_track_distance(p_behind, p_start, p_end, unit="MILES")
    assert atd_behind < 0.0
