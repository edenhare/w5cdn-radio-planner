"""Self-update engine for W5CDN RadioPlanner (supports both Git/source and Standalone bundles).

Ported directly from w5cdn-net-logger/src/net_logger/updater.py.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("radioplanner.updater")

DEFAULT_UPDATE_REPO = "edenhare/w5cdn-radio-planner"
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")

ALLOWED_DOWNLOAD_HOSTS: set[str] = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "codeload.github.com",
}

MAX_UPDATE_ARCHIVE_BYTES = 250 * 1024 * 1024
MAX_UPDATE_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_UPDATE_FILES = 20000

InstallMode = Literal["standalone", "git", "source"]

UPDATE_ERROR_MESSAGES: dict[str, str] = {
    "untrusted_url": "Update download URL is not on an allowed GitHub host.",
    "git_missing": "Git is not installed or not on PATH; cannot apply source update automatically.",
    "git_branch_unknown": "Could not determine the active Git branch.",
    "git_non_main": "Self-update only updates the 'main' or 'master' branch. Switch to main first.",
    "git_status_failed": "Could not check Git working tree status.",
    "git_dirty": "Local uncommitted changes detected. Commit or stash your changes before updating.",
    "git_fetch_failed": "Could not fetch updates from origin. Check network connectivity.",
    "git_pull_failed": "Could not fast-forward local branch from origin.",
    "archive_too_many_files": "Update archive contains too many files.",
    "archive_unsafe_path": "Update archive contains an unsafe file path.",
    "archive_too_large": "Update archive exceeds uncompressed size limit.",
    "archive_escape": "Update archive entry escapes staging directory.",
    "archive_invalid_name": "Invalid standalone update archive filename.",
    "archive_corrupt": "Update archive is corrupted or not a valid ZIP file.",
    "checksum_missing": "Matching SHA-256 checksum was not found in SHA256SUMS.txt.",
    "download_too_large": "Update archive exceeds maximum allowed download size.",
    "download_failed": "Failed to download update package from GitHub Releases.",
    "checksum_mismatch": "Update archive failed SHA-256 integrity verification and was discarded.",
}


class UpdateError(ValueError):
    """Structured update error backed by a static, user-safe reason code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(UPDATE_ERROR_MESSAGES.get(code, "Application update failed."))


def safe_error_message(exc: UpdateError) -> str:
    """Return a static, sanitized message for an UpdateError without leaking internals."""
    return UPDATE_ERROR_MESSAGES.get(exc.code, "Application update failed.")


def get_update_repo() -> str:
    configured = (os.environ.get("RADIOPLANNER_UPDATE_REPO") or "").strip()
    if configured and REPO_SLUG_RE.match(configured):
        return configured
    return DEFAULT_UPDATE_REPO


def detect_install_mode(data_dir: Path) -> InstallMode:
    """Detect whether the app runs as a PyInstaller standalone bundle, a Git clone, or plain source."""
    if getattr(sys, "frozen", False):
        return "standalone"
    if (data_dir / ".git").exists():
        return "git"
    return "source"


def parse_semver(raw: str) -> tuple[int, int, int]:
    """Parse a release tag or version string (e.g. 'v0.2.1') into (major, minor, patch)."""
    match = SEMVER_RE.match((raw or "").strip())
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_newer_version(latest: str, current: str) -> bool:
    latest_tuple = parse_semver(latest)
    current_tuple = parse_semver(current)
    return latest_tuple > (0, 0, 0) and latest_tuple > current_tuple


def validate_download_url(url: str) -> str:
    """Allow only HTTPS URLs hosted on official GitHub release domains."""
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_DOWNLOAD_HOSTS:
        raise UpdateError("untrusted_url")
    return cleaned


def select_release_asset(
    assets: list[dict[str, Any]],
    *,
    platform_name: str | None = None,
    machine: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Select the best matching OS standalone .zip asset and SHA256SUMS.txt asset."""
    plat = (platform_name or sys.platform).lower()
    arch = (machine or platform.machine() or "").lower()
    os_token = "windows" if plat == "win32" else ("macos" if plat == "darwin" else "linux")

    checksum_asset: dict[str, Any] | None = None
    exact_match: dict[str, Any] | None = None
    os_match: dict[str, Any] | None = None

    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        low = name.lower()
        if low == "sha256sums.txt":
            checksum_asset = item
            continue
        if not low.endswith(".zip") or os_token not in low:
            continue
        if arch and arch in low:
            exact_match = item
        elif os_match is None:
            os_match = item

    return (exact_match or os_match), checksum_asset


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse standard sha256sum output ('<64-hex>  <filename>') into {basename: hex}."""
    out: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest = parts[0].strip().lower()
        filename = Path(parts[1].strip().lstrip("*")).name
        if SHA256_HEX_RE.match(digest) and filename:
            out[filename] = digest
    return out


def verify_sha256(file_path: Path, expected_hex: str) -> bool:
    expected = (expected_hex or "").strip().lower()
    if not SHA256_HEX_RE.match(expected) or not file_path.is_file():
        return False
    hasher = hashlib.sha256()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower() == expected


def create_pre_update_backup(config_home: Path) -> Path | None:
    """Create a zip snapshot of RadioPlanner config directory before applying an update."""
    if not config_home.is_dir():
        return None
    backup_path = config_home / "radioplanner.pre_update.bak"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_name in ("preferences.yaml",):
            src = config_home / rel_name
            if src.is_file():
                zf.write(src, arcname=rel_name)
        for folder in ("recipes", "radios", "templates"):
            sub = config_home / folder
            if sub.is_dir():
                for fp in sorted(sub.glob("*.yaml")):
                    if fp.is_file():
                        zf.write(fp, arcname=f"{folder}/{fp.name}")
    return backup_path


async def check_for_update(
    *,
    current_version: str,
    data_dir: Path,
    client: httpx.AsyncClient | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Query GitHub Releases for the latest version without failing when offline."""
    target_repo = repo if (repo and REPO_SLUG_RE.match(repo)) else get_update_repo()
    install_mode = detect_install_mode(data_dir)
    releases_url = f"https://github.com/{target_repo}/releases"
    api_url = f"https://api.github.com/repos/{target_repo}/releases/latest"

    base_resp: dict[str, Any] = {
        "online": False,
        "repo": target_repo,
        "install_mode": install_mode,
        "current_version": current_version,
        "latest_version": current_version,
        "update_available": False,
        "can_self_update": install_mode in {"git", "standalone"},
        "release_name": "",
        "release_url": releases_url,
        "published_at": "",
        "release_notes": "",
        "asset_name": "",
        "asset_url": "",
        "checksum_url": "",
        "message": "",
    }

    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=httpx.Timeout(6.0, connect=4.0),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"W5CDN-RadioPlanner/{current_version}",
        },
        follow_redirects=True,
    )
    try:
        resp = await http.get(api_url)
        if resp.status_code == 404:
            base_resp["online"] = True
            base_resp["message"] = "Connected to GitHub, but no formal release tags (v*) have been published yet."
            return base_resp
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError, OSError) as exc:
        logger.info("GitHub update check unavailable (offline or unreachable): %s", exc)
        base_resp["message"] = "Could not reach GitHub Releases (offline or rate-limited)."
        return base_resp
    finally:
        if owns_client:
            await http.aclose()

    if not isinstance(data, dict):
        base_resp["message"] = "Unexpected response from GitHub Releases API."
        return base_resp

    tag = str(data.get("tag_name") or "").strip()
    latest_clean = tag.lstrip("vV") or current_version
    release_html_url = str(data.get("html_url") or releases_url).strip()
    if not release_html_url.startswith("https://github.com/"):
        release_html_url = releases_url

    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    asset, checksum = select_release_asset(assets)
    asset_name = str(asset.get("name") or "") if asset else ""
    asset_url = str(asset.get("browser_download_url") or "") if asset else ""
    checksum_url = str(checksum.get("browser_download_url") or "") if checksum else ""

    update_avail = is_newer_version(tag, current_version)
    can_auto = install_mode == "git" or (install_mode == "standalone" and bool(asset_url) and bool(checksum_url))

    msg = (
        f"Version {latest_clean} is available (currently running {current_version})."
        if update_avail
        else f"W5CDN RadioPlanner {current_version} is up to date."
    )

    base_resp.update(
        {
            "online": True,
            "latest_version": latest_clean,
            "update_available": update_avail,
            "can_self_update": can_auto,
            "release_name": str(data.get("name") or tag or latest_clean)[:120],
            "release_url": release_html_url,
            "published_at": str(data.get("published_at") or "")[:40],
            "release_notes": str(data.get("body") or "").strip()[:3000],
            "asset_name": asset_name,
            "asset_url": asset_url,
            "checksum_url": checksum_url,
            "message": msg,
        }
    )
    return base_resp


def _run_cmd(cmd: list[str], cwd: Path, timeout: float = 90.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # nosec B603
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr="Command timed out.")


def apply_git_update(data_dir: Path, config_home: Path) -> dict[str, Any]:
    """Fast-forward a clean Git checkout on main/master and sync Python dependencies."""
    git_bin = shutil.which("git")
    if not git_bin:
        raise UpdateError("git_missing")

    branch_proc = _run_cmd([git_bin, "rev-parse", "--abbrev-ref", "HEAD"], data_dir, timeout=15.0)
    if branch_proc.returncode != 0:
        raise UpdateError("git_branch_unknown")
    branch = branch_proc.stdout.strip()
    if branch not in {"main", "master"}:
        raise UpdateError("git_non_main")

    status_proc = _run_cmd([git_bin, "status", "--porcelain"], data_dir, timeout=15.0)
    if status_proc.returncode != 0:
        raise UpdateError("git_status_failed")
    if status_proc.stdout.strip():
        raise UpdateError("git_dirty")

    backup_path = create_pre_update_backup(config_home)

    fetch_proc = _run_cmd([git_bin, "fetch", "origin", "--tags"], data_dir, timeout=60.0)
    if fetch_proc.returncode != 0:
        raise UpdateError("git_fetch_failed")

    pull_proc = _run_cmd([git_bin, "pull", "--ff-only", "origin", branch], data_dir, timeout=60.0)
    if pull_proc.returncode != 0:
        raise UpdateError("git_pull_failed")

    dep_note = "Dependencies unchanged."
    uv_bin = shutil.which("uv")
    if uv_bin:
        sync_proc = _run_cmd([uv_bin, "sync"], data_dir, timeout=120.0)
        dep_note = (
            "Dependencies synced via uv."
            if sync_proc.returncode == 0
            else "Code updated, but uv sync reported a warning."
        )

    return {
        "ok": True,
        "mode": "git",
        "branch": branch,
        "restart_required": True,
        "backup_created": backup_path is not None,
        "message": f"Updated Git branch '{branch}' from origin. {dep_note} Restart RadioPlanner to load the new version.",
    }


def _safe_extract_update_zip(zip_path: Path, staging_dir: Path) -> Path:
    """Validate and extract a standalone update archive without Zip-Slip or zip-bomb risks."""
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    base_abs = os.path.abspath(str(staging_dir))

    try:
        zf_ctx = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        raise UpdateError("archive_corrupt") from exc
    with zf_ctx as zf:
        infos = zf.infolist()
        if len(infos) > MAX_UPDATE_FILES:
            raise UpdateError("archive_too_many_files")
        total_size = 0
        for info in infos:
            name = info.filename
            if (
                name.startswith(("/", "\\"))
                or ".." in re.split(r"[\\/]+", name)
                or WINDOWS_ABS_RE.match(name)
            ):
                raise UpdateError("archive_unsafe_path")
            total_size += max(0, info.file_size)
            if total_size > MAX_UPDATE_UNCOMPRESSED_BYTES:
                raise UpdateError("archive_too_large")

        for info in infos:
            if info.is_dir():
                continue
            dest = os.path.normpath(os.path.join(base_abs, info.filename))
            if not dest.startswith(base_abs + os.sep):
                raise UpdateError("archive_escape")
            dest_path = Path(dest)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src_f, dest_path.open("wb") as dst_f:
                shutil.copyfileobj(src_f, dst_f)

    top_entries = list(staging_dir.iterdir())
    if len(top_entries) == 1 and top_entries[0].is_dir():
        return top_entries[0]
    return staging_dir


def _write_standalone_swap_script(
    *,
    data_dir: Path,
    payload_dir: Path,
    staging_root: Path,
    pid: int,
    platform_name: str | None = None,
) -> Path:
    """Write a small OS helper script that swaps staged app files after exit while preserving exports."""
    plat = (platform_name or sys.platform).lower()
    if plat == "win32":
        script_path = staging_root / "_apply_update.bat"
        exe_name = Path(sys.executable).name if getattr(sys, "frozen", False) else "W5CDN-RadioPlanner.exe"
        script_text = (
            "@echo off\r\n"
            "setlocal\r\n"
            f'set "TARGET_PID={pid}"\r\n'
            f'set "SRC_DIR={payload_dir}"\r\n'
            f'set "DST_DIR={data_dir}"\r\n'
            f'set "STAGE_ROOT={staging_root}"\r\n'
            ":wait_exit\r\n"
            'tasklist /FI "PID eq %TARGET_PID%" 2>NUL | find /I "%TARGET_PID%" >NUL\r\n'
            "if not errorlevel 1 (\r\n"
            "  timeout /t 1 /nobreak >NUL\r\n"
            "  goto wait_exit\r\n"
            ")\r\n"
            'robocopy "%SRC_DIR%" "%DST_DIR%" /E /IS /IT /R:5 /W:1 '
            '/XF .env *.bak /XD exports _update_staging >NUL\r\n'
            f'if exist "%DST_DIR%\\{exe_name}" start "" "%DST_DIR%\\{exe_name}"\r\n'
            'rmdir /S /Q "%STAGE_ROOT%" >NUL 2>&1\r\n'
            "endlocal\r\n"
        )
        script_path.write_text(script_text, encoding="utf-8")
        return script_path

    script_path = staging_root / "_apply_update.sh"
    launcher = data_dir / "run-w5cdn-radio-planner.sh"
    exe_name = Path(sys.executable).name if getattr(sys, "frozen", False) else "W5CDN-RadioPlanner"
    script_text = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"TARGET_PID={pid}\n"
        f'SRC_DIR="{payload_dir}"\n'
        f'DST_DIR="{data_dir}"\n'
        f'STAGE_ROOT="{staging_root}"\n'
        'while kill -0 "$TARGET_PID" 2>/dev/null; do sleep 0.5; done\n'
        'for item in "$SRC_DIR"/*; do\n'
        '  base="$(basename "$item")"\n'
        '  case "$base" in\n'
        '    .env|exports|*.bak) continue ;;\n'
        '  esac\n'
        '  rm -rf "$DST_DIR/$base"\n'
        '  cp -a "$item" "$DST_DIR/$base"\n'
        'done\n'
        f'if [[ -x "{launcher}" ]]; then\n'
        f'  nohup "{launcher}" >/dev/null 2>&1 &\n'
        f'elif [[ -x "$DST_DIR/{exe_name}" ]]; then\n'
        f'  nohup "$DST_DIR/{exe_name}" --app-window >/dev/null 2>&1 &\n'
        "fi\n"
        'rm -rf "$STAGE_ROOT"\n'
    )
    script_path.write_text(script_text, encoding="utf-8", newline="\n")
    try:
        os.chmod(script_path, 0o700)
    except OSError:
        pass
    return script_path


async def apply_standalone_update(
    *,
    data_dir: Path,
    config_home: Path,
    asset_name: str,
    asset_url: str,
    checksum_url: str,
    current_version: str,
    client: httpx.AsyncClient | None = None,
    spawn_helper: bool = True,
) -> dict[str, Any]:
    """Download, SHA-256 verify, safely extract, and launch detached swap helper for standalone bundles."""
    safe_asset_url = validate_download_url(asset_url)
    safe_checksum_url = validate_download_url(checksum_url)
    clean_asset_name = Path(asset_name).name
    if (
        not clean_asset_name
        or not clean_asset_name.lower().endswith(".zip")
        or any(ch in clean_asset_name for ch in ("/", "\\", "\x00"))
        or ".." in clean_asset_name
    ):
        raise UpdateError("archive_invalid_name")

    staging_root = data_dir / "_update_staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging_abs = os.path.abspath(str(staging_root))
    archive_norm = os.path.normpath(os.path.join(staging_abs, clean_asset_name))
    if not archive_norm.startswith(staging_abs + os.sep):
        raise UpdateError("archive_invalid_name")
    archive_path = Path(archive_norm)

    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=10.0),
        headers={"User-Agent": f"W5CDN-RadioPlanner/{current_version}"},
        follow_redirects=True,
    )
    try:
        sum_resp = await http.get(safe_checksum_url)
        sum_resp.raise_for_status()
        checksums = parse_sha256sums(sum_resp.text)
        expected_hash = checksums.get(clean_asset_name)
        if not expected_hash:
            raise UpdateError("checksum_missing")

        downloaded = 0
        async with http.stream("GET", safe_asset_url) as resp:
            resp.raise_for_status()
            with archive_path.open("wb") as out_f:
                async for chunk in resp.aiter_bytes(65536):
                    downloaded += len(chunk)
                    if downloaded > MAX_UPDATE_ARCHIVE_BYTES:
                        raise UpdateError("download_too_large")
                    out_f.write(chunk)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Standalone update download failed: %s", exc)
        raise UpdateError("download_failed") from exc
    finally:
        if owns_client:
            await http.aclose()

    if not verify_sha256(archive_path, expected_hash):
        archive_path.unlink(missing_ok=True)
        raise UpdateError("checksum_mismatch")

    extract_dir = staging_root / "extracted"
    payload_dir = _safe_extract_update_zip(archive_path, extract_dir)
    archive_path.unlink(missing_ok=True)
    backup_path = create_pre_update_backup(config_home)

    helper_script = _write_standalone_swap_script(
        data_dir=data_dir,
        payload_dir=payload_dir,
        staging_root=staging_root,
        pid=os.getpid(),
    )
    if spawn_helper:
        if sys.platform == "win32":
            cmd_bin = shutil.which("cmd.exe") or "cmd.exe"
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(  # nosec B603
                [cmd_bin, "/c", str(helper_script)],
                creationflags=flags,
                close_fds=True,
            )
        else:
            bash_bin = shutil.which("bash") or "/bin/bash"
            subprocess.Popen(  # nosec B603
                [bash_bin, str(helper_script)],
                start_new_session=True,
                close_fds=True,
            )

    return {
        "ok": True,
        "mode": "standalone",
        "restart_required": True,
        "backup_created": backup_path is not None,
        "helper_script": str(helper_script),
        "message": "Update verified (SHA-256 OK) and staged. RadioPlanner is restarting to finish installation.",
    }
