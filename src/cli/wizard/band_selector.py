"""Interactive Frequency Band Selector for Target Radio Hardware."""

from __future__ import annotations

from typing import List, Optional, Set

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from cli.ui.renderers import render_header
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

    console.clear()
    render_header(console, subtitle="Radio Configuration")

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


REPEATER_ACCESS_OPTIONS: list[tuple[str, str]] = [
    ("OPEN", "Open Repeaters (Publicly accessible to all licensed amateurs)"),
    ("CLOSED", "Closed Repeaters (Club / member access required)"),
    ("PRIVATE", "Private Repeaters (Owner permission required)"),
]


def select_repeater_access(
    console: Console,
    default_access: Optional[List[str]] = None,
) -> Optional[List[str]]:
    """Prompt user to select and toggle repeater access types (OPEN, CLOSED, PRIVATE)."""
    supported = [item[0] for item in REPEATER_ACCESS_OPTIONS]
    active: Set[str] = {
        x.strip().upper() for x in (default_access or ["OPEN"]) if x.strip().upper() in supported
    } or {"OPEN"}

    console.clear()
    render_header(console, subtitle="Repeater Access Configuration")

    while True:
        console.print("\n[bold cyan]═══ Select Repeater Access Types (OPEN / CLOSED / PRIVATE) ═══[/bold cyan]")
        table = Table(border_style="cyan", show_lines=False)
        table.add_column("#", justify="right", style="cyan", width=4)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Access Type", style="bold white", width=14)
        table.add_column("Description", style="dim")

        for idx, (code, desc) in enumerate(REPEATER_ACCESS_OPTIONS, start=1):
            is_active = code in active
            status_badge = "[bold green][X][/bold green]" if is_active else "[dim][ ][/dim]"
            table.add_row(str(idx), status_badge, code, desc)

        active_sorted = [code for code in supported if code in active]
        active_summary = ", ".join(active_sorted) if active_sorted else "[italic red]None selected[/italic red]"
        panel = Panel(
            table,
            title=f"Active Repeater Access Filter: {active_summary}",
            border_style="blue",
        )
        console.print(panel)

        console.print("\n[bold cyan]Access Selection Actions:[/bold cyan]")
        console.print("  [C] [bold green]Confirm Repeater Access & Continue[/bold green]")
        console.print("  [A] Select All (OPEN, CLOSED, PRIVATE)")
        console.print("  [O] Open Only (Default)")
        console.print("  [1-3] Toggle Access Type")
        console.print("  [B] Back / Cancel")

        valid_choices = ["C", "c", "A", "a", "O", "o", "B", "b", "Q", "q", "1", "2", "3"]
        choice = Prompt.ask(
            "Select action or number to toggle",
            choices=valid_choices,
            default="C",
        ).strip().upper()

        if choice in {"B", "Q"}:
            return None
        elif choice == "C":
            if not active:
                console.print("[red]At least one repeater access type must be selected.[/red]")
                continue
            return [code for code in supported if code in active]
        elif choice == "A":
            active = set(supported)
        elif choice == "O":
            active = {"OPEN"}
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(supported):
                code = supported[idx]
                if code in active:
                    active.remove(code)
                else:
                    active.add(code)


NAMING_FORMAT_OPTIONS: list[tuple[str, str, str]] = [
    ("CITY_FREQ", "City + Frequency", "Shortened city name + '.xx' frequency suffix"),
    ("CALLSIGN_FREQ", "Callsign + Frequency", "Repeater callsign + '.xx' frequency suffix"),
    ("CALLSIGN", "Callsign Only", "Repeater station callsign only"),
    ("CITY", "City Only", "City / town name only (no frequency suffix)"),
    ("STANDARD", "Standard / Full Name", "Full channel name abbreviated to fit LCD"),
]

AVIATION_NAMING_FORMAT_OPTIONS: list[tuple[str, str, str]] = [
    ("IDENT_TYPE", "Airport ID + Service Type", "ICAO/FAA Identifier + Service (e.g. KTYR ATIS / KTYRAT)"),
    ("CITY_TYPE", "City + Service Type", "Municipality + Service (e.g. Tyler ATIS / TyleAT)"),
    ("IDENT_FREQ", "Airport ID + Frequency", "ICAO/FAA Identifier + '.xx' frequency suffix"),
    ("IDENT_ONLY", "Airport ID Only", "ICAO/FAA Airport Identifier only (e.g. KTYR)"),
]


def select_channel_naming_format(
    console: Console,
    spec: TargetRadioSpec,
    default_format: str = "CITY_FREQ",
) -> Optional[str]:
    """Prompt user to select or verify channel naming format with live LCD preview for the target radio."""
    from core.models.channel import RadioChannel
    from core.sanitizers.condenser import NameCondenser

    valid_codes = [item[0] for item in NAMING_FORMAT_OPTIONS]
    active_format = (default_format or "CITY_FREQ").strip().upper()
    if active_format not in valid_codes:
        active_format = "CITY_FREQ"

    sample_ch = RadioChannel(
        number=1,
        name="Tyler 147.20",
        callsign="W5ETX",
        rxFreq=147.20,
        txFreq=147.80,
        city="Tyler",
        state="TX",
    )

    console.clear()
    render_header(console, subtitle="Channel Naming Configuration")

    while True:
        console.print(
            f"\n[bold cyan]═══ Select Channel Naming Format for {spec.brand} {spec.model} (Max {spec.maxNameLength} chars) ═══[/bold cyan]"
        )
        table = Table(border_style="cyan", show_lines=False)
        table.add_column("#", justify="right", style="cyan", width=4)
        table.add_column("Active", justify="center", width=8)
        table.add_column("Naming Format", style="bold white", width=22)
        table.add_column(f"Sample ({spec.maxNameLength}c LCD)", style="bold yellow", width=18)
        table.add_column("Description", style="dim")

        for idx, (code, label, desc) in enumerate(NAMING_FORMAT_OPTIONS, start=1):
            is_active = code == active_format
            status_badge = "[bold green][X][/bold green]" if is_active else "[dim][ ][/dim]"
            preview = NameCondenser.condense_channel(sample_ch, spec, naming_format=code)
            table.add_row(str(idx), status_badge, label, f"'{preview}'", desc)

        active_label = next((lbl for c, lbl, _ in NAMING_FORMAT_OPTIONS if c == active_format), active_format)
        panel = Panel(
            table,
            title=f"Hardware: {spec.brand} {spec.model} ({spec.maxNameLength}-char LCD) | Active Format: [bold green]{active_label}[/bold green]",
            border_style="blue",
        )
        console.print(panel)

        console.print("\n[bold cyan]Channel Naming Actions:[/bold cyan]")
        console.print("  [C] [bold green]Confirm Channel Naming Format & Continue[/bold green]")
        console.print(f"  [1-{len(NAMING_FORMAT_OPTIONS)}] Select Naming Format")
        console.print("  [B] Back / Cancel")

        valid_choices = ["C", "c", "B", "b", "Q", "q"] + [str(i) for i in range(1, len(NAMING_FORMAT_OPTIONS) + 1)]
        choice = Prompt.ask(
            "Select action or format number",
            choices=valid_choices,
            default="C",
        ).strip().upper()

        if choice in {"B", "Q"}:
            return None
        elif choice == "C":
            return active_format
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(NAMING_FORMAT_OPTIONS):
                active_format = NAMING_FORMAT_OPTIONS[idx][0]
                console.clear()
                render_header(console, subtitle="Channel Naming Configuration")


