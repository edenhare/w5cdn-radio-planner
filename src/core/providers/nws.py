"""Async National Weather Service (NWS api.weather.gov) Active Alerts Provider.

Adapted from w5cdn-net-logger for Route Corridor and Proximity Area weather briefings.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("radioplanner.nws")

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
STATE_CODE_RE = re.compile(r"^[A-Z]{2}$")
SEVERITY_ORDER: dict[str, int] = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}


class NwsAlertsService:
    """Fetch active National Weather Service alerts for states covered by a RadioPlanner plan."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _http_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        return (
            httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=5.0),
                headers={
                    "Accept": "application/geo+json",
                    "User-Agent": "(W5CDN-RadioPlanner, github.com/edenhare/w5cdn-radio-planner)",
                },
                follow_redirects=True,
            ),
            True,
        )

    async def get_alerts_for_states(self, states: list[str], *, max_alerts: int = 25) -> dict[str, Any]:
        """Query active NWS alerts across 2-letter US state abbreviations (offline-safe)."""
        clean_states = sorted({s.strip().upper() for s in states if STATE_CODE_RE.match(s.strip().upper())})
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not clean_states:
            return {
                "online": True,
                "states": [],
                "fetched_at": fetched_at,
                "count": 0,
                "alerts": [],
                "briefing_text": "No US states specified for NWS weather briefing.",
            }

        http, owns = await self._http_client()
        try:
            resp = await http.get(NWS_ALERTS_URL, params={"area": ",".join(clean_states)})
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError, OSError) as exc:
            logger.info("NWS weather alert fetch unavailable: %s", exc)
            return {
                "online": False,
                "states": clean_states,
                "fetched_at": fetched_at,
                "count": 0,
                "alerts": [],
                "error": f"Could not reach api.weather.gov: {exc}",
                "briefing_text": f"NWS weather briefing offline/unavailable for {', '.join(clean_states)}.",
            }
        finally:
            if owns:
                await http.aclose()

        features = data.get("features") if isinstance(data, dict) else []
        alerts: list[dict[str, Any]] = []
        for feat in features if isinstance(features, list) else []:
            props = feat.get("properties") if isinstance(feat, dict) else None
            if not isinstance(props, dict):
                continue
            alerts.append(
                {
                    "id": str(props.get("id") or ""),
                    "event": str(props.get("event") or "Weather Alert"),
                    "severity": str(props.get("severity") or "Unknown"),
                    "urgency": str(props.get("urgency") or ""),
                    "certainty": str(props.get("certainty") or ""),
                    "headline": str(props.get("headline") or ""),
                    "area": str(props.get("areaDesc") or "")[:240],
                    "expires": str(props.get("expires") or ""),
                    "description": str(props.get("description") or "").strip()[:1200],
                    "instruction": str(props.get("instruction") or "").strip()[:600],
                }
            )

        alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 4), a["event"]))
        alerts = alerts[:max_alerts]

        lines = [
            f"NWS ACTIVE WEATHER BRIEFING — States: {', '.join(clean_states)}",
            f"Fetched: {fetched_at} | Active Alerts Shown: {len(alerts)}",
            "=" * 72,
        ]
        if not alerts:
            lines.append("ALL CLEAR — No active NWS watches, warnings, or advisories.")
        else:
            for idx, a in enumerate(alerts, start=1):
                lines.append(f"{idx}. [{a['severity'].upper()}] {a['event']}")
                if a["headline"]:
                    lines.append(f"   {a['headline']}")
                if a["area"]:
                    lines.append(f"   Areas: {a['area']}")
                if a["expires"]:
                    lines.append(f"   Expires: {a['expires']}")
        briefing_text = "\n".join(lines) + "\n"

        return {
            "online": True,
            "states": clean_states,
            "fetched_at": fetched_at,
            "count": len(alerts),
            "alerts": alerts,
            "briefing_text": briefing_text,
        }
