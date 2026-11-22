"""Rich UI component renderers: panels, split views, tables, and error diagnostics."""

from __future__ import annotations

from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from cli.ui.theme import make_channel_badges
from core.config.recipe import RadioPlannerRecipe
from core.config.yaml_loader import YamlDiagnosticError
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.providers.geocoding import GeoPoint
from core.providers.repeaterbook import US_STATE_ABBR
from core.sanitizers.condenser import NameCondenser

US_AND_CA_STATE_ABBR: dict[str, str] = {
    **US_STATE_ABBR,
    "alberta": "AB",
    "british columbia": "BC",
    "manitoba": "MB",
    "new brunswick": "NB",
    "newfoundland": "NL",
    "newfoundland and labrador": "NL",
    "northwest territories": "NT",
    "nova scotia": "NS",
    "nunavut": "NU",
    "ontario": "ON",
    "prince edward island": "PE",
    "quebec": "QC",
    "saskatchewan": "SK",
    "yukon": "YT",
    "yukon territory": "YT",
}


def format_location(city: str | None, state: str | None) -> str:
    """Format location string as 'City, ST' using standard 2-letter state abbreviation."""
    city_str = (city or "").strip()
    state_str = (state or "").strip()

    if not city_str and not state_str:
        return "-"

    # If city already includes state abbreviation (e.g. "Tyler, TX")
    if "," in city_str:
        parts = [p.strip() for p in city_str.split(",", 1)]
        st = parts[1].lower()
        st_abbr = US_AND_CA_STATE_ABBR.get(st, parts[1].upper() if len(parts[1]) == 2 else parts[1])
        return f"{parts[0]}, {st_abbr}"

    # Resolve state abbreviation
    st_abbr = ""
    if state_str:
        st_lower = state_str.lower()
        if st_lower in US_AND_CA_STATE_ABBR:
            st_abbr = US_AND_CA_STATE_ABBR[st_lower]
        elif len(state_str) == 2 and state_str.isalpha():
            st_abbr = state_str.upper()
        else:
            st_abbr = state_str

    if city_str and st_abbr:
        return f"{city_str}, {st_abbr}"
    elif city_str:
        return city_str
    elif st_abbr:
        return st_abbr
    return "-"


def render_header(
    console: Console,
    title: str = "RadioPlanner",
    subtitle: str = "Travel Corridor & Codeplug Generator",
    clear_screen: bool = True,
) -> None:
    """Render clean, styled application header banner after clearing the screen."""
    if clear_screen:
        console.clear()
    header_text = Text()
    header_text.append("[RADIO] ", style="bold gold1")
    header_text.append(title, style="bold cyan")
    header_text.append(" -- ", style="dim")
    header_text.append(subtitle, style="italic green")

    console.print(Panel(header_text, border_style="cyan", padding=(0, 2)))


def render_config_panel(
    console: Console,
    recipe: RadioPlannerRecipe,
    title: str = "Active Configuration Preview",
) -> None:
    """Render intermittent configuration snapshot panel showing current choices."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(style="white")

    table.add_row("Plan Name:", recipe.name)
    table.add_row("Operating Mode:", recipe.mode)
    table.add_row("Target Radio ID:", recipe.radio_target.radio_id)

    if recipe.mode == "ROUTE_CORRIDOR" and recipe.corridor:
        wps = " -> ".join(recipe.corridor.waypoints)
        table.add_row("Corridor Waypoints:", wps)
        table.add_row("Corridor Width:", f"{recipe.corridor.corridor_width_miles} miles")
    elif recipe.mode == "PROXIMITY_SEARCH" and recipe.proximity:
        table.add_row("Center Location:", recipe.proximity.center_location)
        table.add_row("Search Radius:", f"{recipe.proximity.radius_miles} miles")
    elif recipe.mode == "AVIATION_PLANNER" and recipe.aviation:
        table.add_row("Aviation Center:", recipe.aviation.center_location)
        table.add_row("Search Radius:", f"{recipe.aviation.radius_miles} miles")

    bands_str = ", ".join(recipe.radio_target.bands)
    modes_str = ", ".join(recipe.radio_target.modes)
    table.add_row("Active Bands:", bands_str)
    table.add_row("Active Modes:", modes_str)
    if recipe.mode in {"ROUTE_CORRIDOR", "PROXIMITY_SEARCH"}:
        access_str = ", ".join(recipe.radio_target.repeater_access or ["OPEN"])
        table.add_row("Repeater Access:", access_str)
    table.add_row("Channel Naming:", getattr(recipe.radio_target, "naming_format", "CITY_FREQ"))
    table.add_row("Include Simplex:", "Yes" if recipe.radio_target.include_simplex else "No")
    table.add_row("Sequence Layout:", " -> ".join(recipe.sequence_order))

    console.print(Panel(table, title=f"[bold]{title}[/bold]", border_style="blue", padding=(1, 2)))


def render_split_summary(
    console: Console,
    title: str,
    waypoints: list[GeoPoint],
    cumulative_miles: list[float],
    total_miles: float,
    band_counts: dict[str, int],
    total_channels: int,
) -> None:
    """Render dual-column summary split view (Spec 3.3)."""
    # Left Column: Route/Location Information
    left_table = Table(title="Route / Corridor Information", border_style="cyan", show_header=True)
    left_table.add_column("#", style="dim", width=4)
    left_table.add_column("Location / City", style="bold white")
    left_table.add_column("Cumulative Miles", justify="right", style="green")

    for idx, (pt, dist) in enumerate(zip(waypoints, cumulative_miles), start=1):
        left_table.add_row(str(idx), pt.name or f"Point {idx}", f"{dist:.1f} mi")

    left_table.add_section()
    left_table.add_row(
        "TOTAL",
        f"{len(waypoints)} Waypoints",
        f"{total_miles:.1f} mi",
        style="bold cyan",
    )

    # Right Column: Frequency Band & Channel Breakdown
    right_table = Table(title="Channel Breakdown", border_style="magenta", show_header=True)
    right_table.add_column("Band / Category", style="bold")
    right_table.add_column("Channels", justify="right", style="bold yellow")

    for band, count in sorted(band_counts.items()):
        right_table.add_row(band, str(count))

    right_table.add_section()
    right_table.add_row("Total Channels", str(total_channels), style="bold green")

    # Render split view in dual columns
    console.print(Columns([left_table, right_table], equal=True))


def render_aviation_summary(
    console: Console,
    title: str = "Aviation Summary",
    airfields: list | None = None,
    distances_miles: list[float] | None = None,
    radius_miles: float = 35.0,
    band_counts: dict[str, int] | None = None,
    total_channels: int = 0,
) -> None:
    """Render dual-column summary for Mode 3 showing matched airfields with distance to airfield and channel breakdown."""
    arpts = airfields or []
    dists = distances_miles or [0.0] * len(arpts)
    bands = band_counts or {}

    # Left Column: Airfields Within Range
    left_table = Table(title="Airfields Within Range", border_style="cyan", show_header=True)
    left_table.add_column("#", style="dim", width=4)
    left_table.add_column("Airport / Airfield", style="bold white")
    left_table.add_column("Distance to Airfield", justify="right", style="green")

    for idx, (arpt, dist) in enumerate(zip(arpts, dists), start=1):
        label = arpt.name if hasattr(arpt, "name") and not hasattr(arpt, "ident") else f"{arpt.ident} ({arpt.name})"
        left_table.add_row(str(idx), label, f"{dist:.1f} mi")

    left_table.add_section()
    left_table.add_row(
        "TOTAL",
        f"{len(arpts)} Airfields",
        f"Max {radius_miles:.1f} mi",
        style="bold cyan",
    )

    # Right Column: Frequency Band & Channel Breakdown
    right_table = Table(title="Channel Breakdown", border_style="magenta", show_header=True)
    right_table.add_column("Band / Category", style="bold")
    right_table.add_column("Channels", justify="right", style="bold yellow")

    for band, count in sorted(bands.items()):
        right_table.add_row(band, str(count))

    right_table.add_section()
    right_table.add_row("Total Channels", str(total_channels), style="bold green")

    # Render split view in dual columns
    console.print(Columns([left_table, right_table], equal=True))


def render_proximity_summary(
    console: Console,
    title: str = "Proximity Summary",
    center_name: str = "Center",
    radius_miles: float = 50.0,
    rings: dict[int, list] | None = None,
    ring_ranges: dict[int, tuple[float, float]] | None = None,
    band_counts: dict[str, int] | None = None,
    total_channels: int = 0,
) -> None:
    """Render dual-column summary for Mode 2 showing concentric distance rings and band breakdown."""
    rings_map = rings or {}
    ranges_map = ring_ranges or {}
    bands = band_counts or {}

    # Left Column: Concentric Distance Rings Information
    left_table = Table(title="Distance Rings Information", border_style="cyan", show_header=True)
    left_table.add_column("Ring", style="bold cyan", width=8)
    left_table.add_column("Distance Range", style="white", width=18)
    left_table.add_column("Channels", justify="right", style="green")

    for ring_idx in sorted(rings_map.keys()):
        ch_list = rings_map[ring_idx]
        if ring_idx in ranges_map:
            d_start, d_end = ranges_map[ring_idx]
            rng_str = f"{d_start:.1f} - {d_end:.1f} mi"
        else:
            rng_str = f"Ring {ring_idx}"
        left_table.add_row(f"Ring {ring_idx}", rng_str, f"{len(ch_list)} channels")

    left_table.add_section()
    total_rpt = sum(len(ch_list) for ch_list in rings_map.values())
    left_table.add_row(
        "TOTAL",
        f"Up to {radius_miles:.1f} mi",
        f"{total_rpt} repeaters",
        style="bold cyan",
    )

    # Right Column: Frequency Band & Channel Breakdown
    right_table = Table(title="Channel Breakdown", border_style="magenta", show_header=True)
    right_table.add_column("Band / Category", style="bold")
    right_table.add_column("Channels", justify="right", style="bold yellow")

    for band, count in sorted(bands.items()):
        right_table.add_row(band, str(count))

    right_table.add_section()
    right_table.add_row("Total Channels", str(total_channels), style="bold green")

    # Render split view in dual columns
    console.print(Columns([left_table, right_table], equal=True))


def render_review_table(
    console: Console,
    codeplug: Codeplug,
    max_display: int | None = None,
    target_spec: TargetRadioSpec | None = None,
    naming_format: str = "CITY_FREQ",
    clear_screen: bool = True,
) -> None:
    """Render Channel Review Table with color-coded badges and details."""
    if clear_screen:
        render_header(console, subtitle="Codeplug Channel Review")

    table = Table(
        title=f"Codeplug Channel Review: {codeplug.name} ({codeplug.total_channels} channels)",
        border_style="blue",
        show_lines=False,
    )
    table.add_column("Slot", justify="right", style="cyan", width=5)
    table.add_column("Badges", width=20)
    table.add_column("Name", style="bold white", width=16)
    table.add_column("RX (MHz)", justify="right", style="green", width=10)
    table.add_column("TX (MHz)", justify="right", style="dim green", width=10)
    table.add_column("Tone / DCS", width=12)
    table.add_column("Location", style="italic", width=20)

    channels_to_show = codeplug.channels if max_display is None else codeplug.channels[:max_display]
    for ch in channels_to_show:
        badges = make_channel_badges(ch)
        tone_str = (
            ch.ctcss if ch.toneMode.upper() in {"TONE", "TSQL"} else ch.dcs if ch.toneMode.upper() == "DCS" else "-"
        )
        loc_str = format_location(ch.city, ch.state)
        ch_name = (
            NameCondenser.condense_channel(ch, target_spec, naming_format=naming_format)
            if target_spec
            else ch.name
        )

        table.add_row(
            str(ch.number),
            badges,
            ch_name,
            f"{ch.rxFreq:.5f}",
            f"{ch.txFreq:.5f}",
            tone_str,
            loc_str,
        )

    console.print(table)


def render_yaml_error(console: Console, err: YamlDiagnosticError) -> None:
    """Render high-visibility YAML diagnostic error panel with code snippet and tips."""
    content_items = []

    msg_text = Text(f"Error: {err.message}\n", style="bold red")
    content_items.append(msg_text)

    if err.snippet:
        content_items.append(Text("Context Snippet:\n", style="bold yellow"))
        content_items.append(Syntax(err.snippet, "yaml", line_numbers=False, theme="ansi_dark"))
        content_items.append(Text("\n"))

    if err.suggestion:
        tip_text = Text()
        tip_text.append("[Tip] Fix Suggestion: ", style="bold green")
        tip_text.append(err.suggestion, style="white")
        content_items.append(tip_text)

    loc_str = f" [Line {err.line}, Col {err.column}]" if err.line is not None else ""
    title = f"[!] YAML Configuration Syntax Error{loc_str}"

    console.print(Panel(Group(*content_items), title=title, border_style="red", padding=(1, 2)))
