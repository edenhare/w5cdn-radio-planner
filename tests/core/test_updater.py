"""Unit & security tests for core.updater (Git & Standalone SHA-256 self-updater)."""

from __future__ import annotations

import asyncio
import hashlib
import io
import subprocess
import zipfile
from pathlib import Path

import httpx
import pytest

from core import updater


def test_semver_parsing_and_comparison() -> None:
    assert updater.parse_semver("v1.2.3") == (1, 2, 3)
    assert updater.parse_semver("0.2.0") == (0, 2, 0)
    assert updater.parse_semver("invalid") == (0, 0, 0)
    assert updater.is_newer_version("v0.3.0", "0.2.0") is True
    assert updater.is_newer_version("v0.2.0", "0.2.0") is False
    assert updater.is_newer_version("v0.1.9", "0.2.0") is False


def test_validate_download_url_allowlist() -> None:
    good = "https://github.com/edenhare/w5cdn-radio-planner/releases/download/v0.2.0/W5CDN-RadioPlanner-windows-amd64.zip"
    assert updater.validate_download_url(good) == good

    for bad in (
        "http://github.com/a/b.zip",
        "https://evil.example/payload.zip",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ):
        with pytest.raises(updater.UpdateError) as exc:
            updater.validate_download_url(bad)
        assert exc.value.code == "untrusted_url"


def test_select_release_asset_and_sha256_parsing(tmp_path: Path) -> None:
    assets = [
        {"name": "W5CDN-RadioPlanner-linux-x86_64.zip", "browser_download_url": "https://github.com/r/linux.zip"},
        {"name": "W5CDN-RadioPlanner-windows-amd64.zip", "browser_download_url": "https://github.com/r/win.zip"},
        {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/r/SHA256SUMS.txt"},
    ]
    win_asset, sums = updater.select_release_asset(assets, platform_name="win32", machine="AMD64")
    assert win_asset and win_asset["name"] == "W5CDN-RadioPlanner-windows-amd64.zip"
    assert sums and sums["name"] == "SHA256SUMS.txt"

    lin_asset, _ = updater.select_release_asset(assets, platform_name="linux", machine="x86_64")
    assert lin_asset and lin_asset["name"] == "W5CDN-RadioPlanner-linux-x86_64.zip"

    sample = tmp_path / "pkg.zip"
    sample.write_bytes(b"hello radioplanner")
    digest = hashlib.sha256(b"hello radioplanner").hexdigest()
    parsed = updater.parse_sha256sums(f"# comment\n{digest}  dist/pkg.zip\nbadline\n")
    assert parsed == {"pkg.zip": digest}
    assert updater.verify_sha256(sample, digest) is True
    assert updater.verify_sha256(sample, "0" * 64) is False


def test_check_for_update_online_and_offline(tmp_path: Path) -> None:
    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tag_name": "v0.9.0",
                "name": "v0.9.0 Release",
                "html_url": "https://github.com/edenhare/w5cdn-radio-planner/releases/tag/v0.9.0",
                "published_at": "2026-11-22T00:00:00Z",
                "body": "- Added new feature",
                "assets": [
                    {"name": "W5CDN-RadioPlanner-windows-amd64.zip", "browser_download_url": "https://github.com/x/win.zip"},
                    {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/x/SHA256SUMS.txt"},
                ],
            },
        )

    def err_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    async def _run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(ok_handler)) as client:
            res = await updater.check_for_update(current_version="0.2.0", data_dir=tmp_path, client=client)
            assert res["online"] is True
            assert res["update_available"] is True
            assert res["latest_version"] == "0.9.0"

        async with httpx.AsyncClient(transport=httpx.MockTransport(err_handler)) as client:
            res_off = await updater.check_for_update(current_version="0.2.0", data_dir=tmp_path, client=client)
            assert res_off["online"] is False
            assert res_off["update_available"] is False

    asyncio.run(_run())


def test_apply_git_update_guards_and_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "preferences.yaml").write_text("callsign: W5CDN\n", encoding="utf-8")

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/git" if name == "git" else None)

    def fake_run_dirty(cmd, cwd, timeout=90.0):
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/app.py\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(updater, "_run_cmd", fake_run_dirty)
    with pytest.raises(updater.UpdateError) as exc:
        updater.apply_git_update(tmp_path, cfg)
    assert exc.value.code == "git_dirty"

    def fake_run_clean(cmd, cwd, timeout=90.0):
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(updater, "_run_cmd", fake_run_clean)
    res = updater.apply_git_update(tmp_path, cfg)
    assert res["ok"] is True
    assert res["backup_created"] is True
    assert (cfg / "radioplanner.pre_update.bak").is_file()


def test_apply_standalone_update_verified_and_zip_slip_blocked(tmp_path: Path) -> None:
    # Build valid update zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("W5CDN-RadioPlanner/README.md", "new version")
    zip_bytes = buf.getvalue()
    digest = hashlib.sha256(zip_bytes).hexdigest()

    asset_name = "W5CDN-RadioPlanner-windows-amd64.zip"
    asset_url = f"https://github.com/edenhare/w5cdn-radio-planner/releases/download/v0.3.0/{asset_name}"
    sums_url = "https://github.com/edenhare/w5cdn-radio-planner/releases/download/v0.3.0/SHA256SUMS.txt"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == sums_url:
            return httpx.Response(200, text=f"{digest}  {asset_name}\n")
        if str(request.url) == asset_url:
            return httpx.Response(200, content=zip_bytes)
        return httpx.Response(404)

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "preferences.yaml").write_text("callsign: W5CDN\n", encoding="utf-8")

    async def _run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            res = await updater.apply_standalone_update(
                data_dir=tmp_path / "app",
                config_home=cfg,
                asset_name=asset_name,
                asset_url=asset_url,
                checksum_url=sums_url,
                current_version="0.2.0",
                client=client,
                spawn_helper=False,
            )
            assert res["ok"] is True
            assert res["mode"] == "standalone"
            assert Path(res["helper_script"]).is_file()

    asyncio.run(_run())

    # Zip-Slip archive must be rejected
    evil_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as zf:
        zf.writestr("../../pwned.txt", "nope")
    with pytest.raises(updater.UpdateError) as exc:
        updater._safe_extract_update_zip(evil_zip, tmp_path / "stage")
    assert exc.value.code == "archive_unsafe_path"
