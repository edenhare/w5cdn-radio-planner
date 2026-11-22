"""Async Amateur Radio Callsign Lookup Service (QRZ.com XML + Callook.info fallback).

Adapted from w5cdn-net-logger with XXE-safe XML parsing.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

logger = logging.getLogger("radioplanner.callsign_lookup")

CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]{1,4}(/[A-Z0-9]{1,4})?$")
QRZ_XML_URL = "https://xmldata.qrz.com/xml/current/"
CALLOOK_URL_TMPL = "https://callook.info/{call}/json"


def parse_xml_safely(xml_text: str) -> ET.Element:
    """Parse XML while rejecting DOCTYPE/ENTITY declarations (XXE & entity-expansion defense)."""
    head = (xml_text or "")[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        raise ET.ParseError("XML DOCTYPE/ENTITY declarations are not permitted")
    return ET.fromstring(xml_text)  # nosec B314


def _xml_child_text(root: ET.Element, tag: str) -> str:
    for elem in root.iter():
        local = elem.tag.rsplit("}", 1)[-1]
        if local == tag and elem.text:
            return elem.text.strip()
    return ""


def _format_callook_name(raw_name: str) -> str:
    cleaned = (raw_name or "").strip()
    if "," in cleaned:
        last, first = [p.strip() for p in cleaned.split(",", 1)]
        return f"{first} {last}".strip().title()
    return cleaned.title()


class CallsignLookupService:
    """Look up amateur radio callsigns via QRZ.com XML (if configured) with Callook.info fallback."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._qrz_key: str | None = None
        self._qrz_user: str = ""

    def reset_qrz_session(self) -> None:
        self._qrz_key = None
        self._qrz_user = ""

    async def _http_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        return (
            httpx.AsyncClient(
                timeout=httpx.Timeout(6.0, connect=4.0),
                headers={"User-Agent": "W5CDN-RadioPlanner/0.2.0"},
                follow_redirects=True,
            ),
            True,
        )

    async def _qrz_login(self, http: httpx.AsyncClient, username: str, password: str) -> tuple[str | None, str]:
        resp = await http.get(QRZ_XML_URL, params={"username": username, "password": password})
        resp.raise_for_status()
        root = parse_xml_safely(resp.text)
        key = _xml_child_text(root, "Key")
        err = _xml_child_text(root, "Error")
        if key:
            self._qrz_key = key
            self._qrz_user = username
            return key, ""
        return None, err or "QRZ XML login failed"

    async def test_qrz_login(self, username: str, password: str) -> dict[str, Any]:
        if not username.strip() or not password.strip():
            return {"ok": False, "message": "Enter both QRZ username and password first."}
        http, owns = await self._http_client()
        try:
            key, err = await self._qrz_login(http, username.strip(), password.strip())
            if key:
                return {"ok": True, "message": f"QRZ XML login succeeded for {username.strip().upper()}."}
            return {"ok": False, "message": err}
        except (httpx.HTTPError, ET.ParseError, OSError, ValueError) as exc:
            return {"ok": False, "message": f"QRZ connection error: {exc}"}
        finally:
            if owns:
                await http.aclose()

    async def _lookup_qrz(
        self,
        http: httpx.AsyncClient,
        callsign: str,
        username: str,
        password: str,
    ) -> dict[str, Any] | None:
        if not username or not password:
            return None
        if not self._qrz_key or self._qrz_user != username:
            key, _ = await self._qrz_login(http, username, password)
            if not key:
                return None

        resp = await http.get(QRZ_XML_URL, params={"s": self._qrz_key, "callsign": callsign})
        resp.raise_for_status()
        root = parse_xml_safely(resp.text)
        err = _xml_child_text(root, "Error")
        if err and "session" in err.lower():
            key, _ = await self._qrz_login(http, username, password)
            if not key:
                return None
            resp = await http.get(QRZ_XML_URL, params={"s": key, "callsign": callsign})
            resp.raise_for_status()
            root = parse_xml_safely(resp.text)

        found_call = _xml_child_text(root, "call").upper()
        if not found_call:
            return None
        fname = _xml_child_text(root, "fname")
        lname = _xml_child_text(root, "name")
        city = _xml_child_text(root, "addr2")
        state = _xml_child_text(root, "state").upper()
        grid = _xml_child_text(root, "grid").upper()
        lic_class = _xml_child_text(root, "class").upper()
        qth = f"{city}, {state}".strip(", ")
        return {
            "found": True,
            "source": "qrz",
            "callsign": found_call,
            "name": f"{fname} {lname}".strip() or found_call,
            "qth": qth,
            "city": city,
            "state": state,
            "grid": grid,
            "license_class": lic_class,
        }

    async def _lookup_callook(self, http: httpx.AsyncClient, callsign: str) -> dict[str, Any] | None:
        base_call = callsign.split("/", 1)[0]
        resp = await http.get(CALLOOK_URL_TMPL.format(call=base_call))
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or str(data.get("status", "")).upper() != "VALID":
            return None
        addr = data.get("address") if isinstance(data.get("address"), dict) else {}
        loc = data.get("location") if isinstance(data.get("location"), dict) else {}
        cur = data.get("current") if isinstance(data.get("current"), dict) else {}
        line2 = str(addr.get("line2") or "").strip()
        city = ""
        state = ""
        if "," in line2:
            city_part, rest = line2.split(",", 1)
            city = city_part.strip().title()
            state = rest.strip().split(" ", 1)[0].upper()
        qth = f"{city}, {state}".strip(", ") or line2
        return {
            "found": True,
            "source": "callook",
            "callsign": str(cur.get("callsign") or base_call).upper(),
            "name": _format_callook_name(str(data.get("name") or "")),
            "qth": qth,
            "city": city,
            "state": state,
            "grid": str(loc.get("gridsquare") or "").upper(),
            "license_class": str(cur.get("operClass") or "").upper(),
        }

    async def lookup(
        self,
        callsign: str,
        *,
        qrz_user: str | None = None,
        qrz_pass: str | None = None,
    ) -> dict[str, Any]:
        cleaned = (callsign or "").strip().upper()
        if not cleaned or not CALLSIGN_RE.match(cleaned):
            return {"found": False, "callsign": cleaned, "source": "none", "error": "Invalid callsign format"}

        http, owns = await self._http_client()
        try:
            if qrz_user and qrz_pass:
                try:
                    qrz_res = await self._lookup_qrz(http, cleaned, qrz_user, qrz_pass)
                    if qrz_res:
                        return qrz_res
                except (httpx.HTTPError, ET.ParseError, OSError, ValueError) as exc:
                    logger.debug("QRZ lookup fallback to Callook for %s: %s", cleaned, exc)

            callook_res = await self._lookup_callook(http, cleaned)
            if callook_res:
                return callook_res
            return {"found": False, "callsign": cleaned, "source": "callook"}
        except (httpx.HTTPError, ValueError, OSError) as exc:
            logger.debug("Callsign lookup failed for %s: %s", cleaned, exc)
            return {"found": False, "callsign": cleaned, "source": "offline", "error": str(exc)}
        finally:
            if owns:
                await http.aclose()
