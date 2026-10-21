"""Unit tests for RepeaterBookProvider API token discovery, fallback, and parsing."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.providers.geocoding import GeoPoint
from core.providers.repeaterbook import (
    OFFLINE_REPEATERS,
    RepeaterBookProvider,
    identify_states_for_proximity,
    identify_states_for_route,
)


def test_repeaterbook_provider_offline_dataset():
    """Good Data: Ensure expanded offline dataset contains comprehensive repeaters."""
    provider = RepeaterBookProvider(api_key=None)
    repeaters = provider.get_repeaters_near(32.35, -95.30, radius_miles=50.0)

    assert len(repeaters) >= 50
    assert len(OFFLINE_REPEATERS) >= 60

    # Verify channel attributes
    for ch in repeaters:
        assert ch.rxFreq > 0.0
        assert ch.txFreq > 0.0
        assert ch.specialType == "REPEATERS"
        assert ch.mode in {"FM", "DMR"}


def test_repeaterbook_provider_api_key_discovery_explicit():
    """Good Data: Explicit API key takes precedence."""
    provider = RepeaterBookProvider(api_key="test_explicit_key")
    assert provider.has_api_key() is True
    assert provider.api_key == "test_explicit_key"
    assert provider.token_source == "preferences_or_parameter"


def test_repeaterbook_provider_api_key_discovery_env(monkeypatch):
    """Good Data: Environment variable discovery."""
    monkeypatch.setenv("REPEATERBOOK_API_KEY", "env_secret_key_123")
    provider = RepeaterBookProvider()
    assert provider.has_api_key() is True
    assert provider.api_key == "env_secret_key_123"
    assert provider.token_source == "environment_variable"


def test_repeaterbook_provider_api_key_discovery_file(tmp_path, monkeypatch):
    """Good Data: File discovery from docs or tokens directory."""
    monkeypatch.delenv("REPEATERBOOK_API_KEY", raising=False)
    # When no explicit key and no env var, checks docs/RepeaterBookPythonClientApiToken.txt if present
    doc_token_path = Path("docs/RepeaterBookPythonClientApiToken.txt")
    if doc_token_path.is_file():
        provider = RepeaterBookProvider()
        assert provider.has_api_key() is True
        assert len(provider.api_key) > 10
    else:
        provider = RepeaterBookProvider()
        assert provider.has_api_key() is False


def test_repeaterbook_provider_live_api_graceful_fallback_on_error(tmp_path: Path):
    """Resilience: Live API HTTP error gracefully falls back to offline dataset."""
    provider = RepeaterBookProvider(api_key="dummy_token", cache_dir=tmp_path / "empty_cache")

    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_instance.__enter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_instance

        channels = provider.get_repeaters_near(32.35, -95.30, radius_miles=25.0)
        assert len(channels) >= 50
        assert "LIVE_API_FALLBACK" in provider.last_status


def test_repeaterbook_provider_live_api_success(tmp_path: Path):
    """Good Data: Live API success parses returned repeaters."""
    provider = RepeaterBookProvider(api_key="dummy_token", cache_dir=tmp_path / "cache")

    sample_api_response = [
        {
            "Frequency": "146.9400",
            "Input Freq": "146.3400",
            "PL": "136.5",
            "Nearest City": "Tyler",
            "Callsign": "W5ETX",
            "State": "TX",
            "Lat": "32.3513",
            "Long": "-95.3011",
            "Operational Mode": "FM",
        }
    ]

    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_api_response
        mock_instance.__enter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_instance

        channels = provider.get_repeaters_near(32.35, -95.30, radius_miles=25.0)
        assert len(channels) == 1
        assert channels[0].callsign == "W5ETX"
        assert channels[0].rxFreq == 146.94
        assert channels[0].ctcss == "136.5"
        assert provider.last_status == "LIVE_API_SUCCESS"


def test_repeaterbook_provider_disk_cache_save_and_load(tmp_path: Path):
    """Good Data: Ensure downloaded state repeaters are saved to data cache and reloaded offline."""
    cache_dir = tmp_path / "data" / "repeaterbook"
    provider = RepeaterBookProvider(api_key="dummy_token", cache_dir=cache_dir)

    sample_api_response = {
        "count": 2,
        "results": [
            {
                "State ID": "48",
                "State": "Texas",
                "Frequency": "146.9400",
                "Input Freq": "146.3400",
                "PL": "136.5",
                "Nearest City": "Tyler",
                "Callsign": "W5ETX",
                "Lat": "32.3513",
                "Long": "-95.3011",
                "FM Analog": "Yes",
            },
            {
                "State ID": "22",
                "State": "Louisiana",
                "Frequency": "146.8200",
                "Input Freq": "146.2200",
                "PL": "107.2",
                "Nearest City": "Shreveport",
                "Callsign": "K5SHR",
                "Lat": "32.5251",
                "Long": "-93.7502",
                "FM Analog": "Yes",
            },
        ],
    }

    # 1. Fetch with mock API to populate disk cache
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_api_response
        mock_instance.__enter__.return_value.get.return_value = mock_response
        mock_client.return_value = mock_instance

        live_channels = provider.get_repeaters_for_states(["TX", "LA"])
        assert len(live_channels) == 2

    # Verify files written to disk cache with rb_STATE_DATE.json pattern (no rb_ALL file)
    today_str = datetime.now().strftime("%Y-%m-%d")
    assert (cache_dir / f"rb_TX_{today_str}.json").is_file()
    assert (cache_dir / f"rb_LA_{today_str}.json").is_file()
    assert not (cache_dir / f"rb_ALL_{today_str}.json").exists()

    cached_summary = provider.list_cached_state_files()
    states_found = {entry["state"] for entry in cached_summary}
    assert "TX" in states_found
    assert "LA" in states_found

    # 2. Instantiate new provider without API key (offline) pointing to the same cache directory
    offline_provider = RepeaterBookProvider(api_key="", cache_dir=cache_dir)
    assert offline_provider.has_api_key() is False

    cached_channels = offline_provider.get_repeaters_near(32.35, -95.30, radius_miles=100.0)
    assert len(cached_channels) == 2
    assert offline_provider.last_status == "DISK_CACHE"
    callsigns = {c.callsign for c in cached_channels}
    assert "W5ETX" in callsigns
    assert "K5SHR" in callsigns


def test_repeaterbook_filter_on_air_and_open_only():
    """Verify that off-air, closed, and private repeaters are filtered out by default, and configurable via allowed_use."""
    provider = RepeaterBookProvider(api_key="")

    # Item 1: On-air and OPEN (should pass)
    item_valid = {
        "Frequency": "146.9400",
        "Input Freq": "146.3400",
        "Callsign": "W5OK",
        "Operational Status": "On-air",
        "Use": "OPEN",
    }
    ch1 = provider._parse_api_item(1, item_valid)
    assert ch1 is not None
    assert ch1.callsign == "W5OK"

    # Item 2: Off-air and OPEN (should be filtered out even if OPEN is allowed)
    item_off_air = {
        "Frequency": "146.8200",
        "Input Freq": "146.2200",
        "Callsign": "W5OFF",
        "Operational Status": "Off-air",
        "Use": "OPEN",
    }
    assert provider._parse_api_item(2, item_off_air) is None
    assert provider._parse_api_item(2, item_off_air, allowed_use={"OPEN", "CLOSED", "PRIVATE"}) is None

    # Item 3: On-air and CLOSED (filtered out by default, allowed when CLOSED selected)
    item_closed = {
        "Frequency": "444.2000",
        "Input Freq": "449.2000",
        "Callsign": "W5CLS",
        "Operational Status": "On-air",
        "Use": "CLOSED",
    }
    assert provider._parse_api_item(3, item_closed) is None
    ch_closed = provider._parse_api_item(3, item_closed, allowed_use={"OPEN", "CLOSED"})
    assert ch_closed is not None
    assert ch_closed.callsign == "W5CLS"

    # Item 4: On-air and PRIVATE (filtered out by default, allowed when PRIVATE selected)
    item_private = {
        "Frequency": "444.5000",
        "Input Freq": "449.5000",
        "Callsign": "W5PVT",
        "Operational Status": "On-air",
        "Use": "PRIVATE",
    }
    assert provider._parse_api_item(4, item_private) is None
    ch_private = provider._parse_api_item(4, item_private, allowed_use={"PRIVATE"})
    assert ch_private is not None
    assert ch_private.callsign == "W5PVT"


def test_identify_states_for_route_and_proximity():
    """Verify state identification only returns states touched by the route or proximity ring."""
    route_states = identify_states_for_route(
        ["Tyler, TX", "Shreveport, LA", "Jackson, MS"],
        geo_points=[
            GeoPoint(lat=32.3513, lon=-95.3011, name="Tyler, TX"),
            GeoPoint(lat=32.5252, lon=-93.7502, name="Shreveport, LA"),
            GeoPoint(lat=32.2988, lon=-90.1848, name="Jackson, MS"),
        ],
        corridor_width_miles=25.0,
    )
    assert route_states == ["TX", "LA", "MS"]

    # Proximity around Tyler, TX with 30mi radius -> only TX
    prox_tx = identify_states_for_proximity(
        "Tyler, TX",
        center_point=GeoPoint(lat=32.3513, lon=-95.3011, name="Tyler, TX"),
        radius_miles=30.0,
    )
    assert prox_tx == ["TX"]

    # Proximity around Shreveport, LA with 40mi radius -> LA and TX
    prox_shreveport = identify_states_for_proximity(
        "Shreveport, LA",
        center_point=GeoPoint(lat=32.5252, lon=-93.7502, name="Shreveport, LA"),
        radius_miles=40.0,
    )
    assert "LA" in prox_shreveport
    assert "TX" in prox_shreveport

    # Canadian route: Toronto, ON -> Montreal, QC
    ca_route_states = identify_states_for_route(
        ["Toronto, ON", "Ottawa, ON", "Montreal, QC"],
        geo_points=[
            GeoPoint(lat=43.6532, lon=-79.3832, name="Toronto, ON"),
            GeoPoint(lat=45.4215, lon=-75.6972, name="Ottawa, ON"),
            GeoPoint(lat=45.5017, lon=-73.5673, name="Montreal, QC"),
        ],
        corridor_width_miles=25.0,
    )
    assert "ON" in ca_route_states
    assert "QC" in ca_route_states

    # Canadian proximity: Calgary, AB
    prox_calgary = identify_states_for_proximity(
        "Calgary, AB",
        center_point=GeoPoint(lat=51.0447, lon=-114.0719, name="Calgary, AB"),
        radius_miles=30.0,
    )
    assert prox_calgary == ["AB"]


def test_get_repeaters_for_states_fresh_vs_stale_refresh(tmp_path: Path):
    """Verify fresh state files are reused without API calls and stale state files are re-downloaded."""
    cache_dir = tmp_path / "repeaterbook"
    cache_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    old_date_str = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")

    # Write a fresh TX file (0 days old)
    tx_fresh_path = cache_dir / f"rb_TX_{today_str}.json"
    tx_fresh_path.write_text(
        json.dumps(
            {
                "state": "TX",
                "downloaded_at": today_str,
                "count": 1,
                "results": [
                    {
                        "State": "TX",
                        "Frequency": "146.9400",
                        "Input Freq": "146.3400",
                        "Nearest City": "Tyler",
                        "Callsign": "W5TXFRESH",
                        "Lat": "32.3513",
                        "Long": "-95.3011",
                        "Operational Status": "On-air",
                        "Use": "OPEN",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # Write a stale LA file (45 days old)
    la_stale_path = cache_dir / f"rb_LA_{old_date_str}.json"
    la_stale_path.write_text(
        json.dumps(
            {
                "state": "LA",
                "downloaded_at": old_date_str,
                "count": 1,
                "results": [
                    {
                        "State": "LA",
                        "Frequency": "146.8200",
                        "Input Freq": "146.2200",
                        "Nearest City": "Shreveport",
                        "Callsign": "K5OLDLA",
                        "Lat": "32.5251",
                        "Long": "-93.7502",
                        "Operational Status": "On-air",
                        "Use": "OPEN",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    provider = RepeaterBookProvider(api_key="dummy_token", cache_dir=cache_dir)

    # Check state file info before call
    assert provider.get_state_file_info("TX", max_age_days=30)["status"] == "FRESH"
    assert provider.get_state_file_info("LA", max_age_days=30)["status"] == "STALE"

    refreshed_la_api = {
        "count": 1,
        "results": [
            {
                "State": "LA",
                "Frequency": "146.7600",
                "Input Freq": "146.1600",
                "Nearest City": "Shreveport",
                "Callsign": "K5NEWLA",
                "Lat": "32.5251",
                "Long": "-93.7502",
                "Operational Status": "On-air",
                "Use": "OPEN",
            }
        ],
    }

    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = refreshed_la_api
        mock_get = mock_instance.__enter__.return_value.get
        mock_get.return_value = mock_response
        mock_client.return_value = mock_instance

        channels = provider.get_repeaters_for_states(["TX", "LA"], max_age_days=30, allowed_use=["OPEN"])

        # Only 1 HTTP GET call should have been made (for stale LA, state_id=22), NOT for fresh TX!
        assert mock_get.call_count == 1
        called_url = mock_get.call_args.args[0]
        assert "state_id=22" in called_url

    callsigns = {c.callsign for c in channels}
    assert "W5TXFRESH" in callsigns
    assert "K5NEWLA" in callsigns
    assert "K5OLDLA" not in callsigns

    # Old LA file should be replaced by today's LA file
    assert not la_stale_path.exists()
    assert (cache_dir / f"rb_LA_{today_str}.json").is_file()



