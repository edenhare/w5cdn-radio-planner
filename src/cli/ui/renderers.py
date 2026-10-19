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
from core.providers.geocoding import GeoPoint


def render_header(
    console: Console,
    title: str = "RadioPlanner",
    subtitle: str = "Travel Corridor & Codeplug Generator",
) -> None:
    """Render clean, styled application header banner."""
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
        table.add_row(
            "Corridor Width:", f"{recipe.corridor.corridor_width_miles} miles"
        )
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
    table.add_row(
        "Include Simplex:", "Yes" if recipe.radio_target.include_simplex else "No"
    )
    table.add_row("Sequence Layout:", " -> ".join(recipe.sequence_order))

    console.print(
        Panel(
            table, title=f"[bold]{title}[/bold]", border_style="blue", padding=(1, 2)
        )
    )


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
    left_table = Table(
        title="Route / Corridor Information", border_style="cyan", show_header=True
    )
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
    right_table = Table(
        title="Channel Breakdown", border_style="magenta", show_header=True
    )
    right_table.add_column("Band / Category", style="bold")
    right_table.add_column("Channels", justify="right", style="bold yellow")

    for band, count in sorted(band_counts.items()):
        right_table.add_row(band, str(count))

    right_table.add_section()
    right_table.add_row("Total Channels", str(total_channels), style="bold green")

    # Render split view in dual columns
    console.print(Columns([left_table, right_table], equal=True))


def render_review_table(
    console: Console, codeplug: Codeplug, max_display: int = 50
) -> None:
    """Render Channel Review Table with color-coded badges and details."""
    table = Table(
        title=f"Codeplug Channel Review: {codeplug.name} ({codeplug.total_channels} channels)",
        border_style="blue",
        show_lines=True,
    )
    table.add_column("Slot", justify="right", style="cyan", width=5)
    table.add_column("Badges", width=22)
    table.add_column("Name", style="bold white", width=16)
    table.add_column("RX (MHz)", justify="right", style="green", width=10)
    table.add_column("TX (MHz)", justify="right", style="dim green", width=10)
    table.add_column("Tone / DCS", width=12)
    table.add_column("Location", style="italic", width=14)
    table.add_column("Comment", style="dim", overflow="ellipsis")

    channels_to_show = codeplug.channels[:max_display]
    for ch in channels_to_show:
        badges = make_channel_badges(ch)
        tone_str = (
            ch.ctcss
            if ch.toneMode.upper() in {"TONE", "TSQL"}
            else ch.dcs
            if ch.toneMode.upper() == "DCS"
            else "-"
        )
        loc_str = f"{ch.city or ''}, {ch.state or ''}".strip(", ")

        table.add_row(
            str(ch.number),
            badges,
            ch.name,
            f"{ch.rxFreq:.5f}",
            f"{ch.txFreq:.5f}",
            tone_str,
            loc_str,
            ch.comment,
        )

    console.print(table)
    if codeplug.total_channels > max_display:
        remaining = codeplug.total_channels - max_display
        console.print(
            f"[dim italic]... and {remaining} more channels not shown in preview.[/dim italic]"
        )


def render_yaml_error(console: Console, err: YamlDiagnosticError) -> None:
    """Render high-visibility YAML diagnostic error panel with code snippet and tips."""
    content_items = []

    msg_text = Text(f"Error: {err.message}\n", style="bold red")
    content_items.append(msg_text)

    if err.snippet:
        content_items.append(Text("Context Snippet:\n", style="bold yellow"))
        content_items.append(
            Syntax(err.snippet, "yaml", line_numbers=False, theme="ansi_dark")
        )
        content_items.append(Text("\n"))

    if err.suggestion:
        tip_text = Text()
        tip_text.append("[Tip] Fix Suggestion: ", style="bold green")
        tip_text.append(err.suggestion, style="white")
        content_items.append(tip_text)

    loc_str = f" [Line {err.line}, Col {err.column}]" if err.line is not None else ""
    title = f"[!] YAML Configuration Syntax Error{loc_str}"

    console.print(
        Panel(Group(*content_items), title=title, border_style="red", padding=(1, 2))
    )
