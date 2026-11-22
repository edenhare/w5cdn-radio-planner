"""Optional full-browser Playwright E2E & axe-core WCAG 2.1 AA test suite.

Run locally with:
    uv run --group dev --group ui pytest tests/web/test_ui_e2e.py --no-cov -v

Skipped automatically when Playwright is not installed (e.g., standard unit-test runs).
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn

sync_api = pytest.importorskip("playwright.sync_api")

from core.models.preferences import VALID_COCKPIT_THEMES  # noqa: E402
from web import app as web_app  # noqa: E402
from web.state import workspace  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Local server did not start on port {port}")


def _launch_headless_browser(playwright: sync_api.Playwright) -> sync_api.Browser:
    for channel in ("msedge", "chrome", None):
        try:
            if channel:
                return playwright.chromium.launch(headless=True, channel=channel)
            return playwright.chromium.launch(headless=True)
        except sync_api.Error:
            continue
    pytest.skip("No Chromium/Edge/Chrome browser available for Playwright E2E tests")


@pytest.fixture
def live_radioplanner_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("RADIOPLANNER_HOME", str(tmp_path / "rp_home"))
    workspace.reload_all()
    workspace.session = workspace.session.__class__()

    def mock_lookup_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "callook.info" and "/W5CDN/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "status": "VALID",
                    "name": "HARE, EDEN",
                    "current": {"callsign": "W5CDN", "operClass": "EXTRA"},
                    "address": {"line2": "TYLER, TX 75701"},
                    "location": {"gridsquare": "EM22"},
                },
            )
        return httpx.Response(200, json={"status": "INVALID"})

    def mock_nws_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "properties": {
                            "id": "rp-alert-1",
                            "event": "Severe Thunderstorm Watch",
                            "severity": "Severe",
                            "headline": "Severe Thunderstorm Watch for Smith County, TX",
                            "areaDesc": "Smith, TX; Caddo, LA",
                            "description": "Isolated severe storms along I-20 corridor.",
                            "expires": "2026-11-22T23:00:00Z",
                        }
                    }
                ]
            },
        )

    workspace.lookup_service._client = httpx.AsyncClient(transport=httpx.MockTransport(mock_lookup_handler))
    workspace.nws_service._client = httpx.AsyncClient(transport=httpx.MockTransport(mock_nws_handler))

    async def _mock_update_check(**kwargs):
        return {
            "online": True,
            "repo": "edenhare/w5cdn-radio-planner",
            "install_mode": "git",
            "current_version": web_app.APP_VERSION,
            "latest_version": web_app.APP_VERSION,
            "update_available": False,
            "can_self_update": True,
            "release_name": "",
            "release_url": "https://github.com/edenhare/w5cdn-radio-planner/releases",
            "published_at": "",
            "release_notes": "",
            "asset_name": "",
            "asset_url": "",
            "checksum_url": "",
            "message": f"W5CDN RadioPlanner {web_app.APP_VERSION} is up to date.",
        }

    monkeypatch.setattr(web_app, "check_for_update", _mock_update_check)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(web_app.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_ready(port)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=3.0)


@pytest.mark.ui
def test_ui_e2e_cockpit_workflows_and_all_modals(live_radioplanner_server: str) -> None:
    """Exercise plan assembly, radio switching, inline edit, delete/undo, pocket card, NWS alerts & preferences."""
    page_errors: list[str] = []
    console_errors: list[str] = []

    with sync_api.sync_playwright() as p:
        browser = _launch_headless_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        # Block external map tiles so the test stays 100% local/offline
        page.route("https://**", lambda route: route.abort())

        page.goto(live_radioplanner_server, wait_until="domcontentloaded")
        page.wait_for_selector("#btnAssemblePlan")
        assert "W5CDN RadioPlanner" in page.title()

        # 1. Assemble default Route Corridor plan
        page.click("#btnAssemblePlan")
        page.wait_for_selector("#channelsTbody tr[data-slot]", timeout=15000)
        initial_rows = page.locator("#channelsTbody tr[data-slot]").count()
        assert initial_rows > 5

        # 2. Inline Channel Editor
        page.locator("#channelsTbody tr[data-slot] [data-row-action='edit']").first.click()
        page.wait_for_selector("#editChannelBackdrop:not(.hidden)")
        page.fill("#editChName", "E2ETST")
        page.click("#editChannelForm button[type='submit']")
        page.wait_for_selector("#editChannelBackdrop", state="hidden")
        assert "E2ETST" in page.locator("#channelsTbody").inner_text()

        # 3. Delete first channel & Undo
        page.locator("#channelsTbody tr[data-slot] [data-row-action='delete']").first.click()
        page.wait_for_function(
            f"() => document.querySelectorAll('#channelsTbody tr[data-slot]').length === {initial_rows - 1}"
        )
        page.click("#btnUndoDelete")
        page.wait_for_function(
            f"() => document.querySelectorAll('#channelsTbody tr[data-slot]').length === {initial_rows}"
        )

        # 4. Pocket Reference Card modal
        page.click("#btnPlanReport")
        page.wait_for_selector("#planReportBackdrop:not(.hidden)")
        assert "RADIOPLANNER CODEPLUG REFERENCE CARD" in page.locator("#planReportText").input_value()
        page.click("#planReportBackdrop [data-close-modal='planReportBackdrop']")

        # 5. NWS Area Weather Alerts modal
        page.click("#btnPlanWeather")
        page.wait_for_selector("#nwsAlertsBackdrop:not(.hidden)")
        page.wait_for_selector(".nws-alert-card", timeout=10000)
        assert "Severe Thunderstorm Watch" in page.locator("#nwsAlertsList").inner_text()
        page.click("#nwsAlertsBackdrop [data-close-modal='nwsAlertsBackdrop']")

        # 6. Preferences modal — Operator callsign lookup + System tab
        page.click("#btnOpenPrefs")
        page.wait_for_selector("#prefsModalBackdrop:not(.hidden)")
        page.click("[data-pref-tab='operator']")
        page.fill("#prefCallsign", "W5CDN")
        page.click("#btnPrefLookupCall")
        page.wait_for_function("() => document.getElementById('prefOperatorName').value.includes('Eden')")
        page.click("[data-pref-tab='system']")
        assert page.locator("#btnDownloadBackup").is_visible()
        assert page.locator("#btnCheckUpdate").is_visible()
        page.click("#btnCancelPrefs")

        browser.close()

    assert not page_errors, f"Uncaught JS page errors: {page_errors}"
    assert not console_errors, f"Console errors: {console_errors}"


@pytest.mark.ui
def test_ui_wcag_accessibility_across_all_9_themes(live_radioplanner_server: str) -> None:
    """Verify zero critical/serious axe-core WCAG 2.1 AA violations across all 9 Cockpit themes."""
    axe_mod = pytest.importorskip("axe_playwright_python.sync_playwright")
    axe = axe_mod.Axe()

    with sync_api.sync_playwright() as p:
        browser = _launch_headless_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.route("https://**", lambda route: route.abort())
        page.goto(live_radioplanner_server, wait_until="domcontentloaded")
        page.wait_for_selector("#btnAssemblePlan")

        for theme in VALID_COCKPIT_THEMES:
            page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
            results = axe.run(page, options={"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21aa"]}})
            violations = results.response.get("violations", [])
            severe = [v for v in violations if v.get("impact") in {"critical", "serious"}]
            assert not severe, f"WCAG serious/critical violations in theme '{theme}': {severe}"

        browser.close()
