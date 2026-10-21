"""Execution runner for replayable RadioPlanner recipes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.config.recipe import RadioPlannerRecipe
from core.engines.aviation import AviationEngine
from core.engines.proximity import ProximityEngine
from core.engines.route_corridor import RouteCorridorEngine
from core.engines.sequence import SequenceOrganizer
from core.exporters import export_codeplug
from core.managers.radio_manager import RadioManager
from core.models.codeplug import Codeplug
from core.providers.airports import AirportsProvider
from core.providers.geocoding import GeocodingProvider
from core.providers.repeaterbook import (
    RepeaterBookProvider,
    identify_states_for_proximity,
    identify_states_for_route,
)
from core.sanitizers.sanitizer import DataSanitizer


class RecipeRunner:
    """Executes a RadioPlannerRecipe and generates hardware-compliant codeplug files."""

    def __init__(
        self,
        radio_manager: RadioManager | None = None,
        repeater_provider: RepeaterBookProvider | None = None,
        airports_provider: AirportsProvider | None = None,
        geocoder: GeocodingProvider | None = None,
    ):
        self.radio_manager = radio_manager or RadioManager()
        self.repeater_provider = repeater_provider or RepeaterBookProvider()
        self.airports_provider = airports_provider or AirportsProvider()
        self.geocoder = geocoder or GeocodingProvider()

    def run(self, recipe: RadioPlannerRecipe, base_output_dir: Path | str | None = None) -> tuple[Codeplug, Path]:
        """Execute a recipe and export the resulting codeplug CSV."""
        errors = recipe.validate_for_execution()
        if errors:
            raise ValueError("Recipe validation failed:\n" + "\n".join(f"- {e}" for e in errors))

        # 1. Retrieve target radio spec
        radio_spec = self.radio_manager.get_radio(recipe.radio_target.radio_id)

        # Apply recipe band/mode overrides if specified
        if recipe.radio_target.bands:
            radio_spec = radio_spec.model_copy(update={"supportedBands": recipe.radio_target.bands})
        if recipe.radio_target.modes:
            radio_spec = radio_spec.model_copy(update={"supportedModes": recipe.radio_target.modes})
        if recipe.radio_target.programmer_format:
            radio_spec = radio_spec.model_copy(update={"programmerType": recipe.radio_target.programmer_format})

        # 2. Execute Mode Engine
        date_str = datetime.now().strftime("%m%d%y")

        if recipe.mode == "ROUTE_CORRIDOR":
            corridor = recipe.corridor  # guaranteed not None by validation
            engine = RouteCorridorEngine(geocoder=self.geocoder)
            geo_points = []
            for wp in corridor.waypoints:
                try:
                    geo_points.append(self.geocoder.resolve(wp))
                except Exception:
                    pass
            route_states = identify_states_for_route(
                corridor.waypoints,
                geo_points=geo_points,
                corridor_width_miles=corridor.corridor_width_miles,
            )
            all_repeaters = self.repeater_provider.get_repeaters_for_states(
                states=route_states,
                allowed_use=recipe.radio_target.repeater_access,
            )

            result = engine.plan_route(
                waypoint_names=corridor.waypoints,
                candidate_channels=all_repeaters,
                corridor_width_miles=corridor.corridor_width_miles,
                include_simplex=recipe.radio_target.include_simplex,
            )
            primary_channels = result.channels
            start_city = DataSanitizer.sanitize_filename(corridor.waypoints[0].split(",")[0])
            end_city = DataSanitizer.sanitize_filename(corridor.waypoints[-1].split(",")[0])
            default_filename = f"{start_city}-{end_city}-route-{radio_spec.id}-{date_str}.csv"

        elif recipe.mode == "PROXIMITY_SEARCH":
            proximity = recipe.proximity
            engine = ProximityEngine(geocoder=self.geocoder)
            try:
                center_pt = self.geocoder.resolve(proximity.center_location)
            except Exception:
                center_pt = None
            prox_states = identify_states_for_proximity(
                proximity.center_location,
                center_point=center_pt,
                radius_miles=proximity.radius_miles,
            )
            all_repeaters = self.repeater_provider.get_repeaters_for_states(
                states=prox_states,
                allowed_use=recipe.radio_target.repeater_access,
            )

            result = engine.search_proximity(
                center_location=proximity.center_location,
                candidate_channels=all_repeaters,
                radius_miles=proximity.radius_miles,
                include_simplex=recipe.radio_target.include_simplex,
            )
            primary_channels = result.channels
            center_city = DataSanitizer.sanitize_filename(proximity.center_location.split(",")[0])
            default_filename = f"{center_city}-proximity-{radio_spec.id}-{date_str}.csv"

        elif recipe.mode == "AVIATION_PLANNER":
            aviation = recipe.aviation
            engine = AviationEngine(geocoder=self.geocoder, airports_provider=self.airports_provider)

            result = engine.plan_aviation(
                center_location=aviation.center_location,
                radius_miles=aviation.radius_miles,
            )
            primary_channels = result.channels
            center_city = DataSanitizer.sanitize_filename(aviation.center_location.split(",")[0])
            default_filename = f"{center_city}-aviation-{radio_spec.id}-{date_str}.csv"

        else:
            primary_channels = []
            default_filename = f"{DataSanitizer.sanitize_filename(recipe.name)}-{date_str}.csv"

        # 3. Assemble Codeplug using sequence positions
        codeplug = SequenceOrganizer.assemble(
            codeplug_name=recipe.name,
            sequence_keys=recipe.sequence_order,
            primary_channels=primary_channels,
            target_spec=radio_spec,
        )

        # 4. Determine output file path
        out_dir = Path(base_output_dir or recipe.export.output_dir).resolve()
        filename = recipe.export.filename_pattern or default_filename
        dest_file = out_dir / filename

        export_codeplug(codeplug, radio_spec, dest_file)
        return codeplug, dest_file
