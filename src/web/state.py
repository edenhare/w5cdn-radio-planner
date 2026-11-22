"""Active workspace state manager for the FastAPI + HTMX web interface."""

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


@dataclass
class ActivePlanSession:
    """Stores the most recently assembled plan and raw channels for instant HTMX updates and CSV export."""

    recipe: RadioPlannerRecipe | None = None
    codeplug: Codeplug | None = None
    radio_spec: TargetRadioSpec | None = None
    primary_channels: list[RadioChannel] = field(default_factory=list)
    raw_channels: list[RadioChannel] = field(default_factory=list)
    deleted_keys: set[tuple[float, str, str]] = field(default_factory=set)
    map_data: dict[str, Any] = field(default_factory=dict)
    summary_data: dict[str, Any] = field(default_factory=dict)


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
