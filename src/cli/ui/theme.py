"""Visual styling, color themes, and badge renderers for Rich CLI."""

from __future__ import annotations

from rich.text import Text

from core.models.channel import RadioChannel

BAND_STYLES = {
    "10m": "bold magenta",
    "6m": "bold cyan",
    "2m": "bold dodger_blue1",
    "1.25m": "bold yellow",
    "70cm": "bold bright_red",
    "GMRS": "bold green",
    "Airband": "bold deep_sky_blue1",
    "WX": "bold bright_yellow",
    "Other": "bold white",
}


def make_band_badge(band: str) -> Text:
    """Create a formatted Text badge for frequency band."""
    style = BAND_STYLES.get(band, "bold white")
    return Text(f"[{band}]", style=style)


def make_channel_badges(ch: RadioChannel) -> Text:
    """Create composite badges for band, mode, and special tags using foreground text colors and no background."""
    t = Text()
    # 1. Band badge
    t.append(f"[{ch.band}]", style=BAND_STYLES.get(ch.band, "bold white"))

    # 2. Digital mode badge (foreground styled, no background)
    if ch.mode.upper() == "DMR" or ch.colorCode is not None:
        t.append(" [DMR]", style="bold royal_blue1")
    elif ch.mode.upper() == "AM":
        t.append(" [AM]", style="bold bright_cyan")

    # 3. Special tag badge (foreground styled, no background)
    if ch.specialType == "CALLING":
        t.append(" [CALL]", style="bold bright_magenta")
    elif ch.specialType == "WX" and ch.band != "WX":
        t.append(" [WX]", style="bold bright_yellow")
    elif ch.specialType == "AVIATION" and ch.band != "Airband":
        t.append(" [AIR]", style="bold royal_blue1")

    # 4. Simplex badge
    if ch.is_simplex and ch.specialType not in {"CALLING", "WX"}:
        t.append(" Simplex", style="dim italic")

    return t
