"""Tests for web.desktop standalone wrapper, port binding, bridge, and smoke test."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from web import app as web_app
from web import desktop


def test_parse_args_and_port_helpers() -> None:
    assert web_app.parse_port("8765", default=8000) == 8765
    assert web_app.parse_port("0", default=8000) == 0
    assert web_app.parse_port("invalid", default=8000) == 8000
    assert web_app.parse_port("99999", default=8000) == 8000

    args = desktop.parse_args(["--app-window", "--port", "9012", "--smoke-test"])
    assert args.app_window is True
    assert args.port == 9012
    assert args.smoke_test is True

    port = desktop.find_available_port("127.0.0.1", 0)
    assert port > 0


def test_window_shutdown_manager_schedule_and_cancel() -> None:
    mgr = web_app.WindowShutdownManager(delay_seconds=0.05)
    fired = threading.Event()
    assert mgr.schedule() is False

    mgr.register(fired.set)
    assert mgr.schedule(delay_seconds=0.2) is True
    mgr.cancel()
    time.sleep(0.05)
    assert not fired.is_set()

    assert mgr.schedule(delay_seconds=0.03) is True
    assert fired.wait(timeout=1.0)
    mgr.register(None)


def test_desktop_bridge_save_text_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = desktop.DesktopBridge()
    assert bridge.save_text_file("test.csv", "a,b")["saved"] is False

    out_file = tmp_path / "codeplug.csv"
    fake_window = MagicMock()
    fake_window.create_file_dialog.return_value = [str(out_file)]
    bridge.window = fake_window

    fake_webview = MagicMock()
    fake_webview.FileDialog.SAVE = 20
    monkeypatch.setitem(__import__("sys").modules, "webview", fake_webview)

    res = bridge.save_text_file("codeplug.csv", "col1,col2\n1,2\n", "csv")
    assert res["saved"] is True
    assert out_file.read_text(encoding="utf-8") == "col1,col2\n1,2\n"

    fake_window.create_file_dialog.return_value = None
    cancelled = bridge.save_text_file("codeplug.csv", "x", "csv")
    assert cancelled["cancelled"] is True


def test_desktop_smoke_test_end_to_end(tmp_path: Path) -> None:
    out_json = tmp_path / "smoke.json"
    rc = desktop.main(["--smoke-test", "--smoke-test-out", str(out_json), "--port", "0"])
    assert rc == 0
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["index_status"] == 200
    assert data["config_status"] == 200
    assert data["version"] == web_app.APP_VERSION
    assert data["install_mode"] in {"git", "source", "standalone"}


def test_find_chromium_app_browser_custom_path(tmp_path: Path) -> None:
    fake_exe = tmp_path / "custom-browser.exe"
    fake_exe.write_text("", encoding="utf-8")
    assert desktop.find_chromium_app_browser(str(fake_exe)) == str(fake_exe)
    assert desktop.get_app_profile_dir().name in {"browser-profile", "w5cdn_radio_planner_app_profile"}
