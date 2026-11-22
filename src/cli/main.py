"""RadioPlanner CLI Entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from cli.ui.renderers import render_header, render_review_table, render_yaml_error
from core.config.recipe import RadioPlannerRecipe
from core.config.yaml_loader import YamlDiagnosticError
from core.managers.radio_manager import RadioManager
from core.runner import RecipeRunner

VERSION = "0.2.0"


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="radioplanner",
        description="W5CDN RadioPlanner - Travel Corridor and Proximity Radio Codeplug Generator",
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
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address for the FastAPI web server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=None,
        help="Port for the FastAPI web server (defaults to saved preference webPort or 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open the web browser on startup",
    )
    parser.add_argument(
        "--app-window",
        action="store_true",
        help="Launch in a standalone chromeless Chrome/Edge window (no tabs or address bar)",
    )
    parser.add_argument(
        "--chrome",
        action="store_true",
        help="Launch in a standalone chromeless Google Chrome window",
    )
    parser.add_argument(
        "--app-browser",
        default="",
        help="Browser for chromeless app window: chrome, edge, auto, or path to executable",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in the default tabbed web browser instead of a standalone desktop window",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable WebView2 developer tools when running desktop wrapper",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Start local server, verify / and /api/config respond 200, and exit",
    )
    parser.add_argument(
        "--smoke-test-out",
        default="",
        help="Optional JSON file path for --smoke-test results",
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
        except (OSError, ValueError):
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
                    f"  Max Channels: {r.maxChannels} | Name Limit: {r.maxNameLength} chars\n"
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
            except (OSError, ValueError) as exc:
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
                target_spec = runner.radio_manager.get_radio(recipe.radio_target.radio_id)
                render_review_table(console, codeplug, target_spec=target_spec)
                return 0
            except YamlDiagnosticError as err:
                render_yaml_error(console, err)
                return 1
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                console.print(f"[bold red]Execution error: {exc}[/bold red]")
                return 1

        # 4. Delegate desktop/smoke-test flags directly to web.desktop
        if args.smoke_test or args.app_window or args.chrome or args.app_browser:
            from web.desktop import main as desktop_main

            desktop_argv: list[str] = []
            if args.app_window:
                desktop_argv.append("--app-window")
            if args.chrome:
                desktop_argv.append("--chrome")
            if args.app_browser:
                desktop_argv.extend(["--app-browser", args.app_browser])
            if args.browser:
                desktop_argv.append("--browser")
            if args.debug:
                desktop_argv.append("--debug")
            if args.port is not None:
                desktop_argv.extend(["--port", str(args.port)])
            if args.smoke_test:
                desktop_argv.append("--smoke-test")
            if args.smoke_test_out:
                desktop_argv.extend(["--smoke-test-out", args.smoke_test_out])
            return desktop_main(desktop_argv)

        # 5. Launch FastAPI Cockpit Studio
        import os
        import socket
        import threading
        import webbrowser

        import uvicorn

        from core.managers.preferences_manager import PreferencesManager

        prefs_mgr = PreferencesManager()
        env_port = os.environ.get("RADIOPLANNER_PORT")
        port = (
            args.port
            if args.port is not None
            else (int(env_port) if env_port and env_port.isdigit() else getattr(prefs_mgr.preferences, "webPort", 8000))
        )

        url = f"http://{args.host}:{port}"
        render_header(console, title="RadioPlanner", subtitle=f"Cockpit Studio — {url}")

        # Smart single-instance check: if server is already listening on host:port, open browser and exit cleanly
        check_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host  # nosec B104
        already_running = False
        try:
            with socket.create_connection((check_host, port), timeout=0.6):
                already_running = True
        except OSError:
            already_running = False

        if already_running:
            console.print(
                f"\n[bold green]✔ RadioPlanner Cockpit Studio is already running at:[/bold green] [bold cyan]{url}[/bold cyan]"
            )
            if not args.no_browser:
                console.print("[dim]Opening browser tab to active RadioPlanner session...[/dim]\n")
                webbrowser.open(url)
            return 0

        if not args.no_browser and not args.browser:
            from web.desktop import main as desktop_main

            desktop_argv = ["--port", str(port)]
            if args.debug:
                desktop_argv.append("--debug")
            return desktop_main(desktop_argv)

        console.print(f"\n[bold green]✔ Starting RadioPlanner Cockpit Studio at:[/bold green] [bold cyan]{url}[/bold cyan]")
        console.print("[dim]Press Ctrl+C to stop the server.[/dim]\n")

        if not args.no_browser:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()

        uvicorn.run("web.app:app", host=args.host, port=port, log_level="info")
        return 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user. Goodbye![/yellow]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
