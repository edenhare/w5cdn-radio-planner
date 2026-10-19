"""Interactive Rich Console Wizard orchestrating multi-step RadioPlanner workflow."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from cli.ui.menu import DynamicMenu, PreferenceItem, prompt_choice_from_list
from cli.ui.renderers import (
    render_config_panel,
    render_header,
    render_review_table,
    render_split_summary,
)
from cli.wizard.radio_selector import select_target_radio_hierarchical
from cli.wizard.sequence_editor import select_and_sequence_blocks
from cli.wizard.waypoint_editor import validate_and_edit_route
from core.config.paths import get_recipes_dir, initialize_startup_environment
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
from core.managers.template_manager import TemplateManager
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.models.template import PresetTemplateFile
from core.providers.airports import AirportsProvider
from core.providers.geocoding import GeocodingProvider, GeoPoint, haversine_distance
from core.providers.radio_id import RadioIdProvider
from core.providers.repeaterbook import RepeaterBookProvider
from core.sanitizers.sanitizer import DataSanitizer
from core.special_channels import filter_channels_for_radio


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
        was_initialized, actions = initialize_startup_environment()
        self.startup_actions = actions if was_initialized else []

        self.radio_mgr = RadioManager()
        self.prefs_mgr = PreferencesManager()
        self.template_mgr = TemplateManager()
        self.geocoder = GeocodingProvider()
        self.repeater_provider = RepeaterBookProvider()
        self.airports_provider = AirportsProvider()
        self.radio_id_provider = RadioIdProvider()

    def start(self) -> None:
        """Main interaction loop using dynamic numbered menu."""
        self.console.clear()
        try:
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
                main_menu = DynamicMenu("Select Application Operating Mode")
                main_menu.add(
                    "Highway Route Corridor Mode (Sequenced repeaters along route)",
                    self._flow_route_corridor,
                )
                main_menu.add(
                    "Radial Proximity Ring Search Mode (5 Concentric distance bands)",
                    self._flow_proximity,
                )
                main_menu.add(
                    "Local Aviation & Airport Planner Mode (CTAF, Tower, Ground, ATIS)",
                    self._flow_aviation,
                )
                main_menu.add(
                    "Preset Codeplug Templates Manager (Calling, NOAA WX, Custom)",
                    self._flow_templates_manager,
                )
                main_menu.add(
                    "Radios & Hardware Manager (Specs, limits, custom models)",
                    self._flow_radios_manager,
                )
                main_menu.add("User Preferences & API Tokens", self._flow_preferences)
                main_menu.add("Replay Saved Configuration Recipe", self._flow_replay_recipe)
                main_menu.add("Exit", lambda: "EXIT", key="0")

                try:
                    result = main_menu.show_and_execute(self.console, default="1")
                    if result == "EXIT":
                        self.console.print("[green]Goodbye![/green]")
                        break
                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Submenu cancelled. Returning to main menu.[/yellow]")
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Operation cancelled by user. Goodbye![/yellow]")

    def _select_target_radio(self, default_id: str | None = None) -> str | None:
        """Prompt user to select a target radio using two-stage Brand -> Model multi-column selector."""
        return select_target_radio_hierarchical(self.console, self.radio_mgr, default_id)

    def _flow_route_corridor(self) -> None:
        """Mode 1: Highway Route Corridor Wizard."""
        self.console.clear()
        self.console.print("\n[bold green]═══ Mode 1: Highway Route Corridor ═══[/bold green]")

        default_waypoints = ["Tyler, TX", "Shreveport, LA", "Jackson, MS"]
        validated = validate_and_edit_route(self.console, default_waypoints, self.geocoder)
        if not validated or len(validated) < 2:
            self.console.print("[yellow]Route planning cancelled or incomplete.[/yellow]")
            return
        waypoints = validated

        # Clear screen and display top-level banner with summary of waypoint count & route distance
        self.console.clear()
        render_header(self.console)

        total_route_miles = 0.0
        prev_pt = None
        for wp in waypoints:
            try:
                pt = self.geocoder.resolve(wp)
                if prev_pt:
                    total_route_miles += haversine_distance(prev_pt, pt, unit="MILES")
                prev_pt = pt
            except Exception:
                pass

        summary_panel = Panel(
            f"[bold white]Waypoints Count:[/bold white] [bold cyan]{len(waypoints)} stops[/bold cyan]   |   "
            f"[bold white]Estimated Highway Distance:[/bold white] [bold green]{total_route_miles:.1f} miles[/bold green]\n"
            f"[dim]Travel Corridor Path:[/dim] [white]{' ➜ '.join(waypoints)}[/white]",
            title="[bold green]Highway Route Corridor Overview[/bold green]",
            border_style="cyan",
        )
        self.console.print(summary_panel)

        # Prompt for corridor search width
        corridor_width = float(Prompt.ask("\nCorridor search width in miles", default="25.0"))
        include_simplex = Confirm.ask("Include Simplex & National Calling frequencies?", default=True)

        # Interactive sequence block and template organizer BEFORE radio selection
        sequence_keys = select_and_sequence_blocks(
            self.console,
            self.template_mgr,
            primary_block_key="ROUTE_PLAN",
            primary_block_title="Highway Route Corridor Repeaters",
        )
        if not sequence_keys:
            self.console.print("[yellow]Sequence selection cancelled.[/yellow]")
            return

        # Select target radio hardware
        radio_id = self._select_target_radio(self.prefs_mgr.preferences.defaultRadioId)
        if not radio_id:
            self.console.print("[yellow]Radio selection cancelled.[/yellow]")
            return

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
            sequence_order=sequence_keys,
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
                template_manager=self.template_mgr,
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
        self.console.clear()
        self.console.print("\n[bold green]═══ Mode 2: Radial Proximity Ring Search ═══[/bold green]")
        center_loc = Prompt.ask("Center location / city", default="Dallas, TX")
        radius = float(Prompt.ask("Search radius in miles", default="50.0"))
        include_simplex = Confirm.ask("Include Simplex & Calling frequencies?", default=True)

        radio_id = self._select_target_radio(self.prefs_mgr.preferences.defaultRadioId)
        if not radio_id:
            self.console.print("[yellow]Radio selection cancelled.[/yellow]")
            return

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
        self.console.clear()
        self.console.print("\n[bold green]═══ Mode 3: Local Aviation & Airport Planner ═══[/bold green]")
        center_loc = Prompt.ask("Target city or airport", default="Tyler, TX")
        radius = float(Prompt.ask("Search radius in miles", default="35.0"))

        radio_id = self._select_target_radio(self.prefs_mgr.preferences.defaultRadioId)
        if not radio_id:
            self.console.print("[yellow]Radio selection cancelled.[/yellow]")
            return

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

    def _flow_templates_manager(self) -> None:
        """Mode 4: Preset Codeplug Templates Manager."""
        self.console.clear()
        while True:
            templates = self.template_mgr.list_templates()
            self.console.print(f"\n[bold cyan]Preset Codeplug Templates ({len(templates)}):[/bold cyan]")

            table = Table(border_style="cyan", show_lines=True)
            table.add_column("#", justify="right", style="cyan", width=4)
            table.add_column("Template ID", style="bold white")
            table.add_column("Name", style="bold white")
            table.add_column("Badge Tag", style="magenta")
            table.add_column("Channels", justify="right", style="green", width=10)
            table.add_column("Source", justify="center", width=14)

            for idx, tpl in enumerate(templates, start=1):
                try:
                    chans = self.template_mgr.get_template_channels(tpl.id)
                    ch_count = len(chans)
                except Exception:
                    ch_count = 0
                is_user = self.template_mgr.is_user_template(tpl.id)
                source_str = "[green]User Custom[/green]" if is_user else "[cyan]App Default[/cyan]"
                table.add_row(
                    str(idx),
                    tpl.id,
                    tpl.name,
                    f"[bold magenta]{tpl.tagText}[/bold magenta]",
                    str(ch_count),
                    source_str,
                )

            self.console.print(table)
            self.console.print("\n[bold cyan]Template Manager Actions:[/bold cyan]")
            self.console.print("  [V] View / Inspect Template Channels")
            self.console.print("  [E] Export Template Directly to Radio Codeplug")
            self.console.print("  [D] Edit / Customize Template (Copy to User Config)")
            self.console.print("  [I] Import / Add Custom CSV Channel Template")
            self.console.print("  [X] Delete User Custom Template")
            self.console.print("  [B] Back to Main Menu")

            act = Prompt.ask(
                "Choose action",
                choices=["V", "v", "E", "e", "D", "d", "I", "i", "X", "x", "B", "b"],
                default="B",
            ).upper()

            if act == "B":
                break
            elif act == "V":
                pick = IntPrompt.ask(f"Select template number (1-{len(templates)})", default=1)
                if 1 <= pick <= len(templates):
                    tpl = templates[pick - 1]
                    chans = self.template_mgr.get_template_channels(tpl.id)
                    dummy_codeplug = Codeplug(name=tpl.name, channels=chans)
                    dynamic_height = max(10, self.console.height - 10)
                    render_review_table(self.console, dummy_codeplug, max_display=dynamic_height)
            elif act == "E":
                pick = IntPrompt.ask(f"Select template number to export (1-{len(templates)})", default=1)
                if 1 <= pick <= len(templates):
                    tpl = templates[pick - 1]
                    chans = self.template_mgr.get_template_channels(tpl.id)
                    radio_id = self._select_target_radio(self.prefs_mgr.preferences.defaultRadioId)
                    if not radio_id:
                        continue
                    spec = self.radio_mgr.get_radio(radio_id)
                    filtered = filter_channels_for_radio(chans, spec)
                    codeplug = Codeplug(name=tpl.name, channels=filtered).renumbered()
                    recipe = RadioPlannerRecipe(
                        mode="PRESET_TEMPLATES",
                        name=tpl.name,
                        radio_target=RadioTargetConfig(
                            radio_id=radio_id,
                            programmer_format=spec.programmerType,
                            include_simplex=True,
                            bands=spec.supportedBands,
                            modes=spec.supportedModes,
                        ),
                        sequence_order=[f"TEMPLATE:{tpl.id}"],
                    )
                    self._channel_review_and_export_loop(codeplug, recipe, spec)
            elif act == "D":
                pick = IntPrompt.ask(f"Select template number to edit/customize (1-{len(templates)})", default=1)
                if 1 <= pick <= len(templates):
                    tpl = templates[pick - 1]
                    is_user = self.template_mgr.is_user_template(tpl.id)
                    if not is_user:
                        self.console.print(
                            f"[cyan]Customizing app default template '{tpl.name}'.\n"
                            f"An editable copy will be saved to ~/.config/radioplanner/templates/{tpl.id}.json\n"
                            f"which will override the app default template.[/cyan]"
                        )
                    else:
                        self.console.print(
                            f"[cyan]Editing user template '{tpl.name}' (~/.config/radioplanner/templates/{tpl.id}.json):[/cyan]"
                        )
                    new_name = Prompt.ask("Template Display Name", default=tpl.name)
                    new_tag = Prompt.ask("Badge Tag Label", default=tpl.tagText).upper()
                    new_desc = Prompt.ask("Description", default=tpl.description)

                    replace_csv = Confirm.ask(
                        "Do you want to update/replace the channel CSV content from a file?", default=False
                    )
                    raw_csv = tpl.rawCsvContent
                    csv_filename = tpl.fileName
                    if replace_csv:
                        csv_path_str = Prompt.ask("Enter path to new CSV channel file")
                        csv_path = Path(csv_path_str.strip())
                        if csv_path.is_file():
                            raw_csv = csv_path.read_text(encoding="utf-8")
                            csv_filename = csv_path.name
                        else:
                            self.console.print(
                                f"[yellow]File not found: {csv_path}. Retaining existing channel data.[/yellow]"
                            )

                    updated_tpl = PresetTemplateFile(
                        id=tpl.id,
                        name=new_name,
                        description=new_desc,
                        tagText=new_tag,
                        tagColorHex=tpl.tagColorHex,
                        fileName=csv_filename,
                        rawCsvContent=raw_csv,
                    )
                    saved_path = self.template_mgr.save_template(updated_tpl)
                    self.console.print(f"[bold green]✔ Template '{updated_tpl.name}' saved to: {saved_path}[/bold green]")
            elif act == "I":
                self.console.print("\n[bold cyan]Import Custom CSV Template:[/bold cyan]")
                csv_path_str = Prompt.ask("Enter path to CSV channel file (e.g. ./my_channels.csv)")
                csv_path = Path(csv_path_str.strip())
                if not csv_path.is_file():
                    self.console.print(f"[red]File not found: {csv_path}[/red]")
                    continue
                tpl_id = Prompt.ask("Template ID slug (e.g. custom_skywarn)", default=csv_path.stem.lower())
                name = Prompt.ask("Template Display Name", default=csv_path.stem.replace("_", " ").title())
                tag = Prompt.ask("Badge Tag Label (e.g. SKYWARN, ARES, SAR)", default="CUSTOM").upper()
                desc = Prompt.ask("Description", default="Custom user imported channel list")
                raw_csv = csv_path.read_text(encoding="utf-8")
                new_tpl = PresetTemplateFile(
                    id=tpl_id,
                    name=name,
                    description=desc,
                    tagText=tag,
                    tagColorHex="#4CAF50",
                    fileName=csv_path.name,
                    rawCsvContent=raw_csv,
                )
                self.template_mgr.save_template(new_tpl)
                self.console.print(f"[bold green]✔ Template '{name}' imported and saved![/bold green]")
            elif act == "X":
                user_tpls = [t for t in templates if self.template_mgr.is_user_template(t.id)]
                if not user_tpls:
                    self.console.print(
                        "[yellow]No custom user templates found to delete. (App default templates cannot be deleted).[/yellow]"
                    )
                    continue
                self.console.print("\n[bold cyan]Custom User Templates:[/bold cyan]")
                for i, t in enumerate(user_tpls, start=1):
                    self.console.print(f"  [{i}] {t.name} (`{t.id}`) [{t.tagText}]")
                pick_del = IntPrompt.ask(f"Select template to delete (1-{len(user_tpls)})", default=1)
                if 1 <= pick_del <= len(user_tpls):
                    to_del = user_tpls[pick_del - 1]
                    if Confirm.ask(
                        f"Are you sure you want to delete user template '{to_del.name}' (`{to_del.id}`)?", default=False
                    ):
                        self.template_mgr.delete_user_template(to_del.id)
                        if self.template_mgr.has_template(to_del.id):
                            self.console.print(
                                f"[green]✔ User template '{to_del.id}' deleted. Restored application default template.[/green]"
                            )
                        else:
                            self.console.print(f"[green]✔ User template '{to_del.id}' deleted.[/green]")

    def _flow_radios_manager(self) -> None:
        """Mode 5: Radios & Hardware Specifications Manager."""
        self.console.clear()
        while True:
            radios = self.radio_mgr.list_radios()
            self.console.print(f"\n[bold cyan]Configured Radio Hardware Specifications ({len(radios)}):[/bold cyan]")

            table = Table(border_style="cyan", show_lines=True)
            table.add_column("#", justify="right", style="cyan", width=4)
            table.add_column("Brand", style="bold white")
            table.add_column("Model", style="bold white")
            table.add_column("ID", style="italic")
            table.add_column("Programmer", style="yellow")
            table.add_column("Max Ch", justify="right", style="green", width=8)
            table.add_column("LCD Limit", justify="right", style="cyan", width=10)
            table.add_column("Supported Bands", style="dim")
            table.add_column("Type", justify="center", width=9)

            for idx, r in enumerate(radios, start=1):
                is_user = self.radio_mgr.is_user_radio(r.id)
                type_badge = "[green]User[/green]" if is_user else "[cyan]Factory[/cyan]"
                table.add_row(
                    str(idx),
                    r.brand,
                    r.model,
                    r.id,
                    r.programmerType,
                    str(r.maxChannels),
                    f"{r.maxNameLength} chars",
                    ", ".join(r.supportedBands),
                    type_badge,
                )

            self.console.print(table)
            self.console.print("\n[bold cyan]Hardware Manager Actions:[/bold cyan]")
            self.console.print("  [I] Inspect Radio Specification & Exporter Columns")
            self.console.print("  [A] Add New Custom Target Radio Model")
            self.console.print("  [E] Edit / Override Radio Limits & Parameters")
            self.console.print("  [D] Delete Custom User Radio")
            self.console.print("  [B] Back to Main Menu")

            act = Prompt.ask(
                "Choose action",
                choices=["I", "i", "A", "a", "E", "e", "D", "d", "B", "b"],
                default="B",
            ).upper()

            if act == "B":
                break
            elif act == "I":
                pick = IntPrompt.ask(f"Select radio number to inspect (1-{len(radios)})", default=1)
                if 1 <= pick <= len(radios):
                    r = radios[pick - 1]
                    is_user = self.radio_mgr.is_user_radio(r.id)
                    col_list = (
                        "\n".join(f"    {i}. {col}" for i, col in enumerate(r.columns, start=1))
                        if r.columns
                        else "    (Default programmer column mappings apply)"
                    )
                    info = (
                        f"[bold white]{r.brand} {r.model}[/bold white] ([dim]{r.id}[/dim])\n"
                        f"Source: {'[green]User Override / Custom[/green]' if is_user else '[cyan]Factory Specification[/cyan]'}\n"
                        f"Description: {r.description}\n"
                        f"Default Programmer: [bold yellow]{r.programmerType}[/bold yellow]\n"
                        f"Memory Limit: [bold green]{r.maxChannels} channels[/bold green]\n"
                        f"LCD Display Limit: [bold cyan]{r.maxNameLength} characters[/bold cyan]\n"
                        f"Allowed Special Characters: `{r.allowedSpecialChars}` (allowDots={r.allowDots}, allowSpaces={r.allowSpaces})\n"
                        f"Supported Bands: {', '.join(r.supportedBands)}\n"
                        f"Supported Modes: {', '.join(r.supportedModes)}\n\n"
                        f"[bold cyan]CSV Exporter Columns ({len(r.columns)} defined):[/bold cyan]\n{col_list}"
                    )
                    self.console.print(
                        Panel(info, title=f"Hardware Specification: {r.brand} {r.model}", border_style="cyan")
                    )
            elif act == "A":
                self.console.print("\n[bold cyan]Add New Target Radio Hardware Model:[/bold cyan]")
                brand = Prompt.ask("Manufacturer / Brand (e.g. Yaesu, Kenwood, Icom)")
                model = Prompt.ask("Model Name (e.g. FT-70DR)")
                default_id = f"{brand.lower().replace(' ', '_')}_{model.lower().replace(' ', '_').replace('-', '_')}"
                radio_id = Prompt.ask("Unique Radio ID Slug", default=default_id)
                desc = Prompt.ask("Description", default=f"{brand} {model} Handheld Transceiver")
                prog = Prompt.ask(
                    "Programmer Format",
                    choices=["CHIRP", "RT_SYSTEMS", "VENDOR_CPS", "GENERIC_CSV"],
                    default="CHIRP",
                )
                max_ch = IntPrompt.ask("Maximum Channel Capacity", default=128)
                max_name = IntPrompt.ask("Max LCD Name Length (characters)", default=8)
                bands_in = Prompt.ask("Supported Bands (comma-separated)", default="2m, 70cm, Airband, WX")
                bands = [b.strip() for b in bands_in.split(",") if b.strip()]
                modes_in = Prompt.ask("Supported Modes (comma-separated)", default="FM, AM")
                modes = [m.strip() for m in modes_in.split(",") if m.strip()]

                new_spec = TargetRadioSpec(
                    id=radio_id,
                    brand=brand,
                    model=model,
                    description=desc,
                    maxChannels=max_ch,
                    maxNameLength=max_name,
                    allowDots=True,
                    allowSpaces=True,
                    allowedSpecialChars=" -_./#",
                    programmerType=prog,
                    supportedBands=bands,
                    supportedModes=modes,
                    columns=[],
                )
                saved_path = self.radio_mgr.save_user_radio(new_spec)
                self.console.print(f"[bold green]✔ New radio '{brand} {model}' saved to: {saved_path}[/bold green]")
            elif act == "E":
                pick = IntPrompt.ask(f"Select radio number to edit/override (1-{len(radios)})", default=1)
                if 1 <= pick <= len(radios):
                    r = radios[pick - 1]
                    self.console.print(
                        f"[cyan]Editing specs for {r.brand} {r.model} (will save override to ~/.config/radioplanner/radios/{r.id}.yaml):[/cyan]"
                    )
                    max_ch = IntPrompt.ask("Max Channel Capacity", default=r.maxChannels)
                    max_name = IntPrompt.ask("Max LCD Name Length", default=r.maxNameLength)
                    prog = Prompt.ask(
                        "Programmer Format",
                        choices=["CHIRP", "RT_SYSTEMS", "VENDOR_CPS", "GENERIC_CSV"],
                        default=r.programmerType,
                    )
                    bands_in = Prompt.ask("Supported Bands", default=", ".join(r.supportedBands))
                    bands = [b.strip() for b in bands_in.split(",") if b.strip()]
                    modes_in = Prompt.ask("Supported Modes", default=", ".join(r.supportedModes))
                    modes = [m.strip() for m in modes_in.split(",") if m.strip()]

                    updated_spec = TargetRadioSpec(
                        id=r.id,
                        brand=r.brand,
                        model=r.model,
                        description=r.description,
                        maxChannels=max_ch,
                        maxNameLength=max_name,
                        allowDots=r.allowDots,
                        allowSpaces=r.allowSpaces,
                        allowedSpecialChars=r.allowedSpecialChars,
                        programmerType=prog,
                        supportedBands=bands,
                        supportedModes=modes,
                        columns=r.columns,
                    )
                    saved_path = self.radio_mgr.save_user_radio(updated_spec)
                    self.console.print(f"[bold green]✔ Specification override saved to: {saved_path}[/bold green]")
            elif act == "D":
                user_radios = [r for r in radios if self.radio_mgr.is_user_radio(r.id)]
                if not user_radios:
                    self.console.print(
                        "[yellow]No custom user radios found to delete. (Factory radios cannot be deleted).[/yellow]"
                    )
                    continue
                self.console.print("\n[bold cyan]Custom User Radios:[/bold cyan]")
                for i, r in enumerate(user_radios, start=1):
                    self.console.print(f"  [{i}] {r.brand} {r.model} (`{r.id}`)")
                pick_del = IntPrompt.ask(f"Select radio to delete (1-{len(user_radios)})", default=1)
                if 1 <= pick_del <= len(user_radios):
                    to_del = user_radios[pick_del - 1]
                    if Confirm.ask(
                        f"Are you sure you want to delete user radio '{to_del.brand} {to_del.model}'?", default=False
                    ):
                        self.radio_mgr.delete_user_radio(to_del.id)
                        self.console.print(f"[green]✔ Radio '{to_del.id}' deleted.[/green]")

    def _edit_callsign(self) -> None:
        val = Prompt.ask("Enter Amateur Callsign", default=self.prefs_mgr.preferences.callsign)
        new_prefs = self.prefs_mgr.preferences.update_settings(callsign=val)
        self.prefs_mgr.save_preferences(new_prefs)
        self.console.print(f"[green]✔ Callsign updated to {new_prefs.callsign}[/green]")

    def _edit_operator_name(self) -> None:
        val = Prompt.ask("Enter Operator Name", default=self.prefs_mgr.preferences.operatorName)
        new_prefs = self.prefs_mgr.preferences.update_settings(operatorName=val.strip())
        self.prefs_mgr.save_preferences(new_prefs)
        self.console.print(f"[green]✔ Operator Name updated to {val.strip()}[/green]")

    def _edit_dmr_id(self) -> None:
        val = Prompt.ask(
            "Enter 7-digit Primary DMR Radio ID (or leave blank to clear)",
            default=self.prefs_mgr.preferences.primaryDmrId or "",
        )
        cleaned = val.strip() or None
        new_prefs = self.prefs_mgr.preferences.update_settings(primaryDmrId=cleaned)
        self.prefs_mgr.save_preferences(new_prefs)
        self.console.print("[green]✔ DMR Radio ID updated[/green]")

    def _edit_distance_units(self) -> None:
        unit = Prompt.ask(
            "Select Distance Unit ([m] for miles, [k] for kilometers)",
            choices=["m", "k", "M", "K"],
            default="m" if self.prefs_mgr.preferences.distanceUnit == "MILES" else "k",
        ).lower()
        new_prefs = self.prefs_mgr.preferences.update_settings(distanceUnit=unit)
        self.prefs_mgr.save_preferences(new_prefs)
        self.console.print(f"[green]✔ Distance Unit set to {new_prefs.distanceUnit}[/green]")

    def _edit_default_radio(self) -> None:
        radios = self.radio_mgr.list_radios()
        self.console.print("\n[bold cyan]Set Default Target Radio:[/bold cyan]")
        self.console.print("  [0] None / Clear default radio")
        for idx, r in enumerate(radios, start=1):
            self.console.print(f"  [{idx}] {r.brand} {r.model} ({r.id})")
        default_choice = "0"
        if self.prefs_mgr.preferences.defaultRadioId:
            for idx, r in enumerate(radios, start=1):
                if r.id == self.prefs_mgr.preferences.defaultRadioId:
                    default_choice = str(idx)
                    break
        radio_pick = Prompt.ask(
            "Select radio number (or 0 for None)",
            choices=[str(i) for i in range(len(radios) + 1)],
            default=default_choice,
        )
        if radio_pick == "0":
            new_prefs = self.prefs_mgr.preferences.update_settings(defaultRadioId=None)
            self.prefs_mgr.save_preferences(new_prefs)
            self.console.print("[green]✔ Default Target Radio set to None[/green]")
        else:
            selected_id = radios[int(radio_pick) - 1].id
            new_prefs = self.prefs_mgr.preferences.update_settings(defaultRadioId=selected_id)
            self.prefs_mgr.save_preferences(new_prefs)
            self.console.print(f"[green]✔ Default Target Radio set to {selected_id}[/green]")

    def _edit_language(self) -> None:
        options = [
            ("ENGLISH", "English"),
            ("SPANISH", "Spanish"),
            ("FRENCH", "French"),
            ("GERMAN", "German"),
        ]
        val = prompt_choice_from_list(
            self.console, "Select Language", options, default_value=self.prefs_mgr.preferences.language
        )
        new_prefs = self.prefs_mgr.preferences.update_settings(language=val)
        self.prefs_mgr.save_preferences(new_prefs)
        self.console.print(f"[green]✔ Language set to {new_prefs.language}[/green]")

    def _edit_color_theme(self) -> None:
        options = [
            ("DARK", "Dark Theme (Standard vibrant colors for dark backgrounds)"),
            ("LIGHT", "Light Theme (Optimized contrast for light backgrounds)"),
            ("HIGH_CONTRAST", "High Contrast / Monochrome"),
        ]
        val = prompt_choice_from_list(
            self.console, "Select UI Color Theme", options, default_value=self.prefs_mgr.preferences.colorTheme
        )
        new_prefs = self.prefs_mgr.preferences.update_settings(colorTheme=val)
        self.prefs_mgr.save_preferences(new_prefs)
        self.console.print(f"[green]✔ Color Theme set to {new_prefs.colorTheme}[/green]")

    def _edit_repeaterbook_key(self) -> None:
        key = Prompt.ask(
            "Enter RepeaterBook API Key (leave empty to clear)",
            default=self.prefs_mgr.tokens.repeaterBookApiKey or "",
        )
        new_tokens = self.prefs_mgr.tokens.model_copy(update={"repeaterBookApiKey": key.strip() or None})
        self.prefs_mgr.save_tokens(new_tokens)
        self.console.print("[green]✔ RepeaterBook API Key saved to ~/.config/radioplanner/tokens[/green]")

    def _edit_radioid_username(self) -> None:
        call = Prompt.ask(
            "Enter RadioID.net Username/Callsign",
            default=self.prefs_mgr.tokens.radioIdUsername or "",
        )
        new_tokens = self.prefs_mgr.tokens.model_copy(update={"radioIdUsername": call.strip() or None})
        self.prefs_mgr.save_tokens(new_tokens)
        self.console.print("[green]✔ RadioID.net Callsign saved[/green]")

    def _edit_radioid_key(self) -> None:
        key = Prompt.ask("Enter RadioID.net API Key", default=self.prefs_mgr.tokens.radioIdApiKey or "")
        new_tokens = self.prefs_mgr.tokens.model_copy(update={"radioIdApiKey": key.strip() or None})
        self.prefs_mgr.save_tokens(new_tokens)
        self.console.print("[green]✔ RadioID.net API Key saved to ~/.config/radioplanner/tokens[/green]")

    def _flow_preferences(self) -> None:
        """View and edit user preferences with numbered item selection."""
        self.console.clear()
        while True:
            prefs = self.prefs_mgr.preferences
            tokens = self.prefs_mgr.tokens

            pref_items = [
                PreferenceItem("Amateur Callsign", lambda: prefs.callsign, self._edit_callsign),
                PreferenceItem("Operator Name", lambda: prefs.operatorName, self._edit_operator_name),
                PreferenceItem(
                    "Primary DMR Radio ID",
                    lambda: prefs.primaryDmrId or "(Not set)",
                    self._edit_dmr_id,
                ),
                PreferenceItem("Distance Units", lambda: prefs.distanceUnit, self._edit_distance_units),
                PreferenceItem(
                    "Default Target Radio",
                    lambda: prefs.defaultRadioId or "(None)",
                    self._edit_default_radio,
                ),
                PreferenceItem("Language", lambda: prefs.language, self._edit_language),
                PreferenceItem("UI Color Theme", lambda: prefs.colorTheme, self._edit_color_theme),
                PreferenceItem(
                    "RepeaterBook API Key",
                    lambda: "*" * len(tokens.repeaterBookApiKey) if tokens.repeaterBookApiKey else "(None)",
                    self._edit_repeaterbook_key,
                ),
                PreferenceItem(
                    "RadioID.net Callsign",
                    lambda: tokens.radioIdUsername or "(None)",
                    self._edit_radioid_username,
                ),
                PreferenceItem(
                    "RadioID.net API Key",
                    lambda: "*" * len(tokens.radioIdApiKey) if tokens.radioIdApiKey else "(None)",
                    self._edit_radioid_key,
                ),
            ]

            self.console.print("\n[bold cyan]User Preferences & Settings:[/bold cyan]")
            for idx, item in enumerate(pref_items, start=1):
                self.console.print(f"  [{idx}] {(item.label + ':'):<26} [bold white]{item.get_value()}[/bold white]")
            self.console.print("  [Q] Return to Main Menu")

            valid_choices = [str(i) for i in range(1, len(pref_items) + 1)] + ["Q", "q", "esc", "ESC", "0"]
            choice = Prompt.ask(
                "\nSelect number to edit (or 'Q'/'esc' to return)",
                choices=valid_choices,
                default="Q",
            ).strip()

            if choice.upper() in {"Q", "ESC", "0", "BACK", "EXIT"}:
                break

            try:
                pick_idx = int(choice) - 1
                if 0 <= pick_idx < len(pref_items):
                    pref_items[pick_idx].edit_action()
            except ValueError:
                self.console.print(f"[yellow]Invalid selection. Enter 1-{len(pref_items)} or 'Q' to return.[/yellow]")

    def _flow_replay_recipe(self) -> None:
        """Mode 7: Replay a saved configuration recipe."""
        self.console.clear()
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
