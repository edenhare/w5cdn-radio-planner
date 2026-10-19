"""Interactive Route Validation and Waypoint Editor."""

from __future__ import annotations

from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from core.providers.geocoding import GeocodingProvider, GeoPoint, haversine_distance


def _input_new_route_wizard(console: Console) -> List[str]:
    """Interactive guided prompt to build a route from scratch."""
    console.print("\n[bold cyan]═══ Plan New Route from Scratch ═══[/bold cyan]")
    start = Prompt.ask("Enter starting city / location (e.g. Austin, TX)").strip()
    dest = Prompt.ask("Enter destination city / location (e.g. Houston, TX)").strip()

    stops: List[str] = []
    if start:
        stops.append(start)
    if dest:
        stops.append(dest)

    console.print("[dim]Add any intermediate stops along the highway (press Enter with no input when done):[/dim]")
    while True:
        inter = Prompt.ask("Add intermediate stop (or Enter to finish)", default="").strip()
        if not inter:
            break
        if len(stops) >= 2:
            stops.insert(-1, inter)  # Insert before destination
        else:
            stops.append(inter)
        console.print(f"[green]Added '{inter}'. Route now has {len(stops)} stops.[/green]")

    return stops


def validate_and_edit_route(
    console: Console,
    initial_waypoints: List[str],
    geocoder: GeocodingProvider,
) -> Optional[List[str]]:
    """Validate route waypoints and provide interactive editing for typos, order, and stops."""
    waypoints = list(initial_waypoints)

    while True:
        console.print("\n[bold cyan]═══ Route Corridor Waypoints ═══[/bold cyan]")

        if not waypoints:
            console.print(
                Panel(
                    "[yellow]No waypoints currently configured for this route.\n"
                    "Select [bold white][N][/bold white] to enter a new route from scratch, or [bold white][A][/bold white] to add a stop.[/yellow]",
                    title="[bold yellow]Empty Route[/bold yellow]",
                    border_style="yellow",
                )
            )
            has_errors = True
        else:
            table = Table(border_style="cyan", show_lines=True)
            table.add_column("#", justify="right", style="cyan", width=4)
            table.add_column("Input Waypoint", style="bold white")
            table.add_column("Resolved Location / Coordinates", style="italic")
            table.add_column("Leg Distance", justify="right", style="green")
            table.add_column("Status", justify="center", width=14)

            resolved_points: List[Optional[GeoPoint]] = []
            has_errors = False
            prev_point: Optional[GeoPoint] = None
            total_miles = 0.0

            for idx, wp in enumerate(waypoints, start=1):
                try:
                    pt = geocoder.resolve(wp)
                    resolved_points.append(pt)
                    coord_str = f"{pt.name or wp} ({pt.lat:.4f}, {pt.lon:.4f})"
                    if prev_point:
                        dist = haversine_distance(prev_point, pt, unit="MILES")
                        total_miles += dist
                        leg_str = f"{dist:.1f} mi"
                    else:
                        leg_str = "Start (0.0 mi)"
                    status_str = "[bold green]✔ Valid[/bold green]"
                    prev_point = pt
                except Exception:
                    resolved_points.append(None)
                    coord_str = "[red]Unknown / Not found[/red]"
                    leg_str = "-"
                    status_str = "[bold red]❌ Unresolved[/bold red]"
                    has_errors = True

                table.add_row(str(idx), wp, coord_str, leg_str, status_str)

            table.add_section()
            table.add_row(
                "TOTAL",
                f"{len(waypoints)} stops",
                "-",
                f"{total_miles:.1f} mi",
                "[bold green]OK[/bold green]"
                if not has_errors and len(waypoints) >= 2
                else "[bold red]ACTION REQ[/bold red]",
            )
            console.print(table)

            if has_errors:
                console.print(
                    "[bold red]⚠️  One or more waypoints could not be resolved. Please edit spelling.[/bold red]"
                )
            elif len(waypoints) < 2:
                console.print("[bold red]⚠️  At least 2 waypoints are required to form a travel corridor.[/bold red]")

        console.print("\n[bold cyan]Waypoint Actions:[/bold cyan]")
        can_confirm = not has_errors and len(waypoints) >= 2
        if can_confirm:
            console.print("  [C] [bold green]Confirm Route & Proceed to Corridor Setup[/bold green]")
        console.print("  [N] New route from scratch (Clear & enter your own stops)")
        console.print("  [E] Edit a waypoint (Correct spelling or location)")
        console.print("  [A] Add / Insert a waypoint")
        console.print("  [D] Delete a waypoint")
        console.print("  [K] Kill / Clear all waypoints")
        console.print("  [R] Reorder / Swap waypoint positions")
        console.print("  [V] Reverse route direction")
        console.print("  [B] Back to Main Menu")

        valid_choices = ["N", "n", "E", "e", "A", "a", "D", "d", "K", "k", "R", "r", "V", "v", "B", "b", "Q", "q", "esc", "ESC"]
        if can_confirm:
            valid_choices.extend(["C", "c"])

        default_choice = "C" if can_confirm else ("N" if not waypoints else "E")
        action = Prompt.ask("Choose action", choices=valid_choices, default=default_choice).strip().upper()

        if action in {"B", "Q", "ESC"}:
            return None
        elif action == "C":
            return waypoints
        elif action == "N":
            new_stops = _input_new_route_wizard(console)
            if new_stops:
                waypoints = new_stops
                console.print(f"[green]New route set with {len(waypoints)} stops.[/green]")
        elif action == "E":
            if not waypoints:
                console.print("[yellow]No waypoints to edit. Use [N] or [A] to add stops.[/yellow]")
                continue
            idx = IntPrompt.ask(f"Enter waypoint number to edit (1-{len(waypoints)})", default=1)
            if 1 <= idx <= len(waypoints):
                curr = waypoints[idx - 1]
                new_val = Prompt.ask(f"Enter corrected location for stop #{idx}", default=curr)
                if new_val.strip():
                    waypoints[idx - 1] = new_val.strip()
        elif action == "A":
            new_wp = Prompt.ask("Enter new waypoint location (e.g. 'Longview, TX')").strip()
            if new_wp:
                if not waypoints:
                    waypoints.append(new_wp)
                else:
                    pos_choice = Prompt.ask(
                        "Where should it be inserted? [B]eginning, [E]nd, or [A]fter stop number",
                        choices=["B", "b", "E", "e", "A", "a"],
                        default="E",
                    ).upper()
                    if pos_choice == "B":
                        waypoints.insert(0, new_wp)
                    elif pos_choice == "E":
                        waypoints.append(new_wp)
                    else:
                        after_idx = IntPrompt.ask(
                            f"Insert after stop number (1-{len(waypoints)})",
                            default=len(waypoints),
                        )
                        waypoints.insert(min(len(waypoints), max(0, after_idx)), new_wp)
        elif action == "D":
            if not waypoints:
                console.print("[yellow]No waypoints to delete.[/yellow]")
                continue
            idx = IntPrompt.ask(f"Enter waypoint number to delete (1-{len(waypoints)})", default=len(waypoints))
            if 1 <= idx <= len(waypoints):
                removed = waypoints.pop(idx - 1)
                console.print(f"[yellow]Removed stop #{idx}: {removed}[/yellow]")
        elif action == "K":
            if not waypoints:
                console.print("[yellow]Waypoints are already empty.[/yellow]")
                continue
            if Confirm.ask("Are you sure you want to clear/kill all waypoints?", default=True):
                waypoints.clear()
                console.print("[yellow]All waypoints cleared.[/yellow]")
        elif action == "R":
            if len(waypoints) < 2:
                console.print("[red]Need at least 2 waypoints to reorder.[/red]")
                continue
            from_idx = IntPrompt.ask(f"Select waypoint to move (1-{len(waypoints)})", default=1)
            to_idx = IntPrompt.ask(f"Move stop #{from_idx} to position (1-{len(waypoints)})", default=2)
            if 1 <= from_idx <= len(waypoints) and 1 <= to_idx <= len(waypoints):
                item = waypoints.pop(from_idx - 1)
                waypoints.insert(to_idx - 1, item)
                console.print(f"[green]Moved '{item}' to position #{to_idx}.[/green]")
        elif action == "V":
            if len(waypoints) < 2:
                console.print("[red]Need at least 2 waypoints to reverse.[/red]")
                continue
            waypoints.reverse()
            console.print("[green]Reversed route direction![/green]")
