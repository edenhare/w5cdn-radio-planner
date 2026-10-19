"""Tests for RadioManager, PreferencesManager, and TemplateManager."""

from pathlib import Path

import pytest

from core.managers.preferences_manager import PreferencesManager
from core.managers.radio_manager import RadioManager
from core.managers.template_manager import TemplateManager
from core.models.preferences import ApiTokens, UserPreferences
from core.models.radio_spec import TargetRadioSpec
from core.models.template import PresetTemplateFile


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


def test_radio_manager_save_and_delete_user_radio(tmp_path: Path):
    """Verify saving, detecting, and deleting custom user radio specification."""
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
    assert mgr.is_user_radio("custom_radio_1")

    # Reload and verify
    mgr.reload()
    loaded = mgr.get_radio("custom_radio_1")
    assert loaded.brand == "CustomBrand"
    assert loaded.maxChannels == 200

    # Delete custom user radio
    assert mgr.delete_user_radio("custom_radio_1") is True
    assert not mgr.has_radio("custom_radio_1")
    assert mgr.delete_user_radio("custom_radio_1") is False


def test_template_manager_builtin_and_custom(tmp_path: Path):
    """Verify TemplateManager lists built-in and user custom templates."""
    tpl_dir = tmp_path / "templates"
    tpl_mgr = TemplateManager(custom_templates_dir=tpl_dir)

    templates = tpl_mgr.list_templates()
    tpl_ids = {t.id for t in templates}
    assert "builtin_calling_channels" in tpl_ids
    assert "builtin_noaa_wx_channels" in tpl_ids

    # Check built-in channels
    calling_chans = tpl_mgr.get_template_channels("builtin_calling_channels")
    assert len(calling_chans) >= 6
    wx_chans = tpl_mgr.get_template_channels("builtin_noaa_wx_channels")
    assert len(wx_chans) == 7

    # Add custom template
    csv_data = "Name,Frequency,Mode,Power,Comment\nSAR_1,155.160,FM,High,Search and Rescue\n"
    custom_tpl = PresetTemplateFile(
        id="sar_ops",
        name="SAR Operations",
        description="Search and Rescue operations frequencies",
        tagText="SAR",
        tagColorHex="#FF9800",
        fileName="sar_ops.csv",
        rawCsvContent=csv_data,
    )
    tpl_mgr.save_template(custom_tpl)

    # Reload and verify
    tpl_mgr.reload()
    sar_retrieved = tpl_mgr.get_template("sar_ops")
    assert sar_retrieved.name == "SAR Operations"
    sar_chans = tpl_mgr.get_template_channels("sar_ops")
    assert len(sar_chans) == 1
    assert sar_chans[0].name == "SAR_1"
    assert sar_chans[0].rxFreq == 155.160


def test_preferences_manager(tmp_path: Path):
    """Verify loading and saving user preferences and tokens."""
    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"

    mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)
    assert mgr.preferences.callsign == "N0CALL"

    # Save updated preferences
    new_prefs = UserPreferences(callsign="W5CDN", primaryDmrId="3224901", distanceUnit="MILES")
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
