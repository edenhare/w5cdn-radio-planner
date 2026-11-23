"""Security hardening middleware and input sanitizers for RadioPlanner Web Cockpit.

Adapted directly from the localhost security constructs in w5cdn-net-logger:
- DNS rebinding Host allowlist validation
- Cross-site CSRF Origin enforcement on mutating HTTP verbs
- Defensive HTTP response headers (nosniff, DENY framing, no-referrer, Permissions-Policy)
- Safe child path resolution (path traversal defense)
- Single-line control character scrubbing and CSV formula-injection neutralization
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from core.sanitizers.sanitizer import DataSanitizer

CTRL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
URL_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")
HOST_PORT_RE = re.compile(r"^(?:localhost|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+):\d{1,5}(?:/.*)?$", re.IGNORECASE)
LOCAL_ORIGIN_RE = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\]|testserver)(:\d{1,5})?$", re.IGNORECASE)

MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def clean_single_line(raw: Any, max_len: int = 200) -> str:
    """Strip ASCII control characters (including CR/LF/NUL) to prevent header/log injection."""
    return CTRL_CHARS_RE.sub("", str(raw or "")).strip()[:max_len]


def sanitize_http_url(raw: Any, *, default_scheme: str = "https", max_len: int = 240) -> str:
    """Allow only http:// or https:// URLs; reject javascript:, data:, file:, etc."""
    cleaned = clean_single_line(raw, max_len=max_len)
    if not cleaned or any(ch.isspace() for ch in cleaned):
        return ""
    if HOST_PORT_RE.match(cleaned):
        return f"{default_scheme}://{cleaned}"[:max_len]
    match = URL_SCHEME_RE.match(cleaned)
    if match:
        scheme = match.group(1).lower()
        if scheme not in {"http", "https"}:
            return ""
        return cleaned[:max_len]
    return f"{default_scheme}://{cleaned}"[:max_len]


def safe_child_path(base_dir: Path, filename: str) -> Path:
    """Resolve a single filename strictly inside base_dir (prevents path traversal)."""
    raw = str(filename or "")
    if not raw or CTRL_CHARS_RE.search(raw) or "/" in raw or "\\" in raw or ".." in raw:
        raise HTTPException(status_code=400, detail="Invalid filename")
    clean_name = Path(raw).name
    if not clean_name or clean_name in {".", ".."} or "/" in clean_name or "\\" in clean_name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    base_abs = os.path.abspath(str(base_dir))
    full_path = os.path.normpath(os.path.join(base_abs, clean_name))
    if not full_path.startswith(base_abs + os.sep):
        raise HTTPException(status_code=400, detail="File path escapes target directory")
    return Path(full_path)


def csv_safe_cell(val: Any) -> str:
    """Neutralize spreadsheet formula injection while keeping negative numbers intact."""
    return DataSanitizer.csv_safe_cell(val)


def allowed_hosts() -> set[str]:
    """Return allowed Host header hostnames for local operation."""
    hosts = {"127.0.0.1", "localhost", "::1", "testserver"}
    configured = (os.environ.get("HOST") or os.environ.get("RADIOPLANNER_HOST") or "").strip().lower().strip("[]")
    if configured and configured not in {"0.0.0.0", "::"}:  # nosec B104
        hosts.add(configured)
    return hosts


def extract_hostname(host_header: str) -> str:
    """Extract lowercase hostname without port from an HTTP Host header."""
    raw = (host_header or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("["):
        end = raw.find("]")
        return raw[1:end] if end != -1 else raw
    if ":" in raw:
        return raw.split(":", 1)[0]
    return raw


def is_allowed_origin(origin: str) -> bool:
    """Validate that a browser Origin header matches localhost or the configured HOST."""
    cleaned = (origin or "").strip()
    if not cleaned or cleaned.lower() == "null":
        return False
    if LOCAL_ORIGIN_RE.match(cleaned):
        return True
    configured = (os.environ.get("HOST") or os.environ.get("RADIOPLANNER_HOST") or "").strip().lower().strip("[]")
    if configured and configured not in {"0.0.0.0", "::"}:  # nosec B104
        escaped = re.escape(configured)
        if re.match(rf"^https?://{escaped}(:\d{{1,5}})?$", cleaned, re.IGNORECASE):
            return True
    return False


async def security_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Defend localhost server against DNS rebinding, cross-site CSRF, and clickjacking."""
    host_hdr = request.headers.get("host", "")
    if host_hdr and extract_hostname(host_hdr) not in allowed_hosts():
        return JSONResponse(status_code=403, content={"detail": "Forbidden Host header"})

    if request.method in MUTATING_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and not is_allowed_origin(origin):
            return JSONResponse(status_code=403, content={"detail": "Forbidden cross-origin request"})

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(self), microphone=(), camera=()",
    )
    return response
