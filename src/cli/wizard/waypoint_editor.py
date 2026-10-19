"""Interactive Route Validation and Waypoint Editor."""

from __future__ import annotations

from typing import List, Optional

from rich.console import Console
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from core.providers.geocoding import GeocodingProvider, GeoPoint, haversine_distance


def validate_and_edit_route(
    console: Console,
    initial_waypoints: List[str],
    geocoder: GeocodingProvider,
) -> Optional[List[str]]:
    """Validate route waypoints and provide interactive editing for typos, order, and stops."""
    waypoints = list(initial_waypoints)

    while True:
        console.print("\n[bold cyan]Route Waypoints Validation:[/bold cyan]")
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
            "[bold green]OK[/bold green]" if not has_errors and len(waypoints) >= 2 else "[bold red]ACTION REQ[/bold red]",
        )
        console.print(table)

        if has_errors:
            console.print("[bold red]⚠️  One or more waypoints could not be resolved. Please correct spelling.[/bold red]")
        elif len(waypoints) < 2:
            console.print("[bold red]⚠️  At least 2 waypoints are required to form a travel corridor.[/bold red]")

        console.print("\n[bold cyan]Waypoint Editor Actions:[/bold cyan]")
        if not has_errors and len(waypoints) >= 2:
            console.print("  [C] [bold green]Confirm Route & Proceed to Radio Selection[/bold green]")
        console.print("  [1] Edit / Correct spelling of a waypoint")
        console.print("  [2] Add a new waypoint")
        console.print("  [3] Remove a waypoint")
        console.print("  [4] Reorder / Swap waypoint positions")
        console.print("  [5] Reverse route direction")
        console.print("  [Q] Cancel / Return to Main Menu")

        valid_choices = ["1", "2", "3", "4", "5", "Q", "q", "esc", "ESC"]
        if not has_errors and len(waypoints) >= 2:
            valid_choices.extend(["C", "c"])

        action = Prompt.ask("Choose action", choices=valid_choices, default="C" if (not has_errors and len(waypoints) >= 2) else "1").strip().upper()

        if action in {"Q", "ESC"}:
            return None
        elif action == "C":
            return waypoints
        elif action == "1":
            idx = IntPrompt.ask(f"Enter waypoint number to edit (1-{len(waypoints)})", default=1)
            if 1 <= idx <= len(waypoints):
                curr = waypoints[idx - 1]
                new_val = Prompt.ask(f"Enter corrected location for stop #{idx}", default=curr)
                if new_val.strip():
                    waypoints[idx - 1] = new_val.strip()
        elif action == "2":
            new_wp = Prompt.ask("Enter new waypoint location (e.g. 'Longview, TX')")
            if new_wp.strip():
                pos_choice = Prompt.ask("Where should it be inserted? [B]eginning, [E]nd, or [A]fter stop number", choices=["B", "b", "E", "e", "A", "a"], default="E").upper()
                if pos_choice == "B":
                    waypoints.insert(0, new_wp.strip())
                elif pos_choice == "E":
                    waypoints.append(new_wp.strip())
                else:
                    after_idx = IntPrompt.ask(f"Insert after stop number (1-{len(waypoints)})", default=len(waypoints))
                    waypoints.insert(min(len(waypoints), max(0, after_idx)), new_wp.strip())
        elif action == "3":
            if len(waypoints) <= 1:
                console.print("[red]Cannot delete only waypoint.[/red]")
                continue
            idx = IntPrompt.ask(f"Enter waypoint number to delete (1-{len(waypoints)})", default=len(waypoints))
            if 1 <= idx <= len(waypoints):
                removed = waypoints.pop(idx - 1)
                console.print(f"[yellow]Removed stop #{idx}: {removed}[/yellow]")
        elif action == "4":
            if len(waypoints) < 2:
                console.print("[red]Need at least 2 waypoints to reorder.[/red]")
                continue
            from_idx = IntPrompt.ask(f"Select waypoint to move (1-{len(waypoints)})", default=1)
            to_idx = IntPrompt.ask(f"Move stop #{from_idx} to position (1-{len(waypoints)})", default=2)
            if 1 <= from_idx <= len(waypoints) and 1 <= to_idx <= len(waypoints):
                item = waypoints.pop(from_idx - 1)
                waypoints.insert(to_idx - 1, item)
                console.print(f"[green]Moved '{item}' to position #{to_idx}.[/green]")
        elif action == "5":
            waypoints.reverse()
            console.print("[green]Reversed route direction![/green]")
