"""Tests for RadioManager and PreferencesManager."""

from pathlib import Path

import pytest

from core.managers.preferences_manager import PreferencesManager
from core.managers.radio_manager import RadioManager
from core.models.preferences import ApiTokens, UserPreferences
from core.models.radio_spec import TargetRadioSpec


def test_radio_manager_load_and_get():
    """Verify radio manager loads factory radios and retrieves by ID."""
    mgr = RadioManager()
    radios = mgr.list_radios()
    assert len(radios) >= 5

    # Check known radios
    btech = mgr.get_radio("btech_dmr6x2")
    assert btech.brand == "BTECH"
    assert btech.programmerType == "RT_SYSTEMS"

    assert mgr.has_radio("chirp_standard")
    assert not mgr.has_radio("non_existent_radio")

    with pytest.raises(KeyError, match="not found"):
        mgr.get_radio("non_existent_radio")


def test_radio_manager_save_user_radio(tmp_path: Path):
    """Verify saving custom user radio specification."""
    user_radios = tmp_path / "radios"
    mgr = RadioManager(user_radios_dir=user_radios)

    custom_spec = TargetRadioSpec(
        id="custom_radio_1",
        brand="CustomBrand",
        model="CR-100",
        description="Custom radio spec",
        maxChannels=200,
        maxNameLength=12,
        programmerType="GENERIC_CSV",
    )
    dest = mgr.save_user_radio(custom_spec)
    assert dest.is_file()
    assert dest.name == "custom_radio_1.yaml"

    # Reload and verify
    mgr.reload()
    loaded = mgr.get_radio("custom_radio_1")
    assert loaded.brand == "CustomBrand"
    assert loaded.maxChannels == 200


def test_preferences_manager(tmp_path: Path):
    """Verify loading and saving user preferences and tokens."""
    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"

    mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)
    assert mgr.preferences.callsign == "N0CALL"

    # Save updated preferences
    new_prefs = UserPreferences(
        callsign="W5CDN", primaryDmrId="3224901", distanceUnit="MILES"
    )
    mgr.save_preferences(new_prefs)
    assert prefs_file.is_file()

    # Save tokens
    tokens = ApiTokens(repeaterBookApiKey="RP_KEY_123", radioIdApiKey="RID_KEY_456")
    mgr.save_tokens(tokens)
    assert tokens_file.is_file()

    # Reload fresh instance
    reloaded_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)
    assert reloaded_mgr.preferences.callsign == "W5CDN"
    assert reloaded_mgr.preferences.primaryDmrId == "3224901"
    assert reloaded_mgr.tokens.repeaterBookApiKey == "RP_KEY_123"
