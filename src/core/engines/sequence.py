"""Sequence Ordering and Channel Assembly Engine."""

from __future__ import annotations

from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.special_channels import (
    filter_channels_for_radio,
    get_national_calling_channels,
    get_noaa_wx_channels,
)


class SequenceOrganizer:
    """Assembles final codeplug by ordering channel blocks according to sequence positions."""

    @classmethod
    def assemble(
        cls,
        codeplug_name: str,
        sequence_keys: list[str],
        primary_channels: list[RadioChannel],
        target_spec: TargetRadioSpec,
        custom_templates: dict[str, list[RadioChannel]] | None = None,
        deduplicate: bool = True,
    ) -> Codeplug:
        """Merge sequence blocks, filter against radio hardware specs, and renumber."""
        custom_map = custom_templates or {}
        raw_combined: list[RadioChannel] = []

        for key in sequence_keys:
            if key == "ROUTE_PLAN" or key == "PROXIMITY_PLAN" or key == "AVIATION_BLOCK":
                raw_combined.extend(primary_channels)
            elif key == "TEMPLATE:builtin_calling_channels":
                raw_combined.extend(get_national_calling_channels())
            elif key == "TEMPLATE:builtin_noaa_wx_channels":
                raw_combined.extend(get_noaa_wx_channels())
            elif key in custom_map:
                raw_combined.extend(custom_map[key])

        # 1. Filter against radio supported bands and modes
        filtered = filter_channels_for_radio(raw_combined, target_spec)

        # 2. Deduplicate if enabled (match by rxFreq + tone)
        if deduplicate:
            seen = set()
            unique_channels = []
            for ch in filtered:
                ch_key = (
                    round(ch.rxFreq, 4),
                    ch.toneMode,
                    ch.ctcss,
                    ch.dcs,
                    ch.callsign,
                )
                if ch_key not in seen:
                    seen.add(ch_key)
                    unique_channels.append(ch)
            filtered = unique_channels

        # 3. Create codeplug and renumber
        codeplug = Codeplug(name=codeplug_name, channels=filtered).renumbered()
        return codeplug
