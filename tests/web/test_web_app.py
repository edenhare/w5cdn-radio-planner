"""End-to-end tests for the FastAPI + HTMX Web Studio interface."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.recipe import CorridorConfig, RadioPlannerRecipe, RadioTargetConfig
from core.exporters.chirp import CHIRP_COLUMNS
from web.app import app

client = TestClient(app)


def test_web_planner_home_and_modes():
    """Verify main planner page loads as a radio-agnostic planner for Route Corridor, Proximity, and Aviation modes."""
    res_corridor = client.get("/?mode=ROUTE_CORRIDOR")
    assert res_corridor.status_code == 200
    assert "Mode 1: Highway Route Corridor" in res_corridor.text
    assert "Assemble Plan &amp; Map" in res_corridor.text

    res_prox = client.get("/?mode=PROXIMITY_SEARCH")
    assert res_prox.status_code == 200
    assert "Mode 2: Radial Proximity Rings" in res_prox.text

    res_air = client.get("/?mode=AVIATION_PLANNER")
    assert res_air.status_code == 200
    assert "Mode 3: Local Aviation" in res_air.text


def test_web_htmx_radio_options_live_preview():
    """Verify HTMX radio options endpoint returns supported bands and live LCD naming previews."""
    res = client.get("/htmx/radio-options?radio_id=anytone_at778uv&naming_format=CALLSIGN")
    assert res.status_code == 200
    assert "AnyTone AT-778UV" in res.text
    assert "Slots 0..126" in res.text
    assert "LCD Limit: 5 chars" in res.text
    assert "W5ETX" in res.text


def test_web_generate_corridor_plan_live_rename_and_chirp_export():
    """Verify generating a Route Corridor plan via HTMX, switching naming format/radio, and downloading CHIRP CSV."""
    form_data = [
        ("mode", "ROUTE_CORRIDOR"),
        ("waypoints", "Tyler, TX"),
        ("waypoints", "Shreveport, LA"),
        ("corridor_width", "25.0"),
        ("include_simplex", "true"),
        ("sequence_order", "TEMPLATE:calling_channels"),
        ("sequence_order", "ROUTE_PLAN"),
        ("sequence_order", "TEMPLATE:noaa_wx_channels"),
        ("radio_id", "anytone_at778uv"),
        ("bands", "2m"),
        ("bands", "70cm"),
        ("bands", "WX"),
        ("repeater_access", "OPEN"),
        ("naming_format", "CITY_FREQ"),
    ]
    res = client.post("/htmx/plan/generate", data=form_data)
    assert res.status_code == 200
    assert "Interactive Coverage &amp; Repeater Map" in res.text
    assert "Codeplug Channels:" in res.text
    assert "AnyTone AT-778UV" in res.text

    # Switch target radio in Codeplug View to AnyTone AT-778UV (5-char LCD) -> smart default selects CALLSIGN
    res_update = client.post(
        "/htmx/codeplug/update",
        data={"radio_id": "anytone_at778uv", "radio_changed": "true"},
    )
    assert res_update.status_code == 200
    assert "Naming: CALLSIGN" in res_update.text
    assert "Slots 0.." in res_update.text

    # Switch target radio to BTECH DMR-6X2 (16-char LCD) -> smart default selects CITY_FREQ, then switch back to AT-778UV
    res_btech = client.post(
        "/htmx/codeplug/update",
        data={"radio_id": "btech_dmr6x2", "radio_changed": "true"},
    )
    assert res_btech.status_code == 200
    assert "Naming: CITY_FREQ" in res_btech.text

    client.post(
        "/htmx/codeplug/update",
        data={"radio_id": "anytone_at778uv", "radio_changed": "true"},
    )

    # Open dedicated Codeplug View (/codeplug)
    res_cp_view = client.get("/codeplug")
    assert res_cp_view.status_code == 200
    assert "Expanded Codeplug Editor Window" in res_cp_view.text

    # Delete slots 0 and 1 via multi-select delete endpoint and verify renumbering from 0
    res_del = client.post(
        "/htmx/codeplug/delete-channels",
        data={"selected_slots": ["0", "1"], "is_standalone": "true"},
    )
    assert res_del.status_code == 200
    assert "Deleted 2 channel(s)" in res_del.text

    # Download CHIRP CSV and verify 21 official CHIRP columns and channel 0 start
    res_csv = client.post(
        "/export/csv",
        data={"programmer_type": "CHIRP", "filename": "web_test_at778uv.csv"},
    )
    assert res_csv.status_code == 200
    rows = list(csv.reader(io.StringIO(res_csv.text)))
    assert rows[0] == CHIRP_COLUMNS
    assert rows[1][0] == "0"
    for row in rows[1:]:
        assert len(row[1]) <= 5
        assert 50.0 < float(row[6]) < 300.0


def test_web_recipes_templates_radios_and_preferences_pages(tmp_path: Path, monkeypatch):
    """Verify Saved Recipes (including loading into planner), Templates, Radios, and Preferences pages."""
    monkeypatch.setattr("web.app.get_recipes_dir", lambda: tmp_path)

    saved = RadioPlannerRecipe(
        mode="ROUTE_CORRIDOR",
        name="Web_Saved_Corridor",
        description="Interstate corridor route from East Texas to Mississippi",
        corridor=CorridorConfig(waypoints=["Tyler, TX", "Jackson, MS"], corridor_width_miles=30.0),
        radio_target=RadioTargetConfig(
            radio_id="anytone_at778uv",
            bands=["2m"],
            naming_format="CALLSIGN",
        ),
    )
    saved_path = tmp_path / "web_saved.yaml"
    saved.to_yaml_file(saved_path)

    # Verify saved YAML on disk is radio-agnostic (no radio_id stored) and preserves description
    raw_yaml = saved_path.read_text(encoding="utf-8")
    assert "radio_id" not in raw_yaml
    assert "Interstate corridor route from East Texas to Mississippi" in raw_yaml

    res_recipes = client.get("/recipes")
    assert res_recipes.status_code == 200
    assert "Web_Saved_Corridor" in res_recipes.text
    assert "Interstate corridor route from East Texas to Mississippi" in res_recipes.text
    assert "Target Radio:" not in res_recipes.text

    # Load saved recipe into planner for interactive verification
    res_load = client.get("/?recipe_file=web_saved.yaml")
    assert res_load.status_code == 200
    assert "Loaded Saved Recipe:" in res_load.text
    assert "web_saved.yaml" in res_load.text
    assert "Jackson, MS" in res_load.text

    assert client.get("/templates").status_code == 200
    assert client.get("/radios").status_code == 200
    assert client.get("/preferences").status_code == 200


def test_web_preferences_save_theme_font_and_font_size(tmp_path: Path, monkeypatch):
    """Verify changing and saving UI Color Theme, Font Family, and Font Size from Preferences UI."""
    from core.managers.preferences_manager import PreferencesManager
    from web.state import workspace

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    monkeypatch.setattr(workspace, "prefs_mgr", PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file))

    res = client.post(
        "/preferences/save",
        data={
            "callsign": "W5ETX",
            "operator_name": "Test Op",
            "primary_dmr_id": "3148001",
            "default_radio_id": "anytone_at778uv",
            "channel_naming_format": "CALLSIGN",
            "distance_unit": "MILES",
            "repeater_max_age_days": "30",
            "web_port": "8080",
            "color_theme": "LIGHT",
            "font_family": "MONO",
            "font_size": "LARGE",
            "repeaterbook_api_key": "",
            "radioid_username": "",
            "radioid_api_key": "",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert workspace.prefs_mgr.preferences.colorTheme == "LIGHT"
    assert workspace.prefs_mgr.preferences.fontFamily == "MONO"
    assert workspace.prefs_mgr.preferences.fontSize == "LARGE"
    assert workspace.prefs_mgr.preferences.webPort == 8080

    # Verify root <html> attributes reflect saved appearance settings
    assert 'data-theme="light"' in res.text
    assert 'data-font="mono"' in res.text
    assert 'data-font-size="large"' in res.text


def test_web_generate_aviation_and_proximity_plans():
    """Verify Aviation Planner and Proximity Search HTMX generation and hardware notice banners."""
    res_air = client.post(
        "/htmx/plan/generate",
        data={
            "mode": "AVIATION_PLANNER",
            "center_location": "Tyler, TX",
            "radius_miles": "35.0",
            "sequence_order": ["AVIATION_BLOCK", "TEMPLATE:noaa_wx_channels"],
            "radio_id": "alinco_dr735t",
            "naming_format": "IDENT_TYPE",
        },
    )
    assert res_air.status_code == 200
    assert "Airfields Within Range" in res_air.text
    assert "KTYRAT" in res_air.text
    assert "KTYRCT" in res_air.text

    # Also test Aviation Planner with a radio that does not natively list Airband (shows warning notice)
    res_air_warn = client.post(
        "/htmx/plan/generate",
        data={
            "mode": "AVIATION_PLANNER",
            "center_location": "Tyler, TX",
            "radius_miles": "35.0",
            "sequence_order": ["AVIATION_BLOCK"],
            "radio_id": "anytone_at778uv",
            "naming_format": "IDENT_ONLY",
        },
    )
    assert res_air_warn.status_code == 200
    assert "does not list &#39;Airband&#39;" in res_air_warn.text or "does not list 'Airband'" in res_air_warn.text
    assert "KTYR" in res_air_warn.text

    # Test Proximity Search generation
    res_prox = client.post(
        "/htmx/plan/generate",
        data={
            "mode": "PROXIMITY_SEARCH",
            "center_location": "Dallas, TX",
            "radius_miles": "50.0",
            "include_simplex": "true",
            "sequence_order": ["PROXIMITY_PLAN"],
            "radio_id": "baofeng_5rm",
            "bands": ["2m", "70cm"],
            "repeater_access": ["OPEN"],
            "naming_format": "CITY_FREQ",
        },
    )
    assert res_prox.status_code == 200
    assert "Concentric Proximity Rings" in res_prox.text

    # Test /api/geolocate with GPS coordinates (reverse geocodes to Tyler, TX)
    res_geo = client.get("/api/geolocate?lat=32.3513&lon=-95.3011")
    assert res_geo.status_code == 200
    data = res_geo.json()
    assert data["ok"] is True
    assert "Tyler" in data["location"] or "32.3513" in data["location"]


def test_web_template_editor_save_core_template(tmp_path: Path, monkeypatch):
    """Verify inline template spreadsheet editor saves edits directly to core template YAML files."""
    import shutil

    from core.managers.template_manager import APP_TEMPLATES_DIR, TemplateManager
    from web.state import workspace

    temp_app_dir = tmp_path / "core_templates"
    temp_user_dir = tmp_path / "user_templates"
    shutil.copytree(APP_TEMPLATES_DIR, temp_app_dir)

    test_tpl_mgr = TemplateManager(custom_templates_dir=temp_user_dir, app_templates_dir=temp_app_dir)
    monkeypatch.setattr(workspace, "template_mgr", test_tpl_mgr)

    # Save edited core template (calling_channels) with modified rows and a repeater row
    res_save = client.post(
        "/templates/save",
        data={
            "tpl_id": "calling_channels",
            "name": "National Calling & Tactical",
            "tag_text": "CALLING",
            "tag_color_hex": "#00BCD4",
            "description": "Updated core calling channels",
            "ch_name": ["2m CALL", "70cm CALL", "ETX RPT"],
            "ch_rx_freq": ["146.52000", "446.00000", "146.96000"],
            "ch_offset_dir": ["off", "off", "-"],
            "ch_offset": ["0.000", "0.000", "0.600"],
            "ch_mode": ["FM", "FM", "FM"],
            "ch_power": ["High", "High", "High"],
            "ch_tone_mode": ["None", "None", "Tone"],
            "ch_tone_val": ["None", "None", "136.5"],
            "ch_comment": ["2m Simplex", "70cm Simplex", "Tyler Repeater"],
        },
        follow_redirects=True,
    )
    assert res_save.status_code == 200
    assert "Saved 3 channels to core template calling_channels.yaml" in res_save.text

    # Verify the core YAML file in app_dir was updated directly
    updated_core = test_tpl_mgr.get_template("calling_channels")
    assert updated_core.name == "National Calling & Tactical"
    assert len(updated_core.channels) == 3
    assert updated_core.channels[2].name == "ETX RPT"
    assert updated_core.channels[2].rxFreq == 146.96
    assert updated_core.channels[2].txFreq == 146.36
    assert updated_core.channels[2].offsetDir == "-"
    assert updated_core.channels[2].toneMode == "Tone"
    assert updated_core.channels[2].ctcss == "136.5"
    assert (temp_app_dir / "calling_channels.yaml").is_file()
    assert not (temp_user_dir / "calling_channels.yaml").exists()


def test_web_gmrs_radio_standard_channels_and_repeaters():
    """Verify GMRS radios include the 30 standard FCC GMRS channels (Ch 1-22 & 15R-22R) plus regional GMRS repeaters."""
    from web.state import workspace

    workspace.template_mgr.reload()
    gmrs_tpl = workspace.template_mgr.get_template("gmrs_channels")
    assert len(gmrs_tpl.channels) == 30

    # Generate Route Corridor plan and switch to Baofeng UV-5G Plus GMRS radio
    res = client.post(
        "/htmx/plan/generate",
        data={
            "mode": "ROUTE_CORRIDOR",
            "waypoints": ["Tyler, TX", "Shreveport, LA"],
            "corridor_width": "25.0",
            "include_simplex": "true",
            "radio_id": "baofeng_uv5g_plus",
        },
    )
    assert res.status_code == 200
    assert "Baofeng UV-5G Plus GMRS" in res.text
    assert "G01 FRS" in res.text
    assert "G08 PORT" in res.text
    assert "G15 GMRS" in res.text
    assert "G20 EMER" in res.text
    assert "G15R RPT" in res.text
    assert "G20R EMG" in res.text
    # Regional GMRS repeaters along Tyler -> Shreveport I-20 corridor are also present
    assert "WRTX675" in res.text or "Tyler 2.68" in res.text
    assert "WRSH675" in res.text or "Shreve 2.68" in res.text





