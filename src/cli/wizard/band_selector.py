"""Interactive Frequency Band Selector for Target Radio Hardware."""

from __future__ import annotations

from typing import List, Optional, Set

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from core.models.radio_spec import TargetRadioSpec

BAND_DESCRIPTIONS: dict[str, str] = {
    "10m": "28.0 - 29.7 MHz (HF Amateur)",
    "6m": "50.0 - 54.0 MHz (VHF Amateur)",
    "2m": "144.0 - 148.0 MHz (VHF Amateur Primary)",
    "1.25m": "222.0 - 225.0 MHz (220 MHz Amateur)",
    "70cm": "420.0 - 450.0 MHz (UHF Amateur Primary)",
    "GMRS": "462.0 - 468.0 MHz (GMRS / FRS)",
    "Airband": "108.0 - 137.0 MHz (Civil Aviation AM)",
    "WX": "162.400 - 162.550 MHz (NOAA Weather Radio)",
}


def select_bands_for_radio(
    console: Console,
    spec: TargetRadioSpec,
    default_bands: Optional[List[str]] = None,
    mode_name: str = "Route Corridor",
) -> Optional[List[str]]:
    """Prompt user to select and toggle active frequency bands for the chosen target radio."""
    supported = list(spec.supportedBands)
    if not supported:
        return []

    # Determine initial active set according to Spec 2.3
    if default_bands is not None:
        active: Set[str] = set(default_bands).intersection(set(supported))
    elif mode_name.lower().startswith("aviat"):
        # Aviation Planner: Airband AM only
        active = {"Airband"}.intersection(set(supported)) or set(supported)
    else:
        # Route Corridor & Proximity: All supported bands EXCEPT Airband
        active = {b for b in supported if b.lower() != "airband"}

    while True:
        console.print(f"\n[bold cyan]═══ Select Active Frequency Bands for {spec.brand} {spec.model} ═══[/bold cyan]")
        table = Table(border_style="cyan", show_lines=True)
        table.add_column("#", justify="right", style="cyan", width=4)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Band", style="bold white", width=12)
        table.add_column("Frequency Range & Description", style="dim")

        for idx, band in enumerate(supported, start=1):
            is_active = band in active
            status_badge = "[bold green][X][/bold green]" if is_active else "[dim][ ][/dim]"
            desc = BAND_DESCRIPTIONS.get(band, "Supported Frequency Band")
            if band.lower() == "airband" and not is_active and not mode_name.lower().startswith("aviat"):
                desc += " [italic yellow](Excluded by default for land travel)[/italic yellow]"
            table.add_row(str(idx), status_badge, band, desc)

        active_sorted = [b for b in supported if b in active]
        active_summary = ", ".join(active_sorted) if active_sorted else "[italic red]None selected[/italic red]"
        panel = Panel(
            table,
            title=f"Hardware: {spec.brand} {spec.model} | Active Bands: {active_summary}",
            border_style="blue",
        )
        console.print(panel)

        console.print("\n[bold cyan]Band Selection Actions:[/bold cyan]")
        console.print("  [C] [bold green]Confirm Active Bands & Continue[/bold green]")
        console.print("  [A] Select All Bands")
        console.print("  [N] Deselect All Bands")
        console.print(f"  [1-{len(supported)}] Toggle Band Selection")
        console.print("  [B] Back / Cancel")

        valid_choices = ["C", "c", "A", "a", "N", "n", "B", "b", "Q", "q"] + [str(i) for i in range(1, len(supported) + 1)]
        choice = Prompt.ask(
            "Select action or number to toggle",
            choices=valid_choices,
            default="C",
        ).strip().upper()

        if choice in {"B", "Q"}:
            return None
        elif choice == "C":
            if not active:
                console.print("[red]At least one frequency band must be selected.[/red]")
                continue
            return [b for b in supported if b in active]
        elif choice == "A":
            active = set(supported)
        elif choice == "N":
            active = set()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(supported):
                b = supported[idx]
                if b in active:
                    active.remove(b)
                else:
                    active.add(b)
