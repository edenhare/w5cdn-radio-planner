"""RadioID.net API Client and DMR Talkgroup Expander."""

from __future__ import annotations

from typing import Any

from core.models.channel import RadioChannel

OFFLINE_RADIO_ID_USERS: dict[str, dict[str, Any]] = {
    "w5cdn": {
        "callsign": "W5CDN",
        "id": "3224901",
        "fname": "Radio",
        "lname": "Operator",
    }
}

DEFAULT_DMR_TALKGROUPS = [
    {"name": "Local 9", "tg": "9", "ts": 1},
    {"name": "Texas Statewide", "tg": "3148", "ts": 2},
    {"name": "TAC 310", "tg": "310", "ts": 1},
    {"name": "North America", "tg": "3100", "ts": 1},
    {"name": "Parrot", "tg": "9990", "ts": 2},
]


class RadioIdProvider:
    """Interacts with RadioID.net for callsign resolution and DMR Talkgroups."""

    def __init__(self, username: str | None = None, api_key: str | None = None):
        self.username = username
        self.api_key = api_key

    def lookup_callsign(self, callsign: str) -> str | None:
        """Resolve an amateur callsign to its primary 7-digit DMR Radio ID."""
        key = callsign.strip().lower()
        if key in OFFLINE_RADIO_ID_USERS:
            return OFFLINE_RADIO_ID_USERS[key]["id"]
        return None

    def duplicate_channel_for_talkgroups(
        self,
        base_channel: RadioChannel,
        talkgroups: list[dict[str, Any]] | None = None,
    ) -> list[RadioChannel]:
        """Duplicate a DMR channel for each configured Talkgroup entry with custom channel names."""
        tgs = talkgroups if talkgroups is not None else DEFAULT_DMR_TALKGROUPS
        duplicated: list[RadioChannel] = []

        for item in tgs:
            tg_name = item.get("name", "TG")
            tg_id = str(item.get("tg", "9"))
            ts = int(item.get("ts", 1))

            new_name = f"{base_channel.name} {tg_name}"
            comment = f"{base_channel.comment} [TG {tg_id} TS{ts}]".strip()

            new_ch = base_channel.model_copy(
                update={
                    "name": new_name,
                    "mode": "DMR",
                    "timeSlot": ts,
                    "dmrId": tg_id,
                    "contact": tg_name,
                    "comment": comment,
                }
            )
            duplicated.append(new_ch)

        return duplicated
