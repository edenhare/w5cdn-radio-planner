"""Interactive Rich Console Wizard orchestrating multi-step RadioPlanner workflow."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

from cli.ui.renderers import (
    render_config_panel,
    render_header,
    render_review_table,
    render_split_summary,
)
from core.config.paths import get_recipes_dir
from core.config.recipe import (
    AviationConfig,
    CorridorConfig,
    ProximityConfig,
    RadioPlannerRecipe,
    RadioTargetConfig,
)
from core.engines.aviation import AviationEngine
from core.engines.proximity import ProximityEngine
from core.engines.route_corridor import RouteCorridorEngine
from core.engines.sequence import SequenceOrganizer
from core.exporters import export_codeplug
from core.managers.preferences_manager import PreferencesManager
from core.managers.radio_manager import RadioManager
from core.models.codeplug import Codeplug
from core.providers.airports import AirportsProvider
from core.providers.geocoding import GeocodingProvider, GeoPoint
from core.providers.radio_id import RadioIdProvider
from core.providers.repeaterbook import RepeaterBookProvider
from core.sanitizers.sanitizer import DataSanitizer


class InteractiveWizard:
    """Guides user through mode selection, parameter input, configuration review, and export."""

    def __init__(self, console: Console | None = None):
        import sys

        if sys.platform == "win32":
            try:
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                if hasattr(sys.stderr, "reconfigure"):
                    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        self.console = console or Console()
        # Initialize startup environment in user's home directory (~/.config/radioplanner)
        from core.config.paths import initialize_startup_environment

        was_initialized, actions = initialize_startup_environment()
        self.startup_actions = actions if was_initialized else []

        self.radio_mgr = RadioManager()
        self.prefs_mgr = PreferencesManager()
        self.geocoder = GeocodingProvider()
        self.repeater_provider = RepeaterBookProvider()
        self.airports_provider = AirportsProvider()
        self.radio_id_provider = RadioIdProvider()

    def start(self) -> None:
        """Main interaction loop."""
        if self.startup_actions:
            items = "\n".join(f"  [green]*[/green] {act}" for act in self.startup_actions)
            self.console.print(
                Panel(
                    f"[white]First-time initialization completed in [bold cyan]~/.config/radioplanner/[/bold cyan]:[/white]\n\n{items}",
                    title="[bold green]Workspace Ready[/bold green]",
                    border_style="green",
                )
            )
            self.startup_actions = []

        while True:
            render_header(self.console)
            self.console.print("\n[bold cyan]Select Application Operating Mode:[/bold cyan]")
            self.console.print("  [1] Highway Route Corridor Mode (Sequenced repeaters along route)")
            self.console.print("  [2] Radial Proximity Ring Search Mode (5 Concentric distance bands)")
            self.console.print("  [3] Local Aviation & Airport Planner Mode (CTAF, Tower, Ground, ATIS)")
            self.console.print("  [4] Replay Saved Configuration Recipe")
            self.console.print("  [5] Radios & Hardware Manager")
            self.console.print("  [6] User Preferences & API Tokens")
            self.console.print("  [0] Exit")

            choice = Prompt.ask(
                "\nChoose an option",
                choices=["0", "1", "2", "3", "4", "5", "6"],
                default="1",
            )

            if choice == "0":
                self.console.print("[green]Goodbye![/green]")
                break
            elif choice == "1":
                self._flow_route_corridor()
            elif choice == "2":
                self._flow_proximity()
            elif choice == "3":
                self._flow_aviation()
            elif choice == "4":
                self._flow_replay_recipe()
            elif choice == "5":
                self._flow_radios_manager()
            elif choice == "6":
                self._flow_preferences()

    def _select_target_radio(self, default_id: str | None = None) -> str:
        """Prompt user to select a target radio from available specifications."""
        radios = self.radio_mgr.list_radios()
        self.console.print("\n[bold cyan]Target Radio Hardware Models:[/bold cyan]")
        for idx, r in enumerate(radios, start=1):
            self.console.print(
                f"  [{idx}] [bold white]{r.brand} {r.model}[/bold white] — {r.description} (Max {r.maxChannels} ch, LCD {r.maxNameLength} chars)"
            )

        radio_ids = [r.id for r in radios]
        default_index = "1"
        if default_id and default_id in radio_ids:
            default_index = str(radio_ids.index(default_id) + 1)

        choice_idx = IntPrompt.ask("Select target radio number", default=int(default_index))
        if 1 <= choice_idx <= len(radios):
            return radios[choice_idx - 1].id
        return radios[0].id

    def _flow_route_corridor(self) -> None:
        """Mode 1: Highway Route Corridor Wizard."""
        self.console.print("\n[bold green]═══ Mode 1: Highway Route Corridor ═══[/bold green]")
        self.console.print(
            "[dim]Enter travel waypoints separated by semicolons (e.g. 'Tyler, TX; Shreveport, LA; Jackson, MS').[/dim]"
        )

        waypoints_input = Prompt.ask("Waypoints", default="Tyler, TX; Shreveport, LA; Jackson, MS")
        waypoints = [w.strip() for w in waypoints_input.split(";") if w.strip()]
        if len(waypoints) < 2:
            self.console.print("[red]At least 2 waypoints are required.[/red]")
            return

        corridor_width = float(Prompt.ask("Corridor search width in miles", default="25.0"))
        include_simplex = Confirm.ask("Include National Calling & Simplex frequencies?", default=True)

        radio_id = self._select_target_radio(self.prefs_mgr.preferences.defaultRadioId)
        radio_spec = self.radio_mgr.get_radio(radio_id)

        start_city = waypoints[0].split(",")[0].strip()
        end_city = waypoints[-1].split(",")[0].strip()
        plan_name = f"{start_city}_to_{end_city}_Corridor"

        recipe = RadioPlannerRecipe(
            mode="ROUTE_CORRIDOR",
            name=plan_name,
            corridor=CorridorConfig(waypoints=waypoints, corridor_width_miles=corridor_width),
            radio_target=RadioTargetConfig(
                radio_id=radio_id,
                programmer_format=radio_spec.programmerType,
                include_simplex=include_simplex,
                bands=radio_spec.supportedBands,
                modes=radio_spec.supportedModes,
            ),
            sequence_order=[
                "TEMPLATE:builtin_calling_channels",
                "ROUTE_PLAN",
                "TEMPLATE:builtin_noaa_wx_channels",
            ],
        )

        # Show intermittent configuration preview
        render_config_panel(self.console, recipe, title="Route Corridor Configuration")
        if not Confirm.ask("Proceed with route calculation?", default=True):
            return

        with self.console.status("[bold green]Calculating travel corridor repeaters...[/bold green]"):
            engine = RouteCorridorEngine(geocoder=self.geocoder)
            all_repeaters = self.repeater_provider.get_repeaters_near(32.0, -94.0, radius_miles=500.0)
            res = engine.plan_route(
                waypoint_names=waypoints,
                candidate_channels=all_repeaters,
                corridor_width_miles=corridor_width,
                include_simplex=include_simplex,
            )
            codeplug = SequenceOrganizer.assemble(
                codeplug_name=recipe.name,
                sequence_keys=recipe.sequence_order,
                primary_channels=res.channels,
                target_spec=radio_spec,
            )

        # Show Split Summary
        render_split_summary(
            self.console,
            title="Route Summary",
            waypoints=res.waypoints,
            cumulative_miles=res.cumulative_mileages,
            total_miles=res.total_distance_miles,
            band_counts=res.channel_counts_by_band,
            total_channels=codeplug.total_channels,
        )

        self._channel_review_and_export_loop(codeplug, recipe, radio_spec)

    def _flow_proximity(self) -> None:
        """Mode 2: Radial Proximity Ring Search Wizard."""
        self.console.print("\n[bold green]═══ Mode 2: Radial Proximity Ring Search ═══[/bold green]")
        center_loc = Prompt.ask("Center location / city", default="Dallas, TX")
        radius = float(Prompt.ask("Search radius in miles", default="50.0"))
        include_simplex = Confirm.ask("Include Simplex & Calling frequencies?", default=True)

        radio_id = self._select_target_radio(self.prefs_mgr.preferences.defaultRadioId)
        radio_spec = self.radio_mgr.get_radio(radio_id)

        city_clean = center_loc.split(",")[0].strip()
        plan_name = f"{city_clean}_Proximity_{int(radius)}mi"

        recipe = RadioPlannerRecipe(
            mode="PROXIMITY_SEARCH",
            name=plan_name,
            proximity=ProximityConfig(center_location=center_loc, radius_miles=radius),
            radio_target=RadioTargetConfig(
                radio_id=radio_id,
                programmer_format=radio_spec.programmerType,
                include_simplex=include_simplex,
                bands=radio_spec.supportedBands,
                modes=radio_spec.supportedModes,
            ),
            sequence_order=[
                "TEMPLATE:builtin_calling_channels",
                "PROXIMITY_PLAN",
                "TEMPLATE:builtin_noaa_wx_channels",
            ],
        )

        # Show intermittent configuration preview
        render_config_panel(self.console, recipe, title="Proximity Search Configuration")
        if not Confirm.ask("Proceed with proximity search?", default=True):
            return

        with self.console.status("[bold green]Searching 5 concentric proximity rings...[/bold green]"):
            engine = ProximityEngine(geocoder=self.geocoder)
            all_repeaters = self.repeater_provider.get_repeaters_near(32.0, -94.0, radius_miles=500.0)
            res = engine.search_proximity(
                center_location=center_loc,
                candidate_channels=all_repeaters,
                radius_miles=radius,
                include_simplex=include_simplex,
            )
            codeplug = SequenceOrganizer.assemble(
                codeplug_name=recipe.name,
                sequence_keys=recipe.sequence_order,
                primary_channels=res.channels,
                target_spec=radio_spec,
            )

        # Summary view
        render_split_summary(
            self.console,
            title="Proximity Summary",
            waypoints=[res.center_point],
            cumulative_miles=[0.0],
            total_miles=res.radius_miles,
            band_counts=res.channel_counts_by_band,
            total_channels=codeplug.total_channels,
        )

        self._channel_review_and_export_loop(codeplug, recipe, radio_spec)

    def _flow_aviation(self) -> None:
        """Mode 3: Local Aviation Planner Wizard."""
        self.console.print("\n[bold green]═══ Mode 3: Local Aviation & Airport Planner ═══[/bold green]")
        center_loc = Prompt.ask("Target city or airport", default="Tyler, TX")
        radius = float(Prompt.ask("Search radius in miles", default="35.0"))

        radio_id = self._select_target_radio(self.prefs_mgr.preferences.defaultRadioId)
        radio_spec = self.radio_mgr.get_radio(radio_id)

        city_clean = center_loc.split(",")[0].strip()
        plan_name = f"{city_clean}_Aviation_{int(radius)}mi"

        recipe = RadioPlannerRecipe(
            mode="AVIATION_PLANNER",
            name=plan_name,
            aviation=AviationConfig(center_location=center_loc, radius_miles=radius),
            radio_target=RadioTargetConfig(
                radio_id=radio_id,
                programmer_format=radio_spec.programmerType,
                include_simplex=False,
                bands=["Airband"],
                modes=["AM"],
            ),
            sequence_order=["AVIATION_BLOCK"],
        )

        # Show intermittent configuration preview
        render_config_panel(self.console, recipe, title="Aviation Planner Configuration")
        if not Confirm.ask("Proceed with airport query?", default=True):
            return

        with self.console.status("[bold green]Querying local airport frequencies...[/bold green]"):
            engine = AviationEngine(geocoder=self.geocoder, airports_provider=self.airports_provider)
            res = engine.plan_aviation(center_location=center_loc, radius_miles=radius)
            codeplug = SequenceOrganizer.assemble(
                codeplug_name=recipe.name,
                sequence_keys=recipe.sequence_order,
                primary_channels=res.channels,
                target_spec=radio_spec,
            )

        # Aviation Summary
        arpt_pts = [
            GeoPoint(lat=a.latitude, lon=a.longitude, name=f"{a.ident} ({a.name})") for a in res.matched_airports
        ]
        render_split_summary(
            self.console,
            title="Aviation Summary",
            waypoints=arpt_pts,
            cumulative_miles=[0.0] * len(arpt_pts),
            total_miles=res.radius_miles,
            band_counts={"Airband": len(res.channels)},
            total_channels=codeplug.total_channels,
        )

        self._channel_review_and_export_loop(codeplug, recipe, radio_spec)

    def _flow_replay_recipe(self) -> None:
        """Mode 4: Replay a saved configuration recipe."""
        recipes_dir = get_recipes_dir()
        yaml_files = list(recipes_dir.glob("*.yaml"))

        if not yaml_files:
            self.console.print(f"[yellow]No saved recipes found in {recipes_dir}.[/yellow]")
            manual_path = Prompt.ask(
                "Enter path to custom YAML recipe file (or press Enter to return)",
                default="",
            )
            if not manual_path:
                return
            target_path = Path(manual_path)
        else:
            self.console.print("\n[bold cyan]Saved Recipes in ~/.config/radioplanner/recipes/:[/bold cyan]")
            for idx, f in enumerate(yaml_files, start=1):
                self.console.print(f"  [{idx}] {f.name}")
            pick = IntPrompt.ask("Select recipe number", default=1)
            target_path = yaml_files[pick - 1]

        try:
            recipe = RadioPlannerRecipe.from_yaml_file(target_path)
            self.console.print(f"[green]Successfully loaded recipe '{recipe.name}'![/green]")
            render_config_panel(self.console, recipe, title=f"Loaded Recipe: {target_path.name}")

            from core.runner import RecipeRunner

            runner = RecipeRunner(
                radio_manager=self.radio_mgr,
                repeater_provider=self.repeater_provider,
                airports_provider=self.airports_provider,
                geocoder=self.geocoder,
            )
            codeplug, out_file = runner.run(recipe)
            self.console.print(f"[bold green]✔ Codeplug successfully exported to: {out_file}[/bold green]")
            render_review_table(self.console, codeplug)
        except Exception as exc:
            self.console.print(f"[bold red]Failed to execute recipe: {exc}[/bold red]")

    def _flow_radios_manager(self) -> None:
        """View available radio hardware specifications."""
        radios = self.radio_mgr.list_radios()
        self.console.print(f"\n[bold cyan]Registered Radio Hardware Models ({len(radios)}):[/bold cyan]")
        for r in radios:
            self.console.print(
                f"- [bold white]{r.brand} {r.model}[/bold white] (ID: `{r.id}`)\n"
                f"  Programmer: {r.programmerType} | Max Channels: {r.maxChannels} | Name Limit: {r.maxNameLength} chars\n"
                f"  Bands: {', '.join(r.supportedBands)} | Modes: {', '.join(r.supportedModes)}\n"
            )
        Prompt.ask("Press Enter to return to main menu", default="")

    def _flow_preferences(self) -> None:
        """View and edit user preferences."""
        prefs = self.prefs_mgr.preferences
        self.console.print("\n[bold cyan]Current User Preferences:[/bold cyan]")
        self.console.print(f"  Callsign: {prefs.callsign}")
        self.console.print(f"  Operator Name: {prefs.operatorName}")
        self.console.print(f"  Primary DMR ID: {prefs.primaryDmrId or 'Not configured'}")
        self.console.print(f"  Distance Unit: {prefs.distanceUnit}")
        self.console.print(f"  Default Radio ID: {prefs.defaultRadioId}")

        if Confirm.ask("Edit preferences now?", default=False):
            new_call = Prompt.ask("Amateur Callsign", default=prefs.callsign)
            new_dmr = Prompt.ask("Primary DMR ID", default=prefs.primaryDmrId or "")
            new_prefs = prefs.model_copy(update={"callsign": new_call, "primaryDmrId": new_dmr or None})
            self.prefs_mgr.save_preferences(new_prefs)
            self.console.print("[green]Preferences saved![/green]")

    def _channel_review_and_export_loop(self, codeplug: Codeplug, recipe: RadioPlannerRecipe, spec) -> None:
        """Interactive review table actions loop."""
        current_codeplug = codeplug

        while True:
            self.console.print("\n[bold cyan]Codeplug Actions:[/bold cyan]")
            self.console.print("  [R] Review Channel Table (Badges, Frequencies, Tones)")
            self.console.print("  [E] Export Codeplug CSV to Disk")
            self.console.print("  [D] DMR Talkgroup Expansion / Duplication")
            self.console.print("  [S] Save Configuration Recipe to YAML (for re-running)")
            self.console.print("  [C] Inspect Current Configuration Preview")
            self.console.print("  [B] Back to Main Menu")

            act = Prompt.ask(
                "Choose action",
                choices=["R", "r", "E", "e", "D", "d", "S", "s", "C", "c", "B", "b"],
                default="R",
            ).upper()

            if act == "R":
                dynamic_display = max(10, self.console.height - 10)
                render_review_table(self.console, current_codeplug, max_display=dynamic_display)
            elif act == "C":
                render_config_panel(self.console, recipe, title="Current Active Configuration")
            elif act == "E":
                date_str = datetime.now().strftime("%m%d%y")
                out_dir = Path("./exports").resolve()
                out_dir.mkdir(parents=True, exist_ok=True)
                default_name = f"{DataSanitizer.sanitize_filename(recipe.name)}-{spec.id}-{date_str}.csv"
                file_name = Prompt.ask("Output CSV filename", default=default_name)
                dest = out_dir / file_name
                export_codeplug(current_codeplug, spec, dest)
                self.console.print(f"[bold green]✔ Codeplug exported successfully to: {dest}[/bold green]")
            elif act == "D":
                # Find DMR channels in codeplug
                dmr_channels = [ch for ch in current_codeplug.channels if ch.mode.upper() == "DMR"]
                if not dmr_channels:
                    self.console.print("[yellow]No DMR channels found in active codeplug.[/yellow]")
                    continue
                self.console.print(
                    f"[cyan]Found {len(dmr_channels)} DMR channel(s). Duplicating with standard Talkgroups...[/cyan]"
                )
                expanded = []
                for ch in current_codeplug.channels:
                    if ch.mode.upper() == "DMR":
                        expanded.extend(self.radio_id_provider.duplicate_channel_for_talkgroups(ch))
                    else:
                        expanded.append(ch)
                current_codeplug = Codeplug(name=current_codeplug.name, channels=expanded).renumbered()
                self.console.print(
                    f"[green]Talkgroups expanded! Total channels now: {current_codeplug.total_channels}[/green]"
                )
            elif act == "S":
                recipes_dir = get_recipes_dir()
                recipes_dir.mkdir(parents=True, exist_ok=True)
                recipe_filename = f"{DataSanitizer.sanitize_filename(recipe.name)}.yaml"
                dest_yaml = Prompt.ask("Save recipe file path", default=str(recipes_dir / recipe_filename))
                recipe.to_yaml_file(dest_yaml)
                self.console.print(f"[bold green]✔ Configuration recipe saved to: {dest_yaml}[/bold green]")
                self.console.print(
                    f"[dim]Run this recipe again any time with: [bold white]radioplanner --config {dest_yaml}[/bold white][/dim]"
                )
            elif act == "B":
                break
