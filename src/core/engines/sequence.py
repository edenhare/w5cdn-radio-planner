"""Sequence Ordering and Channel Assembly Engine."""

from __future__ import annotations

from typing import Any

from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.sanitizers.condenser import NameCondenser
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
        template_manager: Any | None = None,
        allowed_bands: list[str] | None = None,
        allowed_modes: list[str] | None = None,
        deduplicate: bool = True,
        naming_format: str = "CITY_FREQ",
    ) -> Codeplug:
        """Merge sequence blocks, filter against radio hardware specs and active bands, and renumber."""
        custom_map = custom_templates or {}
        raw_combined: list[RadioChannel] = []

        for key in sequence_keys:
            if key in {"ROUTE_PLAN", "PROXIMITY_PLAN", "AVIATION_BLOCK"}:
                raw_combined.extend(primary_channels)
            elif key in custom_map:
                raw_combined.extend(custom_map[key])
            elif key.startswith("TEMPLATE:"):
                tpl_id = key.split(":", 1)[1]
                if (
                    template_manager
                    and hasattr(template_manager, "has_template")
                    and template_manager.has_template(tpl_id)
                ):
                    raw_combined.extend(template_manager.get_template_channels(tpl_id))
                elif tpl_id in {"calling_channels", "builtin_calling_channels"}:
                    raw_combined.extend(get_national_calling_channels())
                elif tpl_id in {"noaa_wx_channels", "builtin_noaa_wx_channels"}:
                    raw_combined.extend(get_noaa_wx_channels())

        # 1. Filter against radio supported bands and modes
        filtered = filter_channels_for_radio(
            raw_combined, target_spec, allowed_bands=allowed_bands, allowed_modes=allowed_modes
        )

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

        # 3. Apply target radio name condensation rules
        condensed_channels = [
            ch.with_name(NameCondenser.condense_channel(ch, target_spec, naming_format=naming_format))
            for ch in filtered
        ]

        # 4. Create codeplug and renumber
        codeplug = Codeplug(name=codeplug_name, channels=condensed_channels).renumbered()
        return codeplug
