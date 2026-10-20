"""Unit tests for RepeaterBookProvider API token discovery, fallback, and parsing."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.providers.repeaterbook import OFFLINE_REPEATERS, RepeaterBookProvider


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


def test_repeaterbook_provider_live_api_graceful_fallback_on_error():
    """Resilience: Live API HTTP error gracefully falls back to offline dataset."""
    provider = RepeaterBookProvider(api_key="dummy_token")

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

        live_channels = provider.get_repeaters_near(32.35, -95.30, radius_miles=50.0)
        assert len(live_channels) == 2

    # Verify files written to disk cache with rb_STATE_DATE.json pattern
    today_str = datetime.now().strftime("%Y-%m-%d")
    assert (cache_dir / f"rb_TX_{today_str}.json").is_file()
    assert (cache_dir / f"rb_LA_{today_str}.json").is_file()
    assert (cache_dir / f"rb_ALL_{today_str}.json").is_file()

    cached_summary = provider.list_cached_state_files()
    states_found = {entry["state"] for entry in cached_summary}
    assert "TX" in states_found
    assert "LA" in states_found

    # 2. Instantiate new provider without API key (offline) pointing to the same cache directory
    offline_provider = RepeaterBookProvider(api_key="", cache_dir=cache_dir)
    assert offline_provider.has_api_key() is False

    cached_channels = offline_provider.get_repeaters_near(32.35, -95.30, radius_miles=50.0)
    assert len(cached_channels) == 2
    assert offline_provider.last_status == "DISK_CACHE"
    callsigns = {c.callsign for c in cached_channels}
    assert "W5ETX" in callsigns
    assert "K5SHR" in callsigns

