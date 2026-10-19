"""Visual styling, color themes, and badge renderers for Rich CLI."""

from __future__ import annotations

from rich.text import Text

from core.models.channel import RadioChannel

BAND_STYLES = {
    "10m": "bold magenta",
    "6m": "bold cyan",
    "2m": "bold blue",
    "1.25m": "bold yellow",
    "70cm": "bold bright_red",
    "GMRS": "bold green",
    "Airband": "bold deep_sky_blue1",
    "WX": "bold black on bright_yellow",
    "Other": "dim white",
}


def make_band_badge(band: str) -> Text:
    """Create a formatted Text badge for frequency band."""
    style = BAND_STYLES.get(band, "white")
    return Text(f"[{band}]", style=style)


def make_channel_badges(ch: RadioChannel) -> Text:
    """Create composite badges for band, mode, and special tags."""
    t = Text()
    # 1. Band badge
    t.append(f" {ch.band} ", style=BAND_STYLES.get(ch.band, "bold white on grey23"))

    # 2. Digital mode badge
    if ch.mode.upper() == "DMR" or ch.colorCode is not None:
        t.append(" DMR ", style="bold white on navy_blue")
    elif ch.mode.upper() == "AM":
        t.append(" AM ", style="bold black on bright_cyan")

    # 3. Special tag badge
    if ch.specialType == "CALLING":
        t.append(" CALL ", style="bold black on bright_magenta")
    elif ch.specialType == "WX":
        t.append(" WX ", style="bold black on bright_yellow")
    elif ch.specialType == "AVIATION":
        t.append(" AIR ", style="bold white on royal_blue1")

    # 4. Simplex badge
    if ch.is_simplex and ch.specialType not in {"CALLING", "WX"}:
        t.append(" Simplex ", style="dim italic")

    return t
