"""Interactive Sequence and Template Block Organizer."""

from __future__ import annotations

from typing import List, Optional

from rich.console import Console
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from core.managers.template_manager import TemplateManager


def select_and_sequence_blocks(
    console: Console,
    template_mgr: TemplateManager,
    primary_block_key: str = "ROUTE_PLAN",
    primary_block_title: str = "Highway Route Corridor Repeaters",
    initial_sequence: Optional[List[str]] = None,
) -> Optional[List[str]]:
    """Prompt user to select and sequence channel templates and the primary plan block."""
    if initial_sequence is not None:
        sequence = list(initial_sequence)
    else:
        # Default starter sequence: Calling channels -> Route Plan -> NOAA Weather channels
        sequence = []
        if template_mgr.has_template("calling_channels"):
            sequence.append("TEMPLATE:calling_channels")
        sequence.append(primary_block_key)
        if template_mgr.has_template("noaa_wx_channels"):
            sequence.append("TEMPLATE:noaa_wx_channels")

    while True:
        console.print("\n[bold cyan]═══ Codeplug Sequence & Template Blocks ═══[/bold cyan]")
        table = Table(border_style="cyan", show_lines=True)
        table.add_column("#", justify="right", style="cyan", width=4)
        table.add_column("Sequence Block Name", style="bold white")
        table.add_column("Identifier / Key", style="dim")
        table.add_column("Type", justify="center", width=14)

        for idx, key in enumerate(sequence, start=1):
            if key == primary_block_key:
                table.add_row(str(idx), primary_block_title, key, "[bold green]Primary Plan[/bold green]")
            elif key.startswith("TEMPLATE:"):
                tpl_id = key.split(":", 1)[1]
                if template_mgr.has_template(tpl_id):
                    tpl = template_mgr.get_template(tpl_id)
                    name = tpl.name
                    tag = f"[{tpl.tagText}]"
                else:
                    name = f"Template '{tpl_id}'"
                    tag = "[Template]"
                table.add_row(str(idx), f"{name} {tag}", key, "[cyan]Template[/cyan]")
            else:
                table.add_row(str(idx), key, key, "[white]Custom Block[/white]")

        console.print(table)
        console.print("\n[bold cyan]Sequence Actions:[/bold cyan]")
        console.print("  [C] [bold green]Confirm Sequence & Proceed to Target Radio Selection[/bold green]")
        console.print("  [A] Add / Insert a Template block to sequence")
        console.print("  [R] Remove a block from sequence")
        console.print("  [M] Move / Reorder block positions")
        console.print("  [B] Back")

        action = Prompt.ask(
            "Choose action",
            choices=["C", "c", "A", "a", "R", "r", "M", "m", "B", "b", "Q", "q"],
            default="C",
        ).strip().upper()

        if action in {"B", "Q"}:
            return None
        elif action == "C":
            if not sequence:
                console.print("[red]Sequence cannot be empty. Add at least one block.[/red]")
                continue
            return sequence
        elif action == "A":
            templates = template_mgr.list_templates()
            if not templates:
                console.print("[yellow]No templates available to add.[/yellow]")
                continue
            console.print("\n[bold cyan]Available Templates:[/bold cyan]")
            for idx, tpl in enumerate(templates, start=1):
                source = "[green]User[/green]" if template_mgr.is_user_template(tpl.id) else "[cyan]App[/cyan]"
                console.print(f"  [{idx}] {tpl.name} ({tpl.tagText}) - {source}")

            pick = IntPrompt.ask(f"Select template number (1-{len(templates)})", default=1)
            if 1 <= pick <= len(templates):
                chosen = templates[pick - 1]
                new_key = f"TEMPLATE:{chosen.id}"
                if new_key in sequence:
                    console.print(f"[yellow]Template '{chosen.name}' is already in the sequence.[/yellow]")
                    continue

                pos = Prompt.ask(
                    "Insert position: [B]eginning, [E]nd, or [A]fter block #",
                    choices=["B", "b", "E", "e", "A", "a"],
                    default="E",
                ).upper()
                if pos == "B":
                    sequence.insert(0, new_key)
                elif pos == "E":
                    sequence.append(new_key)
                else:
                    after_idx = IntPrompt.ask(f"Insert after block # (1-{len(sequence)})", default=len(sequence))
                    sequence.insert(min(len(sequence), max(0, after_idx)), new_key)
                console.print(f"[green]Added '{chosen.name}' to sequence.[/green]")
        elif action == "R":
            if not sequence:
                continue
            idx = IntPrompt.ask(f"Enter block number to remove (1-{len(sequence)})", default=len(sequence))
            if 1 <= idx <= len(sequence):
                removed = sequence.pop(idx - 1)
                console.print(f"[yellow]Removed block #{idx}: {removed}[/yellow]")
        elif action == "M":
            if len(sequence) < 2:
                console.print("[red]Need at least 2 blocks to reorder.[/red]")
                continue
            from_idx = IntPrompt.ask(f"Select block to move (1-{len(sequence)})", default=1)
            to_idx = IntPrompt.ask(f"Move block #{from_idx} to position (1-{len(sequence)})", default=2)
            if 1 <= from_idx <= len(sequence) and 1 <= to_idx <= len(sequence):
                item = sequence.pop(from_idx - 1)
                sequence.insert(to_idx - 1, item)
                console.print(f"[green]Moved block to position #{to_idx}.[/green]")
