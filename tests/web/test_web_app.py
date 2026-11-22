"""End-to-end REST API & Cockpit Studio tests for RadioPlanner."""

from __future__ import annotations

import csv
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config.recipe import CorridorConfig, RadioPlannerRecipe, RadioTargetConfig
from core.exporters.chirp import CHIRP_COLUMNS
from core.managers.preferences_manager import PreferencesManager
from core.managers.radio_manager import RadioManager
from core.managers.template_manager import APP_TEMPLATES_DIR, TemplateManager
from web.app import app
from web.state import workspace

client = TestClient(app)


def test_cockpit_shell_and_bootstrap_config():
    """Verify SPA index.html, favicon, and /api/config default cockpit layout."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "RadioPlanner — Cockpit Studio" in res_index.text
    assert "/static/styles.css" in res_index.text
    assert "/static/app.js" in res_index.text

    res_icon = client.get("/favicon.ico")
    assert res_icon.status_code == 200

    res_cfg = client.get("/api/config")
    assert res_cfg.status_code == 200
    cfg = res_cfg.json()
    assert cfg["app_title"] == "W5CDN RadioPlanner"
    assert cfg["install_mode"] in {"git", "source", "standalone"}
    assert len(cfg["radios"]) >= 5
    assert len(cfg["templates"]) >= 3

    layout = cfg["preferences"]["panel_layout"]
    assert layout["builder"] == {"visible": True, "position": "left"}
    assert layout["map"] == {"visible": True, "position": "right"}
    assert layout["summary"] == {"visible": True, "position": "right"}


def test_corridor_plan_live_retarget_edit_delete_undo_report_and_chirp_export():
    """Verify corridor plan generation, live target switch, inline edit, delete + undo, pocket card report, and CHIRP CSV export."""
    res = client.post(
        "/api/plan/generate",
        json={
            "mode": "ROUTE_CORRIDOR",
            "waypoints": ["Tyler, TX", "Shreveport, LA"],
            "corridor_width": 25.0,
            "include_simplex": True,
            "sequence_order": [
                "TEMPLATE:calling_channels",
                "ROUTE_PLAN",
                "TEMPLATE:noaa_wx_channels",
            ],
            "radio_id": "anytone_at778uv",
            "bands": ["2m", "70cm", "WX"],
            "repeater_access": ["OPEN"],
            "naming_format": "CITY_FREQ",
        },
    )
    assert res.status_code == 200
    plan = res.json()
    assert plan["active"] is True
    assert plan["radio_spec"]["id"] == "anytone_at778uv"
    assert plan["codeplug"]["total_channels"] > 5
    assert plan["can_undo"] is False

    # Switch to AnyTone AT-778UV (5-char LCD) -> smart default selects CALLSIGN & startChannel 0
    res_upd = client.post(
        "/api/codeplug/update",
        json={"radio_id": "anytone_at778uv", "radio_changed": True},
    )
    assert res_upd.status_code == 200
    upd = res_upd.json()
    assert upd["recipe"]["radio_target"]["naming_format"] == "CALLSIGN"
    assert upd["codeplug"]["channels"][0]["number"] == 0

    # Switch to BTECH DMR-6X2 (16-char LCD) -> smart default selects CITY_FREQ, then switch back
    res_btech = client.post(
        "/api/codeplug/update",
        json={"radio_id": "btech_dmr6x2", "radio_changed": True},
    )
    assert res_btech.status_code == 200
    assert res_btech.json()["recipe"]["radio_target"]["naming_format"] == "CITY_FREQ"

    back = client.post(
        "/api/codeplug/update",
        json={"radio_id": "anytone_at778uv", "radio_changed": True},
    ).json()
    orig_count = back["codeplug"]["total_channels"]

    # Inline Channel Editor: edit slot #0 (LCD name clamped to 5 chars on AT-778UV, + offset & Tone)
    res_edit = client.patch(
        "/api/codeplug/channels/0",
        json={
            "name": "MYCUSTOMLONG",
            "callsign": "w5cdn",
            "rxFreq": 146.94,
            "offsetDir": "-",
            "offset": 0.6,
            "mode": "FM",
            "power": "Mid",
            "toneMode": "Tone",
            "ctcss": "136.5",
            "city": "Tyler",
            "state": "tx",
            "comment": "Primary ARES",
        },
    )
    assert res_edit.status_code == 200
    edited_plan = res_edit.json()
    ch0 = edited_plan["codeplug"]["channels"][0]
    assert ch0["name"] == "MYCUS"
    assert len(ch0["name"]) <= 5
    assert ch0["callsign"] == "W5CDN"
    assert ch0["txFreq"] == pytest.approx(146.34, abs=1e-4)
    assert ch0["toneMode"] == "Tone"
    assert ch0["ctcss"] == "136.5"
    assert edited_plan["can_undo"] is True

    # Delete slots 0 and 1, verify renumbering & undo stack
    res_del = client.post("/api/codeplug/delete-channels", json={"slots": [0, 1]})
    assert res_del.status_code == 200
    after_del = res_del.json()
    assert after_del["codeplug"]["total_channels"] == orig_count - 2
    assert after_del["can_undo"] is True
    assert after_del["undo_count"] == 2

    # Undo Delete -> restores the 2 deleted channels including our edited slot #0
    res_undo = client.post("/api/codeplug/undo-delete")
    assert res_undo.status_code == 200
    restored = res_undo.json()
    assert restored["codeplug"]["total_channels"] == orig_count
    assert restored["codeplug"]["channels"][0]["name"] == "MYCUS"

    # Printable Pocket Reference Card / Plan Report Modal payload
    res_report = client.get("/api/codeplug/report")
    assert res_report.status_code == 200
    report = res_report.json()
    assert "RADIOPLANNER CODEPLUG REFERENCE CARD" in report["text"]
    assert "MYCUS" in report["text"]
    assert report["kpis"]["total_channels"] == orig_count
    assert report["filename"].endswith("_pocket_card.txt")

    # Export CHIRP CSV and verify 21 official columns, slot 0 start, and <= 5 char LCD names
    res_csv = client.post(
        "/api/codeplug/export",
        json={"programmer_type": "CHIRP", "filename": "web_test_at778uv.csv"},
    )
    assert res_csv.status_code == 200
    rows = list(csv.reader(io.StringIO(res_csv.text)))
    assert rows[0] == CHIRP_COLUMNS
    assert rows[1][0] == "0"
    for row in rows[1:]:
        assert len(row[1]) <= 5
        assert 50.0 < float(row[6]) < 300.0


def test_aviation_proximity_gmrs_and_geolocate():
    """Verify Aviation, Proximity, GMRS standard channels, and /api/geolocate endpoints."""
    res_air = client.post(
        "/api/plan/generate",
        json={
            "mode": "AVIATION_PLANNER",
            "center_location": "Tyler, TX",
            "radius_miles": 35.0,
            "sequence_order": ["AVIATION_BLOCK", "TEMPLATE:noaa_wx_channels"],
            "radio_id": "alinco_dr735t",
            "naming_format": "IDENT_TYPE",
        },
    )
    assert res_air.status_code == 200
    air_data = res_air.json()
    assert air_data["summary"]["title"] == "Airfields Within Range"
    names = {ch["name"] for ch in air_data["codeplug"]["channels"]}
    assert "KTYRAT" in names
    assert "KTYRCT" in names

    # Radio without Airband triggers warning notice
    res_air_warn = client.post(
        "/api/plan/generate",
        json={
            "mode": "AVIATION_PLANNER",
            "center_location": "Tyler, TX",
            "radius_miles": 35.0,
            "sequence_order": ["AVIATION_BLOCK"],
            "radio_id": "anytone_at778uv",
            "naming_format": "IDENT_ONLY",
        },
    )
    assert res_air_warn.status_code == 200
    assert any("Airband" in n["message"] for n in res_air_warn.json()["notices"])

    # Proximity Search
    res_prox = client.post(
        "/api/plan/generate",
        json={
            "mode": "PROXIMITY_SEARCH",
            "center_location": "Dallas, TX",
            "radius_miles": 50.0,
            "include_simplex": True,
            "sequence_order": ["PROXIMITY_PLAN"],
            "radio_id": "baofeng_5rm",
            "bands": ["2m", "70cm"],
            "repeater_access": ["OPEN"],
            "naming_format": "CITY_FREQ",
        },
    )
    assert res_prox.status_code == 200
    assert res_prox.json()["summary"]["title"] == "Concentric Proximity Rings"

    # GMRS radio includes 30 standard FCC channels + regional repeaters
    res_gmrs = client.post(
        "/api/plan/generate",
        json={
            "mode": "ROUTE_CORRIDOR",
            "waypoints": ["Tyler, TX", "Shreveport, LA"],
            "corridor_width": 25.0,
            "include_simplex": True,
            "radio_id": "baofeng_uv5g_plus",
        },
    )
    assert res_gmrs.status_code == 200
    gmrs_names = {ch["name"] for ch in res_gmrs.json()["codeplug"]["channels"]}
    assert "G01 FRS" in gmrs_names
    assert "G15R RPT" in gmrs_names

    # Geolocation reverse lookup
    res_geo = client.get("/api/geolocate?lat=32.3513&lon=-95.3011")
    assert res_geo.status_code == 200
    geo = res_geo.json()
    assert geo["ok"] is True
    assert "Tyler" in geo["location"] or "32.3513" in geo["location"]


def test_recipes_templates_radios_and_preferences_crud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify Recipes, Templates, Radios, and 9-Theme Preferences REST CRUD operations."""
    recipes_dir = tmp_path / "recipes"
    recipes_dir.mkdir()
    monkeypatch.setattr("web.app.get_recipes_dir", lambda: recipes_dir)

    saved = RadioPlannerRecipe(
        mode="ROUTE_CORRIDOR",
        name="Web_Saved_Corridor",
        description="East Texas to Mississippi corridor",
        corridor=CorridorConfig(waypoints=["Tyler, TX", "Jackson, MS"], corridor_width_miles=30.0),
        radio_target=RadioTargetConfig(radio_id="anytone_at778uv", bands=["2m"], naming_format="CALLSIGN"),
    )
    saved.to_yaml_file(recipes_dir / "web_saved.yaml")

    res_list = client.get("/api/recipes")
    assert res_list.status_code == 200
    assert any(r["filename"] == "web_saved.yaml" for r in res_list.json()["recipes"])

    res_get = client.get("/api/recipes/web_saved.yaml")
    assert res_get.status_code == 200
    assert res_get.json()["recipe"]["name"] == "Web_Saved_Corridor"

    res_del = client.delete("/api/recipes/web_saved.yaml")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True

    # Templates CRUD in isolated dir
    temp_app_dir = tmp_path / "core_templates"
    temp_user_dir = tmp_path / "user_templates"
    shutil.copytree(APP_TEMPLATES_DIR, temp_app_dir)
    monkeypatch.setattr(
        workspace,
        "template_mgr",
        TemplateManager(custom_templates_dir=temp_user_dir, app_templates_dir=temp_app_dir),
    )

    res_tpl = client.post(
        "/api/templates",
        json={
            "id": "east_tx_test",
            "name": "East TX Test",
            "tagText": "TEST",
            "tagColorHex": "#10b981",
            "description": "Custom test template",
            "channels": [
                {
                    "name": "ETX RPT",
                    "rxFreq": 146.96,
                    "offsetDir": "-",
                    "offset": 0.6,
                    "mode": "FM",
                    "power": "High",
                    "toneMode": "Tone",
                    "toneVal": "136.5",
                    "comment": "Tyler Repeater",
                }
            ],
        },
    )
    assert res_tpl.status_code == 200
    assert res_tpl.json()["saved"] is True
    assert client.delete("/api/templates/east_tx_test").status_code == 200
    assert client.delete("/api/templates/calling_channels").status_code == 400

    # Radios CRUD in isolated dir
    monkeypatch.setattr(workspace, "radio_mgr", RadioManager(user_radios_dir=tmp_path / "radios"))
    res_rad = client.post(
        "/api/radios",
        json={
            "id": "test_ht_900",
            "brand": "TestCorp",
            "model": "HT-900",
            "startChannel": 1,
            "maxChannels": 250,
            "maxNameLength": 10,
            "programmerType": "CHIRP",
            "supportedBands": ["2m", "70cm"],
            "supportedModes": ["FM"],
        },
    )
    assert res_rad.status_code == 200
    assert client.get("/api/radios/test_ht_900/naming-previews").status_code == 200
    assert client.delete("/api/radios/test_ht_900").status_code == 200

    # Preferences: 9-theme support, fonts, sliders, and 5-zone panel layout
    monkeypatch.setattr(
        workspace,
        "prefs_mgr",
        PreferencesManager(prefs_path=tmp_path / "preferences.yaml", tokens_path=tmp_path / "tokens"),
    )
    res_prefs = client.put(
        "/api/preferences",
        json={
            "callsign": "w5cdn",
            "operatorName": "Shack Op",
            "colorTheme": "amber-crt",
            "fontFamily": "humanist",
            "monoFont": "consolas",
            "uiFontSize": 16,
            "lcdFontSize": 18,
            "panelLayout": {
                "builder": {"visible": True, "position": "left"},
                "map": {"visible": True, "position": "top"},
                "summary": {"visible": False, "position": "right"},
            },
        },
    )
    assert res_prefs.status_code == 200
    prefs = res_prefs.json()["preferences"]
    assert prefs["callsign"] == "W5CDN"
    assert prefs["theme"] == "amber-crt"
    assert prefs["ui_font"] == "humanist"
    assert prefs["mono_font"] == "consolas"
    assert prefs["font_size"] == 16
    assert prefs["lcd_font_size"] == 18
    assert prefs["panel_layout"]["map"] == {"visible": True, "position": "top"}
    assert prefs["panel_layout"]["summary"]["visible"] is False


def test_bad_and_missing_api_requests():
    """Tri-state Bad & Empty data tests for error handling."""
    assert client.post("/api/plan/generate", json={"mode": "INVALID_MODE"}).status_code == 400
    assert client.post("/api/plan/generate", json={"mode": "ROUTE_CORRIDOR", "waypoints": ["OnlyOne, TX"]}).status_code == 400
    assert client.get("/api/recipes/does_not_exist.yaml").status_code == 404
    assert client.patch("/api/codeplug/channels/99999", json={"name": "NOPE"}).status_code == 404


def test_backup_restore_session_persistence_lookup_nws_and_net_logger_interop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify Backup/Restore zip, session persistence, Callsign lookup, NWS alerts, Net Logger interop & update API."""
    import json
    import zipfile

    import httpx

    from core.providers.callsign_lookup import CallsignLookupService
    from core.providers.nws import NwsAlertsService
    from web import app as web_app

    rp_home = tmp_path / "rp_home"
    monkeypatch.setenv("RADIOPLANNER_HOME", str(rp_home))
    workspace.reload_all()

    # 1. Persistent session save + reload roundtrip
    gen = client.post(
        "/api/plan/generate",
        json={
            "mode": "PROXIMITY_SEARCH",
            "center_location": "Dallas, TX",
            "radius_miles": 25.0,
            "radio_id": "anytone_at778uv",
        },
    )
    assert gen.status_code == 200
    assert (rp_home / "session.json").is_file()
    saved_count = gen.json()["codeplug"]["total_channels"]
    workspace.session = workspace.session.__class__()
    assert workspace.load_session() is True
    assert workspace.session.codeplug is not None
    assert workspace.session.codeplug.total_channels == saved_count

    # 2. Net Logger repeater preset export from slot 0
    nl_exp = client.get("/api/codeplug/channels/0/net-logger-preset")
    assert nl_exp.status_code == 200
    preset = nl_exp.json()["preset"]
    assert "frequency" in preset and "MHz" in preset["frequency"]
    assert "tone_offset" in preset

    # 3. Import W5CDN Net Logger net_type_defaults JSON into a Preset Template
    temp_app_dir = tmp_path / "core_tpl"
    temp_user_dir = tmp_path / "user_tpl"
    shutil.copytree(APP_TEMPLATES_DIR, temp_app_dir)
    monkeypatch.setattr(
        workspace,
        "template_mgr",
        TemplateManager(custom_templates_dir=temp_user_dir, app_templates_dir=temp_app_dir),
    )
    nl_json = json.dumps(
        {
            "net_type_defaults": {
                "Skywarn": {"frequency": "146.940 MHz", "mode": "FM", "tone_offset": "-0.600 / PL 136.5"},
                "Simplex": {"frequency": "146.520 MHz", "mode": "FM", "tone_offset": "Simplex"},
            }
        }
    )
    res_nl = client.post(
        "/api/templates/import-net-logger",
        json={"id": "w5cdn_nets", "name": "W5CDN Nets", "json_text": nl_json},
    )
    assert res_nl.status_code == 200
    assert res_nl.json()["imported"] is True
    assert any(t["id"] == "w5cdn_nets" and t["channelCount"] == 2 for t in res_nl.json()["templates"])

    # 4. Callsign Lookup (QRZ XML + Callook fallback mocked)
    def lookup_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "xmldata.qrz.com":
            if "username" in request.url.params:
                return httpx.Response(200, text="<QRZDatabase><Session><Key>abc123</Key></Session></QRZDatabase>")
            return httpx.Response(
                200,
                text=(
                    "<QRZDatabase><Callsign><call>W5CDN</call><fname>Eden</fname><name>Hare</name>"
                    "<addr2>Tyler</addr2><state>TX</state><grid>EM22</grid><class>E</class></Callsign></QRZDatabase>"
                ),
            )
        return httpx.Response(
            200,
            json={
                "status": "VALID",
                "name": "DOE, JANE",
                "current": {"callsign": "K5TST", "operClass": "GENERAL"},
                "address": {"line2": "DALLAS, TX 75201"},
                "location": {"gridsquare": "EM12"},
            },
        )

    monkeypatch.setattr(
        workspace,
        "lookup_service",
        CallsignLookupService(client=httpx.AsyncClient(transport=httpx.MockTransport(lookup_handler))),
    )
    r_callook = client.get("/api/lookup/K5TST")
    assert r_callook.status_code == 200
    assert r_callook.json()["found"] is True
    assert r_callook.json()["source"] == "callook"

    r_qrz_test = client.post(
        "/api/preferences/test-qrz",
        json={"qrzUsername": "W5CDN", "qrzPassword": "secret"},
    )
    assert r_qrz_test.status_code == 200
    assert r_qrz_test.json()["ok"] is True

    # 5. NWS Route/Area Weather Alerts (mocked)
    def nws_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "properties": {
                            "id": "wx-1",
                            "event": "Flood Watch",
                            "severity": "Moderate",
                            "headline": "Flood Watch in effect",
                            "areaDesc": "Smith, TX",
                            "description": "Heavy rainfall expected.",
                            "expires": "2026-11-23T00:00:00Z",
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        workspace,
        "nws_service",
        NwsAlertsService(client=httpx.AsyncClient(transport=httpx.MockTransport(nws_handler))),
    )
    r_nws = client.get("/api/nws/plan-alerts?states=TX,LA")
    assert r_nws.status_code == 200
    assert r_nws.json()["online"] is True
    assert r_nws.json()["count"] == 1
    assert "Flood Watch" in r_nws.json()["briefing_text"]

    # 6. Backup export & restore roundtrip
    client.put("/api/preferences", json={"callsign": "W5CDN", "colorTheme": "forest-eoc"})
    r_bak = client.get("/api/backup/export?include_tokens=false")
    assert r_bak.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r_bak.content), "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "preferences.yaml" in names
        assert "tokens" not in names

    client.put("/api/preferences", json={"callsign": "K0TMP", "colorTheme": "daylight"})
    r_res = client.post("/api/backup/restore", content=r_bak.content, headers={"Content-Type": "application/zip"})
    assert r_res.status_code == 200
    assert r_res.json()["restored"] is True
    assert r_res.json()["preferences"]["callsign"] == "W5CDN"
    assert r_res.json()["preferences"]["theme"] == "forest-eoc"

    # 7. Unload & Update check endpoints
    assert client.post("/api/client/unload").status_code == 200

    async def _fake_update(**kwargs):
        return {"online": True, "update_available": False, "current_version": web_app.APP_VERSION, "install_mode": "git"}

    monkeypatch.setattr(web_app, "check_for_update", _fake_update)
    r_upd = client.get("/api/update/check")
    assert r_upd.status_code == 200
    assert r_upd.json()["online"] is True
