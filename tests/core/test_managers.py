"""Tests for RadioManager, PreferencesManager, and TemplateManager."""

from pathlib import Path

import pytest

from core.managers.preferences_manager import PreferencesManager
from core.managers.radio_manager import RadioManager
from core.managers.template_manager import TemplateManager
from core.models.preferences import ApiTokens, UserPreferences
from core.models.radio_spec import TargetRadioSpec
from core.models.template import PresetTemplateFile, TemplateChannelItem


def test_radio_manager_load_and_get():
    """Verify radio manager loads factory radios and retrieves by ID."""
    mgr = RadioManager()
    radios = mgr.list_radios()
    assert len(radios) >= 5

    # Check known radios
    btech = mgr.get_radio("btech_dmr6x2")
    assert btech.brand == "BTECH"

    assert mgr.has_radio("baofeng_5rm")
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
    """Verify TemplateManager lists app resources and user custom templates, with override support."""
    tpl_dir = tmp_path / "templates"
    tpl_mgr = TemplateManager(custom_templates_dir=tpl_dir)

    templates = tpl_mgr.list_templates()
    tpl_ids = {t.id for t in templates}
    assert "calling_channels" in tpl_ids
    assert "noaa_wx_channels" in tpl_ids

    # Check template channels and legacy alias resolution
    calling_chans = tpl_mgr.get_template_channels("calling_channels")
    assert len(calling_chans) >= 6
    legacy_calling = tpl_mgr.get_template_channels("builtin_calling_channels")
    assert len(legacy_calling) == len(calling_chans)

    wx_chans = tpl_mgr.get_template_channels("noaa_wx_channels")
    assert len(wx_chans) == 7
    assert tpl_mgr.has_template("builtin_noaa_wx_channels")

    # App template is initially not a user template
    assert not tpl_mgr.is_user_template("calling_channels")

    # Copy to user directory for customization
    tpl_mgr.copy_to_user_directory("calling_channels")
    assert tpl_mgr.is_user_template("calling_channels")
    user_file = tpl_dir / "calling_channels.yaml"
    assert user_file.is_file()

    # Modify user template to verify precedence
    overridden = tpl_mgr.get_template("calling_channels")
    updated = overridden.model_copy(update={"name": "Customized Calling Channels"})
    tpl_mgr.save_template(updated)
    assert tpl_mgr.get_template("calling_channels").name == "Customized Calling Channels"

    # Delete user template override; app default is restored
    assert tpl_mgr.delete_user_template("calling_channels") is True
    assert not tpl_mgr.is_user_template("calling_channels")
    assert tpl_mgr.has_template("calling_channels")
    assert tpl_mgr.get_template("calling_channels").name == "National Calling Frequencies"

    # Add new custom YAML template with structured channels
    custom_tpl = PresetTemplateFile(
        id="sar_ops",
        name="SAR Operations",
        description="Search and Rescue operations frequencies",
        tagText="SAR",
        tagColorHex="#FF9800",
        channels=[
            TemplateChannelItem(
                name="SAR_1",
                rxFreq=155.160,
                txFreq=155.160,
                mode="FM",
                power="High",
                comment="Search and Rescue primary",
            )
        ],
    )
    tpl_mgr.save_template(custom_tpl)
    assert tpl_mgr.is_user_template("sar_ops")
    assert (tpl_dir / "sar_ops.yaml").is_file()

    # Reload and verify
    tpl_mgr.reload()
    sar_retrieved = tpl_mgr.get_template("sar_ops")
    assert sar_retrieved.name == "SAR Operations"
    sar_chans = tpl_mgr.get_template_channels("sar_ops")
    assert len(sar_chans) == 1
    assert sar_chans[0].name == "SAR_1"
    assert sar_chans[0].rxFreq == 155.160
    assert sar_chans[0].specialType == "CUSTOM"

    # Delete custom template
    assert tpl_mgr.delete_user_template("sar_ops") is True
    assert not tpl_mgr.has_template("sar_ops")
    assert not (tpl_dir / "sar_ops.yaml").is_file()


def test_template_migration_from_raw_csv(tmp_path: Path):
    """Verify PresetTemplateFile automatically parses legacy CSV rows into structured channels."""
    csv_text = "Name,Frequency,Mode,Power,Comment\nARES_PRI,146.550,FM,High,ARES Primary\n"
    tpl = PresetTemplateFile(
        id="ares_net",
        name="ARES Net",
        rawCsvContent=csv_text,
    )
    assert len(tpl.channels) == 1
    assert tpl.channels[0].name == "ARES_PRI"
    assert tpl.channels[0].rxFreq == 146.550

    mgr = TemplateManager(custom_templates_dir=tmp_path / "tpls")
    saved_path = mgr.save_template(tpl)
    assert saved_path.suffix == ".yaml"
    assert saved_path.is_file()

    mgr.reload()
    loaded = mgr.get_template("ares_net")
    assert len(loaded.channels) == 1
    assert loaded.channels[0].name == "ARES_PRI"




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
