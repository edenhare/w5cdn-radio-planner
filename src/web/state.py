"""Active workspace state manager for the RadioPlanner Web Cockpit."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.config.paths import get_radioplanner_home, initialize_startup_environment
from core.config.recipe import RadioPlannerRecipe
from core.managers.preferences_manager import PreferencesManager
from core.managers.radio_manager import RadioManager
from core.managers.template_manager import TemplateManager
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.providers.airports import AirportsProvider
from core.providers.callsign_lookup import CallsignLookupService
from core.providers.geocoding import GeocodingProvider
from core.providers.nws import NwsAlertsService
from core.providers.radio_id import RadioIdProvider
from core.providers.repeaterbook import RepeaterBookProvider

logger = logging.getLogger("radioplanner.state")

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

    def to_persisted_dict(self) -> dict[str, Any]:
        """Serialize active session state to a JSON-compatible dictionary."""
        if not self.recipe or not self.codeplug or not self.radio_spec:
            return {"active": False}
        return {
            "active": True,
            "recipe": self.recipe.model_dump(),
            "codeplug": self.codeplug.model_dump(),
            "radio_spec": self.radio_spec.model_dump(),
            "primary_channels": [ch.model_dump() for ch in self.primary_channels],
            "raw_channels": [ch.model_dump() for ch in self.raw_channels],
            "deleted_keys": [[k[0], k[1], k[2]] for k in sorted(self.deleted_keys)],
            "map_data": self.map_data,
            "summary_data": self.summary_data,
            "notices": self.notices,
        }

    @classmethod
    def from_persisted_dict(cls, data: dict[str, Any]) -> ActivePlanSession:
        """Rehydrate an ActivePlanSession from persisted JSON."""
        if not isinstance(data, dict) or not data.get("active"):
            return cls()
        recipe = RadioPlannerRecipe.model_validate(data["recipe"])
        codeplug = Codeplug.model_validate(data["codeplug"])
        radio_spec = TargetRadioSpec.model_validate(data["radio_spec"])
        primary = [RadioChannel.model_validate(c) for c in data.get("primary_channels", [])]
        raw = [RadioChannel.model_validate(c) for c in data.get("raw_channels", [])]
        deleted: set[tuple[float, str, str]] = set()
        for item in data.get("deleted_keys", []):
            if isinstance(item, list) and len(item) == 3:
                deleted.add((float(item[0]), str(item[1]), str(item[2])))
        return cls(
            recipe=recipe,
            codeplug=codeplug,
            radio_spec=radio_spec,
            primary_channels=primary,
            raw_channels=raw,
            deleted_keys=deleted,
            map_data=dict(data.get("map_data") or {}),
            summary_data=dict(data.get("summary_data") or {}),
            notices=list(data.get("notices") or []),
        )


class WebWorkspace:
    """Centralized managers and providers for the FastAPI web application."""

    def __init__(self, *, load_persisted_session: bool = True) -> None:
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
        self.lookup_service = CallsignLookupService()
        self.nws_service = NwsAlertsService()
        self.session = ActivePlanSession()
        if load_persisted_session:
            self.load_session()

    def session_file_path(self) -> Path:
        return get_radioplanner_home() / "session.json"

    def save_session(self) -> bool:
        """Persist the active codeplug session to ~/.config/radioplanner/session.json."""
        path = self.session_file_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = self.session.to_persisted_dict()
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("Could not persist active session to %s: %s", path, exc)
            return False

    def load_session(self) -> bool:
        """Restore the last active codeplug session if session.json is present and valid."""
        path = self.session_file_path()
        if not path.is_file():
            return False
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            restored = ActivePlanSession.from_persisted_dict(raw)
            if restored.codeplug is not None:
                self.session = restored
                return True
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            logger.debug("Ignoring invalid persisted session %s: %s", path, exc)
        return False

    def reload_all(self) -> None:
        """Reload preferences, tokens, radios, and templates from disk (e.g. after backup restore)."""
        self.prefs_mgr = PreferencesManager()
        self.radio_mgr = RadioManager()
        self.template_mgr = TemplateManager()
        self.repeater_provider.api_key = self.prefs_mgr.tokens.repeaterBookApiKey
        self.repeater_provider.last_status = "CONFIGURED" if self.prefs_mgr.tokens.repeaterBookApiKey else "NO_KEY"
        self.lookup_service.reset_qrz_session()


workspace = WebWorkspace()
