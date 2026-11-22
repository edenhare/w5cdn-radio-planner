"""Active workspace state manager for the RadioPlanner Web Cockpit."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config.paths import initialize_startup_environment
from core.config.recipe import RadioPlannerRecipe
from core.managers.preferences_manager import PreferencesManager
from core.managers.radio_manager import RadioManager
from core.managers.template_manager import TemplateManager
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.providers.airports import AirportsProvider
from core.providers.geocoding import GeocodingProvider
from core.providers.radio_id import RadioIdProvider
from core.providers.repeaterbook import RepeaterBookProvider

MAX_UNDO_HISTORY = 20


@dataclass
class UndoSnapshot:
    """Point-in-time snapshot of channel state for Undo Delete / Undo Edit operations."""

    channels: list[RadioChannel]
    raw_channels: list[RadioChannel]
    primary_channels: list[RadioChannel]
    deleted_keys: set[tuple[float, str, str]]
    label: str = "Channel change"


@dataclass
class ActivePlanSession:
    """Stores the most recently assembled plan, undo stack, and map/summary telemetry."""

    recipe: RadioPlannerRecipe | None = None
    codeplug: Codeplug | None = None
    radio_spec: TargetRadioSpec | None = None
    primary_channels: list[RadioChannel] = field(default_factory=list)
    raw_channels: list[RadioChannel] = field(default_factory=list)
    deleted_keys: set[tuple[float, str, str]] = field(default_factory=set)
    map_data: dict[str, Any] = field(default_factory=dict)
    summary_data: dict[str, Any] = field(default_factory=dict)
    notices: list[dict[str, str]] = field(default_factory=list)
    undo_stack: list[UndoSnapshot] = field(default_factory=list)

    def push_undo(self, label: str = "Channel deletion") -> None:
        """Save current channel state onto the bounded undo stack."""
        if not self.codeplug:
            return
        snap = UndoSnapshot(
            channels=list(self.codeplug.channels),
            raw_channels=list(self.raw_channels),
            primary_channels=list(self.primary_channels),
            deleted_keys=set(self.deleted_keys),
            label=label,
        )
        self.undo_stack.append(snap)
        if len(self.undo_stack) > MAX_UNDO_HISTORY:
            self.undo_stack = self.undo_stack[-MAX_UNDO_HISTORY:]

    def pop_undo(self) -> UndoSnapshot | None:
        """Pop and return the most recent undo snapshot, if any."""
        if not self.undo_stack:
            return None
        return self.undo_stack.pop()


class WebWorkspace:
    """Centralized managers and providers for the FastAPI web application."""

    def __init__(self) -> None:
        initialize_startup_environment()
        self.radio_mgr = RadioManager()
        self.prefs_mgr = PreferencesManager()
        self.template_mgr = TemplateManager()
        self.geocoder = GeocodingProvider()
        self.repeater_provider = RepeaterBookProvider(api_key=self.prefs_mgr.tokens.repeaterBookApiKey)
        if self.repeater_provider.api_key and not self.prefs_mgr.tokens.repeaterBookApiKey:
            self.prefs_mgr.tokens = self.prefs_mgr.tokens.model_copy(
                update={"repeaterBookApiKey": self.repeater_provider.api_key}
            )
            self.prefs_mgr.save_tokens(self.prefs_mgr.tokens)
        self.airports_provider = AirportsProvider()
        self.radio_id_provider = RadioIdProvider()
        self.session = ActivePlanSession()


workspace = WebWorkspace()
