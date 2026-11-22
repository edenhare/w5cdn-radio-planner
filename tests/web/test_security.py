"""Security hardening & input-validation tests for RadioPlanner Web Cockpit."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from web.app import app
from web.security import (
    clean_single_line,
    csv_safe_cell,
    safe_child_path,
    sanitize_http_url,
)

client = TestClient(app)


def test_security_headers_and_host_origin_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify defensive headers, DNS rebinding Host allowlist, and CSRF Origin validation."""
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in resp.headers["Permissions-Policy"]
    assert "geolocation=(self)" in resp.headers["Permissions-Policy"]

    for good_host in ("127.0.0.1:8000", "localhost:8000", "[::1]:8000", "testserver"):
        r = client.get("/api/config", headers={"Host": good_host})
        assert r.status_code == 200

    # DNS rebinding Host header rejected with 403
    for bad_host in ("evil.example", "attacker.local:8000", "192.0.2.99:8000"):
        r = client.get("/api/config", headers={"Host": bad_host})
        assert r.status_code == 403
        assert "Host" in r.json()["detail"]

    # Configured HOST env var allowed for both Host and Origin
    monkeypatch.setenv("HOST", "shack.local")
    assert client.get("/api/config", headers={"Host": "shack.local:8000"}).status_code == 200
    assert (
        client.put(
            "/api/preferences",
            json={"colorTheme": "shack-dark"},
            headers={"Host": "shack.local:8000", "Origin": "http://shack.local:8000"},
        ).status_code
        == 200
    )

    # Cross-site CSRF Origin rejected on mutating verbs
    for bad_origin in ("https://evil.example", "http://evil.example:8000", "null", ""):
        r = client.put(
            "/api/preferences",
            json={"colorTheme": "daylight"},
            headers={"Origin": bad_origin},
        )
        assert r.status_code == 403
        assert "cross-origin" in r.json()["detail"].lower()

    # Localhost Origin allowed
    ok = client.put(
        "/api/preferences",
        json={"colorTheme": "shack-dark"},
        headers={"Origin": "http://127.0.0.1:8000"},
    )
    assert ok.status_code == 200


def test_path_traversal_blocked_in_recipes_and_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify path traversal payloads are rejected with 400 on recipe and CSV export routes."""
    monkeypatch.setattr("web.app.get_recipes_dir", lambda: tmp_path)

    for bad_name in ("../secret.yaml", "..\\windows.ini", "a/b.yaml", "bad\x00.yaml"):
        with pytest.raises(HTTPException) as exc_info:
            safe_child_path(tmp_path, bad_name)
        assert exc_info.value.status_code == 400

    res_upload = client.post(
        "/api/recipes/upload",
        json={
            "filename": "../../evil.yaml",
            "yaml_text": (
                "version: '1.0'\nmode: 'PROXIMITY_SEARCH'\nname: 'SafeTest'\n"
                "proximity:\n  center_location: 'Dallas, TX'\n  radius_miles: 25\n"
            ),
        },
    )
    assert res_upload.status_code == 400

    # Ensure active plan exists then test malicious export filename
    client.post(
        "/api/plan/generate",
        json={"mode": "PROXIMITY_SEARCH", "center_location": "Dallas, TX", "radius_miles": 25.0},
    )
    res_exp = client.post(
        "/api/codeplug/export",
        json={"programmer_type": "CHIRP", "filename": "../../escape.csv"},
    )
    assert res_exp.status_code == 400


def test_sanitizers_url_control_chars_and_csv_cells() -> None:
    """Verify URL scheme enforcement, CR/LF stripping, and CSV formula neutralization."""
    for bad_url in (
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "http://example.com/has space",
    ):
        assert sanitize_http_url(bad_url) == ""

    assert sanitize_http_url("https://repeaterbook.com/api") == "https://repeaterbook.com/api"
    assert sanitize_http_url("127.0.0.1:8000") == "https://127.0.0.1:8000"
    assert clean_single_line("W5CDN\r\nINJECT\x00") == "W5CDNINJECT"

    # CSV formula injection neutralized while negative numbers remain untouched
    assert csv_safe_cell("=CMD|' /C calc'!A0").startswith("'")
    assert csv_safe_cell("+SUM(A1:A2)").startswith("'")
    assert csv_safe_cell("@SUM(1,2)").startswith("'")
    assert csv_safe_cell("-0.600") == "-0.600"
    assert csv_safe_cell("-95.3011") == "-95.3011"
    assert csv_safe_cell("-CMD()") == "'-CMD()"


def test_xxe_qrz_password_crlf_and_backup_zip_slip_defenses() -> None:
    """Verify XML DOCTYPE/ENTITY rejection, QRZ CR/LF rejection, and backup restore Zip-Slip blocking."""
    import io
    import xml.etree.ElementTree as ET
    import zipfile

    from core.providers.callsign_lookup import parse_xml_safely
    from core.updater import UpdateError, validate_download_url

    with pytest.raises(ET.ParseError):
        parse_xml_safely('<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><QRZDatabase>&xxe;</QRZDatabase>')

    # CR/LF/NUL in QRZ password must be rejected with 422
    for bad_pw in ("abc\r\ndef", "abc\ndef", "abc\x00def"):
        res = client.put("/api/preferences", json={"qrzPassword": bad_pw})
        assert res.status_code == 422

    # Zip-Slip archive uploaded to /api/backup/restore must be rejected with 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.yaml", "callsign: HACK\n")
    r_slip = client.post("/api/backup/restore", content=buf.getvalue(), headers={"Content-Type": "application/zip"})
    assert r_slip.status_code == 400

    # Non-zip payload rejected with 400
    r_bad = client.post("/api/backup/restore", content=b"not a zip", headers={"Content-Type": "application/zip"})
    assert r_bad.status_code == 400

    # Untrusted update download URL rejected
    with pytest.raises(UpdateError):
        validate_download_url("https://attacker.example/release.zip")
