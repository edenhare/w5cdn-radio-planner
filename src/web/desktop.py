"""Standalone desktop & chromeless app-window wrapper for W5CDN RadioPlanner."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from collections.abc import Sequence
from pathlib import Path

import httpx
import uvicorn

if __package__ in {None, ""}:
    _src_root = str(Path(__file__).resolve().parent.parent)
    if _src_root not in sys.path:
        sys.path.insert(0, _src_root)

from web.app import APP_TITLE, STATIC_DIR, app, parse_port, register_shutdown_callback
from web.state import workspace

logger = logging.getLogger("radioplanner.desktop")

APP_USER_MODEL_ID = "W5CDN.RadioPlanner"
ICON_ICO_PATH = STATIC_DIR / "icon.ico"


def _default_port() -> int:
    env_port = os.environ.get("RADIOPLANNER_PORT") or os.environ.get("PORT")
    if env_port:
        return parse_port(env_port, default=8000)
    saved = getattr(workspace.prefs_mgr.preferences, "webPort", 8000)
    return parse_port(str(saved), default=8000)


def set_windows_app_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """Assign a dedicated Windows AppUserModelID so the taskbar uses our custom app icon."""
    if sys.platform != "win32":
        return False
    try:
        shell32 = getattr(ctypes, "windll", None)
        if shell32 is None:
            return False
        shell32.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        return True
    except (AttributeError, OSError) as exc:
        logger.debug("Could not set Windows AppUserModelID: %s", exc)
        return False


def apply_windows_taskbar_icon(
    window_title: str,
    icon_path: Path = ICON_ICO_PATH,
) -> bool:
    """Apply static/icon.ico to a native Windows HWND for both title bar and taskbar."""
    if sys.platform != "win32" or not icon_path.is_file():
        return False
    try:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        user32 = windll.user32
        hwnd = user32.FindWindowW(None, window_title)
        if not hwnd:
            return False
        # IMAGE_ICON=1, LR_LOADFROMFILE=0x0010, WM_SETICON=0x0080, ICON_SMALL=0, ICON_BIG=1
        small_icon = user32.LoadImageW(None, str(icon_path), 1, 16, 16, 0x0010)
        big_icon = user32.LoadImageW(None, str(icon_path), 1, 48, 48, 0x0010)
        if small_icon:
            user32.SendMessageW(hwnd, 0x0080, 0, small_icon)
        if big_icon:
            user32.SendMessageW(hwnd, 0x0080, 1, big_icon)
        return bool(small_icon or big_icon)
    except (AttributeError, OSError) as exc:
        logger.debug("Could not apply Windows taskbar icon: %s", exc)
        return False


def find_available_port(host: str, preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, preferred_port))
            return int(sock.getsockname()[1])
        except OSError:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])


def wait_for_server(url: str, timeout_seconds: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url}/api/config", timeout=0.5)
            if resp.status_code == 200:
                return True
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("Waiting for local server at %s: %s", url, exc)
        time.sleep(0.1)
    return False


def find_chromium_app_browser(preferred: str | None = None) -> str | None:
    """Locate Google Chrome or Microsoft Edge for chromeless --app= window mode."""
    pref_raw = (preferred if preferred is not None else os.environ.get("APP_BROWSER", "")).strip()
    pref = pref_raw.lower()

    if pref and pref not in {"auto", "chrome", "edge"}:
        custom_path = Path(pref_raw)
        if custom_path.is_file():
            return str(custom_path)
        return shutil.which(pref_raw)

    chrome_names = (
        "chrome",
        "chrome.exe",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "brave-browser",
    )
    edge_names = ("msedge", "msedge.exe", "microsoft-edge", "microsoft-edge-stable")
    if pref == "chrome":
        names: tuple[str, ...] = chrome_names
    elif pref == "edge":
        names = edge_names
    else:
        names = edge_names + chrome_names

    for name in names:
        found = shutil.which(name)
        if found:
            return found

    if sys.platform == "win32":
        chrome_paths = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
        ]
        edge_paths = [
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
        ]
        if pref == "chrome":
            candidates = chrome_paths
        elif pref == "edge":
            candidates = edge_paths
        else:
            candidates = edge_paths + chrome_paths

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


class DesktopBridge:
    """JavaScript bridge exposed to the UI when running inside pywebview."""

    def __init__(self) -> None:
        self.window = None

    def save_text_file(self, filename: str, content: str, kind: str = "txt") -> dict[str, object]:
        if self.window is None:
            return {"saved": False, "error": "Desktop window not ready"}
        try:
            import webview

            dialog_type = getattr(getattr(webview, "FileDialog", None), "SAVE", None)
            if dialog_type is None:
                dialog_type = getattr(webview, "SAVE_DIALOG", 20)

            filters = {
                "csv": ("CSV Files (*.csv)", "All Files (*.*)"),
                "yaml": ("YAML Files (*.yaml;*.yml)", "All Files (*.*)"),
                "json": ("JSON Files (*.json)", "All Files (*.*)"),
                "txt": ("Text Files (*.txt)", "All Files (*.*)"),
            }.get(kind.lower(), ("All Files (*.*)",))

            result = self.window.create_file_dialog(
                dialog_type,
                save_filename=filename,
                file_types=filters,
            )
            if not result:
                return {"saved": False, "cancelled": True}

            target_path = Path(result[0] if isinstance(result, (list, tuple)) else str(result))
            target_path.write_text(content, encoding="utf-8")
            return {"saved": True, "path": str(target_path)}
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.error("Failed to save exported file %s: %s", filename, exc)
            return {"saved": False, "error": str(exc)}


def start_uvicorn_thread(host: str, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        timeout_graceful_shutdown=1.0,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    thread = threading.Thread(target=server.run, name="radioplanner-uvicorn", daemon=True)
    thread.start()
    return server, thread


def stop_uvicorn_server(
    server: uvicorn.Server,
    thread: threading.Thread,
    timeout: float = 2.0,
) -> None:
    """Stop the embedded Uvicorn server cleanly without hanging on keep-alive sockets."""
    register_shutdown_callback(None)
    server.should_exit = True
    thread.join(timeout=timeout)
    if thread.is_alive():
        server.force_exit = True
        thread.join(timeout=1.0)


def get_app_profile_dir() -> Path:
    """Return a writable Chromium app-mode profile directory (XDG cache on Linux for Snap safety)."""
    if sys.platform.startswith("linux"):
        xdg_cache = os.environ.get("XDG_CACHE_HOME", "").strip()
        base = Path(xdg_cache) if xdg_cache else Path.home() / ".cache"
        profile_dir = base / "radioplanner" / "browser-profile"
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.debug("Could not create XDG cache profile dir %s: %s", profile_dir, exc)
        return profile_dir
    return Path(tempfile.gettempdir()) / "w5cdn_radio_planner_app_profile"


def run_app_window_loop(
    url: str,
    server: uvicorn.Server,
    thread: threading.Thread,
    browser_exe: str | None = None,
    preferred_browser: str | None = None,
) -> bool:
    """Launch in a dedicated chromeless browser window (no tabs, no address bar)."""
    exe = browser_exe or find_chromium_app_browser(preferred_browser)
    if not exe:
        return False

    profile_dir = get_app_profile_dir()
    cmd = [
        exe,
        f"--app={url}",
        "--window-size=1440,920",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile_dir}",
    ]
    if sys.platform.startswith("linux"):
        cmd.append("--class=w5cdn-radio-planner")
    try:
        proc = subprocess.Popen(cmd)  # nosec B603
    except OSError as exc:
        logger.warning("Could not launch chromeless browser window (%s): %s", exe, exc)
        return False

    print(f"{APP_TITLE} running in chromeless app window ({exe}) at {url}")
    register_shutdown_callback(lambda: setattr(server, "should_exit", True))
    window_title = APP_TITLE
    icon_applied = False
    icon_deadline = time.monotonic() + 6.0
    try:
        while proc.poll() is None and thread.is_alive() and not server.should_exit:
            if not icon_applied and time.monotonic() < icon_deadline:
                icon_applied = apply_windows_taskbar_icon(window_title)
            time.sleep(0.3)
    except KeyboardInterrupt:
        proc.terminate()
    finally:
        stop_uvicorn_server(server, thread)
    return True


def run_browser_loop(url: str, server: uvicorn.Server, thread: threading.Thread) -> None:
    print(f"{APP_TITLE} running at {url} (closes automatically with window, or Ctrl+C)")
    register_shutdown_callback(lambda: setattr(server, "should_exit", True))
    webbrowser.open(url)
    try:
        while thread.is_alive() and not server.should_exit:
            time.sleep(0.4)
    except KeyboardInterrupt:
        pass
    finally:
        stop_uvicorn_server(server, thread)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument(
        "--app-window",
        action="store_true",
        help="Launch in a standalone chromeless Chrome/Edge window (no tabs or address bar)",
    )
    parser.add_argument(
        "--chrome",
        action="store_true",
        help="Launch in a standalone chromeless Google Chrome window (no tabs or address bar)",
    )
    parser.add_argument(
        "--app-browser",
        default="",
        help="Browser for chromeless app window: chrome, edge, auto, or path to executable",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in the default tabbed web browser instead of a standalone window",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable WebView2 developer tools",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_default_port(),
        help="Preferred localhost port (default: saved webPort or 8000)",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Start the local server, verify HTTP / and /api/config respond 200, and exit without opening a window",
    )
    parser.add_argument(
        "--smoke-test-out",
        default="",
        help="Optional JSON file path to write --smoke-test verification results",
    )
    return parser.parse_args(argv)


def run_smoke_test(url: str, out_path: str = "") -> bool:
    """Verify the running local server serves index.html and /api/config cleanly."""
    result: dict[str, object] = {
        "ok": False,
        "url": url,
        "index_status": 0,
        "config_status": 0,
        "version": "",
        "install_mode": "",
    }
    try:
        idx = httpx.get(f"{url}/", timeout=5.0)
        cfg = httpx.get(f"{url}/api/config", timeout=5.0)
        result["index_status"] = idx.status_code
        result["config_status"] = cfg.status_code
        cfg_json = cfg.json() if cfg.status_code == 200 else {}
        result["version"] = str(cfg_json.get("version") or "")
        result["install_mode"] = str(cfg_json.get("install_mode") or "")
        result["ok"] = (
            idx.status_code == 200
            and APP_TITLE in idx.text
            and cfg.status_code == 200
            and bool(result["version"])
            and bool(result["install_mode"])
        )
    except (httpx.HTTPError, ValueError, OSError) as exc:
        logger.error("Smoke test failed: %s", exc)
        result["ok"] = False

    payload = json.dumps(result, indent=2)
    if out_path:
        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(payload + "\n", encoding="utf-8")
    print(f"SMOKE_TEST_{'OK' if result['ok'] else 'FAILED'} {payload}")
    return bool(result["ok"])


def main(argv: Sequence[str] | None = None) -> int:
    set_windows_app_id()
    args = parse_args(argv)
    host = os.environ.get("HOST", "127.0.0.1")
    try:
        port = find_available_port(host, args.port)
    except OSError as exc:
        print(f"Error: Could not bind to local host {host}: {exc}", file=sys.stderr)
        return 1

    url = f"http://{host}:{port}"
    server, thread = start_uvicorn_thread(host, port)
    if not wait_for_server(url):
        stop_uvicorn_server(server, thread)
        print("Error: Local RadioPlanner backend failed to start.", file=sys.stderr)
        return 1

    if args.smoke_test:
        ok = run_smoke_test(url, out_path=args.smoke_test_out)
        stop_uvicorn_server(server, thread)
        return 0 if ok else 1

    preferred_browser = (
        "chrome"
        if args.chrome
        else (args.app_browser.strip() or os.environ.get("APP_BROWSER", "").strip())
    )
    use_app_window = args.app_window or args.chrome or (
        bool(preferred_browser) and preferred_browser.lower() != "auto" and not args.browser
    )

    if use_app_window:
        if run_app_window_loop(url, server, thread, preferred_browser=preferred_browser or None):
            return 0
        print(
            "Requested browser not found for chromeless app window; falling back to default browser.",
            file=sys.stderr,
        )
        run_browser_loop(url, server, thread)
        return 0

    if args.browser:
        run_browser_loop(url, server, thread)
        return 0

    try:
        import webview
    except ImportError:
        if run_app_window_loop(url, server, thread):
            return 0
        print(
            f"pywebview is not available; opening in browser at {url} (Ctrl+C to stop)",
            file=sys.stderr,
        )
        run_browser_loop(url, server, thread)
        return 0

    bridge = DesktopBridge()
    window_title = APP_TITLE
    try:
        window = webview.create_window(
            title=window_title,
            url=url,
            width=1440,
            height=920,
            min_size=(760, 560),
            background_color="#0b1017",
            js_api=bridge,
        )
        bridge.window = window
        events = getattr(window, "events", None)
        if events is not None:
            if hasattr(events, "closed"):
                events.closed += lambda: setattr(server, "should_exit", True)
            if hasattr(events, "shown"):
                events.shown += lambda: apply_windows_taskbar_icon(window_title)
            if hasattr(events, "loaded"):
                events.loaded += lambda: apply_windows_taskbar_icon(window_title)
        gui = "edgechromium" if sys.platform == "win32" else None
        webview.start(gui=gui, debug=args.debug)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("Desktop window failed: %s", exc)
        if sys.platform.startswith("linux"):
            print(
                f"pywebview failed on Linux ({exc}); falling back to browser app window.",
                file=sys.stderr,
            )
            if run_app_window_loop(url, server, thread):
                return 0
            run_browser_loop(url, server, thread)
            return 0
        print(f"Error: Desktop window failed to launch: {exc}", file=sys.stderr)
        stop_uvicorn_server(server, thread)
        return 1
    stop_uvicorn_server(server, thread)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
