"""RadioPlanner CLI Entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from cli.ui.renderers import render_header, render_review_table, render_yaml_error
from cli.wizard.interactive import InteractiveWizard
from core.config.recipe import RadioPlannerRecipe
from core.config.yaml_loader import YamlDiagnosticError
from core.managers.radio_manager import RadioManager
from core.runner import RecipeRunner

VERSION = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="radioplanner",
        description="RadioPlanner - Travel Corridor and Proximity Radio Codeplug Generator",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to a YAML configuration recipe file to execute directly",
    )
    parser.add_argument(
        "--validate",
        type=str,
        help="Validate a YAML configuration file syntax and schema without executing",
    )
    parser.add_argument(
        "--list-radios",
        action="store_true",
        help="List all available target radio hardware models",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"RadioPlanner v{VERSION}",
    )
    return parser


def main() -> int:
    """CLI execution entrypoint."""
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    console = Console()
    parser = build_parser()
    args = parser.parse_args()

    try:
        # 1. List Radios
        if args.list_radios:
            render_header(console, title="RadioPlanner", subtitle="Hardware Specifications")
            mgr = RadioManager()
            radios = mgr.list_radios()
            console.print(f"\n[bold cyan]Registered Radio Models ({len(radios)}):[/bold cyan]")
            for r in radios:
                console.print(
                    f"- [bold white]{r.brand} {r.model}[/bold white] (ID: [green]{r.id}[/green])\n"
                    f"  Programmer: {r.programmerType} | Max Channels: {r.maxChannels} | Name Limit: {r.maxNameLength} chars\n"
                    f"  Bands: {', '.join(r.supportedBands)} | Modes: {', '.join(r.supportedModes)}\n"
                )
            return 0

        # 2. Validate YAML Recipe
        if args.validate:
            target_path = Path(args.validate).resolve()
            try:
                recipe = RadioPlannerRecipe.from_yaml_file(target_path)
                errors = recipe.validate_for_execution()
                if errors:
                    console.print(f"[bold red]Validation failed for {target_path}:[/bold red]")
                    for err in errors:
                        console.print(f"  - [red]{err}[/red]")
                    return 1
                console.print(
                    f"[bold green]✔ Configuration '{target_path.name}' is valid and ready to run![/bold green]"
                )
                return 0
            except YamlDiagnosticError as err:
                render_yaml_error(console, err)
                return 1
            except Exception as exc:
                console.print(f"[bold red]Error: {exc}[/bold red]")
                return 1

        # 3. Direct Execution via --config
        if args.config:
            target_path = Path(args.config).resolve()
            try:
                recipe = RadioPlannerRecipe.from_yaml_file(target_path)
                render_header(console, title="RadioPlanner", subtitle=f"Running Recipe: {recipe.name}")
                runner = RecipeRunner()
                with console.status(f"[bold green]Executing recipe '{recipe.name}'...[/bold green]"):
                    codeplug, out_file = runner.run(recipe)

                console.print(f"\n[bold green]✔ Codeplug successfully exported to: {out_file}[/bold green]")
                render_review_table(console, codeplug)
                return 0
            except YamlDiagnosticError as err:
                render_yaml_error(console, err)
                return 1
            except Exception as exc:
                console.print(f"[bold red]Execution error: {exc}[/bold red]")
                return 1

        # 4. Interactive Wizard (Default)
        wizard = InteractiveWizard(console=console)
        wizard.start()
        return 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user. Goodbye![/yellow]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
