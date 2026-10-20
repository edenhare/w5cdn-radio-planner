"""Two-stage multi-column target radio selector (Brand -> Model)."""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from cli.ui.renderers import render_header
from core.managers.radio_manager import RadioManager
from core.models.radio_spec import TargetRadioSpec


def select_target_radio_hierarchical(
    console: Console,
    radio_mgr: RadioManager,
    default_id: Optional[str] = None,
) -> Optional[str]:
    """Prompt user to select a target radio using two-stage Brand -> Model multi-column selection."""
    all_radios = radio_mgr.list_radios()
    if not all_radios:
        console.print("[red]No radios configured.[/red]")
        return None

    # Group radios by brand
    brands_map: Dict[str, List[TargetRadioSpec]] = {}
    for r in all_radios:
        brands_map.setdefault(r.brand, []).append(r)

    sorted_brands = sorted(brands_map.keys())

    # Find which brand default_id belongs to if provided
    default_brand_index = "1"
    if default_id and radio_mgr.has_radio(default_id):
        def_radio = radio_mgr.get_radio(default_id)
        if def_radio.brand in sorted_brands:
            default_brand_index = str(sorted_brands.index(def_radio.brand) + 1)

    console.clear()
    render_header(console, subtitle="Radio Configuration")

    while True:
        # Stage 1: Brand Selection (Multi-Column Grid)
        console.print("\n[bold cyan]Select Radio Brand / Manufacturer:[/bold cyan]")
        brand_table = Table(border_style="cyan", show_header=False, padding=(0, 2))
        brand_table.add_column("Col 1", style="bold white")
        brand_table.add_column("Col 2", style="bold white")

        # Split brands into 2 columns
        brand_items = [
            f"[{idx}] {brand} ({len(brands_map[brand])} model{'s' if len(brands_map[brand]) > 1 else ''})"
            for idx, brand in enumerate(sorted_brands, start=1)
        ]
        mid = (len(brand_items) + 1) // 2
        col1 = brand_items[:mid]
        col2 = brand_items[mid:]

        for i in range(len(col1)):
            c2_val = col2[i] if i < len(col2) else ""
            brand_table.add_row(col1[i], c2_val)

        console.print(brand_table)
        console.print("  [Q] Return to Main Menu")

        brand_choice = Prompt.ask(
            "Select brand number",
            default=default_brand_index,
        ).strip().upper()

        if brand_choice in {"Q", "ESC"}:
            return None

        try:
            brand_idx = int(brand_choice)
            if not (1 <= brand_idx <= len(sorted_brands)):
                console.print(f"[red]Invalid brand choice. Enter 1-{len(sorted_brands)}.[/red]")
                continue
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")
            continue

        selected_brand = sorted_brands[brand_idx - 1]
        models = brands_map[selected_brand]

        # Stage 2: Model Selection (Multi-Column Grid)
        console.clear()
        render_header(console, subtitle="Radio Configuration")
        while True:
            console.print(f"\n[bold cyan]Select {selected_brand} Model:[/bold cyan]")
            model_table = Table(border_style="green", show_header=False, padding=(0, 2))
            model_table.add_column("Col 1", style="bold white")
            model_table.add_column("Col 2", style="bold white")

            model_items = [
                f"[{idx}] {m.model} ([dim]{m.programmerType}, {m.maxChannels} ch, LCD {m.maxNameLength}c[/dim])"
                for idx, m in enumerate(models, start=1)
            ]
            m_mid = (len(model_items) + 1) // 2
            m_col1 = model_items[:m_mid]
            m_col2 = model_items[m_mid:]

            for i in range(len(m_col1)):
                m2_val = m_col2[i] if i < len(m_col2) else ""
                model_table.add_row(m_col1[i], m2_val)

            console.print(model_table)
            console.print("  [B] Back to Brand Selection | [Q] Cancel")

            model_choice = Prompt.ask("Select model number", default="1").strip().upper()

            if model_choice in {"B", "BACK"}:
                console.clear()
                render_header(console, subtitle="Radio Configuration")
                break  # Return to Stage 1
            if model_choice in {"Q", "ESC"}:
                return None

            try:
                m_idx = int(model_choice)
                if 1 <= m_idx <= len(models):
                    return models[m_idx - 1].id
                else:
                    console.print(f"[red]Invalid model choice. Enter 1-{len(models)}.[/red]")
            except ValueError:
                console.print("[red]Please enter a valid number.[/red]")
