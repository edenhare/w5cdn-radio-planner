"""FastAPI Pure JSON REST API + Offline Cockpit SPA for RadioPlanner."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sys
import threading
import zipfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator

from cli.wizard.band_selector import (
    AVIATION_NAMING_FORMAT_OPTIONS,
    NAMING_FORMAT_OPTIONS,
)
from core.config.paths import (
    get_preferences_file,
    get_radioplanner_home,
    get_radios_dir,
    get_recipes_dir,
    get_templates_dir,
    get_tokens_file,
)
from core.config.recipe import (
    AviationConfig,
    CorridorConfig,
    ProximityConfig,
    RadioPlannerRecipe,
    RadioTargetConfig,
)
from core.config.yaml_loader import YamlDiagnosticError, parse_yaml_text
from core.engines.aviation import AviationEngine
from core.engines.proximity import ProximityEngine
from core.engines.route_corridor import RouteCorridorEngine
from core.engines.sequence import SequenceOrganizer
from core.exporters import export_codeplug, get_exporter
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.preferences import sanitize_panel_layout
from core.models.radio_spec import TargetRadioSpec
from core.models.template import PresetTemplateFile, TemplateChannelItem
from core.providers.repeaterbook import (
    identify_states_for_proximity,
    identify_states_for_route,
)
from core.sanitizers.condenser import NameCondenser
from core.sanitizers.sanitizer import DataSanitizer
from core.updater import (
    UpdateError,
    apply_git_update,
    apply_standalone_update,
    check_for_update,
    detect_install_mode,
    safe_error_message,
)
from web.security import clean_single_line, safe_child_path, security_middleware
from web.state import workspace

logger = logging.getLogger("radioplanner.web")

APP_VERSION = "0.2.0"
APP_TITLE = "W5CDN RadioPlanner"


def _resolve_dirs() -> tuple[Path, Path]:
    """Return (data_dir, bundle_dir) for both source and frozen PyInstaller builds."""
    if getattr(sys, "frozen", False):
        data_dir = Path(sys.executable).resolve().parent
        bundle_dir = Path(getattr(sys, "_MEIPASS", str(data_dir)))
        return data_dir, bundle_dir
    pkg_dir = Path(__file__).resolve().parent
    data_dir = pkg_dir.parent.parent if pkg_dir.parent.name == "src" else pkg_dir
    return data_dir, pkg_dir


BASE_DIR, BUNDLE_DIR = _resolve_dirs()
STATIC_DIR = BUNDLE_DIR / "static"

MAX_BACKUP_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_BACKUP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_BACKUP_FILES = 5000
WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


def parse_port(raw: str | None, default: int = 8000) -> int:
    """Parse a TCP port string safely, falling back to default if invalid."""
    try:
        val = int((raw or "").strip())
        if 0 <= val <= 65535:
            return val
    except ValueError:
        pass
    return default


class WindowShutdownManager:
    """Coordinate clean local server exit when browser tab unloads or self-update restarts."""

    def __init__(self, delay_seconds: float = 2.0) -> None:
        self._delay = delay_seconds
        self._lock = threading.Lock()
        self._callback: Callable[[], None] | None = None
        self._timer: threading.Timer | None = None

    def register(self, callback: Callable[[], None] | None) -> None:
        with self._lock:
            self._callback = callback
            if callback is None and self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def cancel(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def schedule(self, delay_seconds: float | None = None) -> bool:
        with self._lock:
            if self._callback is None:
                return False
            if self._timer is not None:
                self._timer.cancel()
            cb = self._callback
            wait = self._delay if delay_seconds is None else delay_seconds
            self._timer = threading.Timer(wait, cb)
            self._timer.daemon = True
            self._timer.start()
            return True


shutdown_manager = WindowShutdownManager()


def register_shutdown_callback(callback: Callable[[], None] | None) -> None:
    shutdown_manager.register(callback)


def cancel_pending_shutdown() -> None:
    shutdown_manager.cancel()

BAND_COLORS: dict[str, str] = {
    "10m": "#f97316",
    "6m": "#ec4899",
    "2m": "#10b981",
    "1.25m": "#14b8a6",
    "70cm": "#a855f7",
    "GMRS": "#eab308",
    "Airband": "#6366f1",
    "WX": "#38bdf8",
    "Other": "#94a3b8",
}

RING_COLORS: list[str] = [
    "#10b981",
    "#06b6d4",
    "#3b82f6",
    "#a855f7",
    "#f59e0b",
    "#f43f5e",
    "#ec4899",
    "#84cc16",
]


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class PlanGenerateRequest(BaseModel):
    mode: str = "ROUTE_CORRIDOR"
    plan_name: str = ""
    plan_description: str = ""
    waypoints: list[str] = Field(default_factory=lambda: ["Tyler, TX", "Shreveport, LA", "Jackson, MS"])
    corridor_width: float = Field(default=25.0, ge=1.0, le=200.0)
    center_location: str = "Dallas, TX"
    radius_miles: float = Field(default=50.0, ge=1.0, le=300.0)
    include_simplex: bool = True
    repeater_access: list[str] = Field(default_factory=lambda: ["OPEN"])
    sequence_order: list[str] = Field(default_factory=list)
    radio_id: str | None = None
    bands: list[str] = Field(default_factory=list)
    naming_format: str = ""


class CodeplugUpdateRequest(BaseModel):
    radio_id: str
    naming_format: str = ""
    bands: list[str] = Field(default_factory=list)
    include_gmrs_std: bool = False
    radio_changed: bool = False


class DeleteChannelsRequest(BaseModel):
    slots: list[int] = Field(default_factory=list)


class ChannelEditRequest(BaseModel):
    name: str | None = None
    callsign: str | None = None
    rxFreq: float | None = Field(default=None, gt=0.0, lt=3000.0)
    offsetDir: str | None = None
    offset: float | None = Field(default=None, ge=0.0, lt=100.0)
    mode: str | None = None
    power: str | None = None
    toneMode: str | None = None
    ctcss: str | None = None
    dcs: str | None = None
    city: str | None = None
    state: str | None = None
    comment: str | None = None


class ExportCsvRequest(BaseModel):
    programmer_type: str = "CHIRP"
    filename: str = "codeplug.csv"


class RecipeSaveRequest(BaseModel):
    name: str = "Saved_Plan"
    description: str = ""


class RecipeUploadRequest(BaseModel):
    filename: str = "uploaded_recipe.yaml"
    yaml_text: str


class TemplateChannelPayload(BaseModel):
    name: str
    rxFreq: float = Field(gt=0.0, lt=3000.0)
    offsetDir: str = "off"
    offset: float = Field(default=0.0, ge=0.0, lt=100.0)
    mode: str = "FM"
    power: str = "High"
    toneMode: str = "None"
    toneVal: str = "None"
    comment: str = ""


class TemplateSaveRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    tagText: str = "PRESET"
    tagColorHex: str = "#00BCD4"
    channels: list[TemplateChannelPayload] = Field(default_factory=list)


class TemplateImportRequest(BaseModel):
    id: str
    name: str
    tagText: str = "CUSTOM"
    description: str = ""
    filename: str = "imported.csv"
    content: str


class RadioSaveRequest(BaseModel):
    id: str
    brand: str
    model: str
    description: str = ""
    startChannel: int = Field(default=1, ge=0, le=1)
    maxChannels: int = Field(default=128, ge=1, le=10000)
    maxNameLength: int = Field(default=8, ge=1, le=32)
    programmerType: str = "RT_SYSTEMS"
    supportedBands: list[str] = Field(default_factory=lambda: ["2m", "70cm", "WX"])
    supportedModes: list[str] = Field(default_factory=lambda: ["FM", "AM"])
    allowDots: bool = True
    allowSpaces: bool = True


class PreferencesUpdateRequest(BaseModel):
    callsign: str | None = None
    operatorName: str | None = None
    primaryDmrId: str | None = None
    defaultRadioId: str | None = None
    channelNamingFormat: str | None = None
    distanceUnit: str | None = None
    repeaterMaxAgeDays: int | None = Field(default=None, ge=1, le=365)
    webPort: int | None = Field(default=None, ge=1, le=65535)
    colorTheme: str | None = None
    fontFamily: str | None = None
    monoFont: str | None = None
    uiFontSize: int | None = Field(default=None, ge=11, le=22)
    lcdFontSize: int | None = Field(default=None, ge=12, le=26)
    panelLayout: dict[str, Any] | None = None
    repeaterBookApiKey: str | None = None
    clearRepeaterBookApiKey: bool = False
    radioIdUsername: str | None = None
    radioIdApiKey: str | None = None
    clearRadioIdApiKey: bool = False
    qrzUsername: str | None = Field(default=None, max_length=120)
    qrzPassword: str | None = Field(default=None, max_length=200)
    clearQrzPassword: bool = False

    @field_validator("qrzPassword")
    @classmethod
    def validate_qrz_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if any(ch in v for ch in ("\x00", "\r", "\n")):
            raise ValueError("Password cannot contain newline or NUL characters")
        return v


class QrzTestRequest(BaseModel):
    qrzUsername: str | None = Field(default=None, max_length=120)
    qrzPassword: str | None = Field(default=None, max_length=200)


class NetLoggerImportRequest(BaseModel):
    id: str = "net_logger_presets"
    name: str = "W5CDN Net Logger Presets"
    tagText: str = "NETLOG"
    description: str = "Imported from W5CDN Net Logger net_type_defaults JSON"
    json_text: str


# ---------------------------------------------------------------------------
# Serialization & Domain Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_band_counts_and_map_channels(
    codeplug: Codeplug,
    active_bands: list[str],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Initialize counts for all selected bands and build map marker records."""
    counts: dict[str, int] = {b: 0 for b in active_bands}
    map_channels: list[dict[str, Any]] = []
    for ch in codeplug.channels:
        counts[ch.band] = counts.get(ch.band, 0) + 1
        if ch.lat and ch.lon:
            tone_lbl = (
                ch.ctcss
                if ch.toneMode in {"Tone", "TSQL"}
                else (f"D{ch.dcs}" if ch.toneMode in {"DCS", "DTCS"} else "CSQ")
            )
            map_channels.append(
                {
                    "number": ch.number,
                    "name": ch.name,
                    "callsign": ch.callsign or "",
                    "rxFreq": ch.rxFreq,
                    "mode": ch.mode,
                    "band": ch.band,
                    "color": BAND_COLORS.get(ch.band, "#10b981"),
                    "tone": tone_lbl,
                    "location": f"{ch.city or ''}, {ch.state or ''}".strip(", "),
                    "lat": ch.lat,
                    "lon": ch.lon,
                }
            )
    return counts, map_channels


def _build_naming_previews(spec: TargetRadioSpec, mode: str = "ROUTE_CORRIDOR") -> list[dict[str, str]]:
    """Generate live LCD sample previews for the active mode's naming formats on the given radio."""
    if mode.upper() == "AVIATION_PLANNER":
        sample_air = RadioChannel(
            number=1,
            name="KTYR ATIS",
            callsign="KTYR",
            rxFreq=126.25,
            txFreq=126.25,
            mode="AM",
            city="Tyler",
            state="TX",
            specialType="AVIATION",
        )
        return [
            {
                "code": code,
                "label": label,
                "desc": desc,
                "sample": NameCondenser.condense_channel(sample_air, spec, naming_format=code),
            }
            for code, label, desc in AVIATION_NAMING_FORMAT_OPTIONS
        ]

    sample_ch = RadioChannel(
        number=1,
        name="Tyler 147.20",
        callsign="W5ETX",
        rxFreq=147.20,
        txFreq=147.80,
        city="Tyler",
        state="TX",
    )
    return [
        {
            "code": code,
            "label": label,
            "desc": desc,
            "sample": NameCondenser.condense_channel(sample_ch, spec, naming_format=code),
        }
        for code, label, desc in NAMING_FORMAT_OPTIONS
    ]


def _default_export_filename(recipe: RadioPlannerRecipe, spec: TargetRadioSpec) -> str:
    date_str = datetime.now().strftime("%m%d%y")
    prog = (recipe.radio_target.programmer_format or spec.programmerType or "RT_SYSTEMS").lower()
    return f"{DataSanitizer.sanitize_filename(recipe.name)}-{spec.id}-{prog}-{date_str}.csv"


def _smart_default_naming(spec: TargetRadioSpec, mode: str) -> str:
    """Return smart default channel naming format based on target radio LCD size and mode."""
    if mode.upper() == "AVIATION_PLANNER":
        return "IDENT_TYPE"
    if spec.maxNameLength <= 6:
        return "CALLSIGN"
    return getattr(workspace.prefs_mgr.preferences, "channelNamingFormat", "CITY_FREQ") or "CITY_FREQ"


def _default_bands_for_radio(
    spec: TargetRadioSpec,
    mode: str,
    sequence_order: list[str] | None = None,
) -> list[str]:
    """Return default active frequency bands for a target radio and operating mode."""
    if mode.upper() == "AVIATION_PLANNER":
        has_templates = any(k.startswith("TEMPLATE:") for k in (sequence_order or []))
        return list(set(spec.supportedBands) | {"Airband"}) if has_templates else ["Airband"]
    non_air = [b for b in spec.supportedBands if b.lower() != "airband"]
    return non_air if non_air else list(spec.supportedBands)


def _serialize_channel(ch: RadioChannel) -> dict[str, Any]:
    data = ch.model_dump()
    data["band"] = ch.band
    data["is_simplex"] = ch.is_simplex
    return data


def _serialize_preferences() -> dict[str, Any]:
    prefs = workspace.prefs_mgr.preferences
    tokens = workspace.prefs_mgr.tokens
    return {
        "callsign": prefs.callsign,
        "operatorName": prefs.operatorName,
        "primaryDmrId": prefs.primaryDmrId or "",
        "distanceUnit": prefs.distanceUnit,
        "defaultRadioId": prefs.defaultRadioId or "",
        "channelNamingFormat": prefs.channelNamingFormat,
        "repeaterAccess": list(prefs.repeaterAccess),
        "repeaterMaxAgeDays": prefs.repeaterMaxAgeDays,
        "webPort": prefs.webPort,
        "theme": prefs.resolved_cockpit_theme,
        "ui_font": prefs.resolved_ui_font,
        "mono_font": prefs.monoFont,
        "font_size": prefs.uiFontSize,
        "lcd_font_size": prefs.lcdFontSize,
        "panel_layout": sanitize_panel_layout(prefs.panelLayout),
        "repeaterBookApiKeySet": bool(tokens.repeaterBookApiKey),
        "radioIdUsername": tokens.radioIdUsername or "",
        "radioIdApiKeySet": bool(tokens.radioIdApiKey),
        "qrzUsername": tokens.qrzUsername or "",
        "qrzConfigured": bool(tokens.qrzUsername and tokens.qrzPassword),
        "has_api_key": workspace.repeater_provider.has_api_key(),
    }


def _serialize_radios() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for spec in workspace.radio_mgr.list_radios():
        item = spec.model_dump()
        item["is_user"] = workspace.radio_mgr.is_user_radio(spec.id)
        items.append(item)
    return items


def _serialize_templates() -> list[dict[str, Any]]:
    workspace.template_mgr.reload()
    items: list[dict[str, Any]] = []
    for tpl in workspace.template_mgr.list_templates():
        channels_out: list[dict[str, Any]] = []
        for ch in tpl.channels:
            tx_f = ch.txFreq if ch.txFreq is not None else ch.rxFreq
            calc_off = ch.offset if ch.offset is not None else abs(tx_f - ch.rxFreq)
            if ch.offsetDir in {"+", "-"}:
                eff_dir = ch.offsetDir
            elif (tx_f - ch.rxFreq) > 0.0001:
                eff_dir = "+"
            elif (ch.rxFreq - tx_f) > 0.0001:
                eff_dir = "-"
            else:
                eff_dir = "off"
            eff_tone = ch.dcs if ch.toneMode == "DCS" else (ch.ctcss if ch.toneMode in {"Tone", "TSQL"} else "None")
            channels_out.append(
                {
                    "name": ch.name,
                    "rxFreq": ch.rxFreq,
                    "txFreq": tx_f,
                    "offsetDir": eff_dir,
                    "offset": round(calc_off if eff_dir != "off" else 0.0, 5),
                    "mode": ch.mode,
                    "power": ch.power,
                    "toneMode": ch.toneMode,
                    "toneVal": eff_tone,
                    "comment": ch.comment,
                }
            )
        items.append(
            {
                "id": tpl.id,
                "name": tpl.name,
                "description": tpl.description,
                "tagText": tpl.tagText,
                "tagColorHex": tpl.tagColorHex,
                "channelCount": len(channels_out),
                "channels": channels_out,
                "is_user": workspace.template_mgr.is_user_template(tpl.id),
                "is_builtin": tpl.id in {"calling_channels", "noaa_wx_channels", "gmrs_channels"},
            }
        )
    return items


def _serialize_recipes() -> list[dict[str, Any]]:
    recipes_dir = get_recipes_dir()
    recipes_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(recipes_dir.glob("*.yaml")):
        try:
            rec = RadioPlannerRecipe.from_yaml_file(path)
        except (OSError, ValueError, YamlDiagnosticError, ValidationError) as exc:
            logger.debug("Skipping invalid recipe %s: %s", path.name, exc)
            continue
        items.append(
            {
                "filename": path.name,
                "name": rec.name,
                "description": rec.description,
                "mode": rec.mode,
                "corridor": rec.corridor.model_dump() if rec.corridor else None,
                "proximity": rec.proximity.model_dump() if rec.proximity else None,
                "aviation": rec.aviation.model_dump() if rec.aviation else None,
                "radio_target": rec.radio_target.model_dump(),
                "sequence_order": list(rec.sequence_order),
            }
        )
    return items


def _serialize_active_plan(message: str = "") -> dict[str, Any]:
    sess = workspace.session
    if not sess.recipe or not sess.codeplug or not sess.radio_spec:
        return {"active": False}
    spec = sess.radio_spec
    recipe = sess.recipe
    codeplug = sess.codeplug
    return {
        "active": True,
        "message": message,
        "recipe": recipe.model_dump(),
        "radio_spec": spec.model_dump(),
        "naming_previews": _build_naming_previews(spec, mode=recipe.mode),
        "codeplug": {
            "name": codeplug.name,
            "total_channels": codeplug.total_channels,
            "channels": [_serialize_channel(ch) for ch in codeplug.channels],
        },
        "summary": sess.summary_data,
        "map_data": sess.map_data,
        "notices": sess.notices,
        "band_colors": BAND_COLORS,
        "default_export_filename": _default_export_filename(recipe, spec),
        "can_undo": len(sess.undo_stack) > 0,
        "undo_count": len(sess.undo_stack),
        "undo_label": sess.undo_stack[-1].label if sess.undo_stack else "",
    }


def _build_pocket_report_text(
    recipe: RadioPlannerRecipe,
    codeplug: Codeplug,
    spec: TargetRadioSpec,
    summary: dict[str, Any],
) -> str:
    """Build a crisp, printable plain-text pocket reference card for the active codeplug."""
    lines: list[str] = [
        f"RADIOPLANNER CODEPLUG REFERENCE CARD — {codeplug.name}",
        "=" * 78,
        f"Mode:         {recipe.mode}",
        f"Target Radio: {spec.brand} {spec.model} ({spec.id}) | Slots {spec.startChannel}..{spec.startChannel + max(codeplug.total_channels - 1, 0)} ({codeplug.total_channels}/{spec.maxChannels})",
        f"LCD Limit:    {spec.maxNameLength} chars | Naming: {recipe.radio_target.naming_format} | Format: {recipe.radio_target.programmer_format or spec.programmerType}",
        f"Generated:    {_utc_now_iso()} | Operator: {workspace.prefs_mgr.preferences.callsign}",
    ]
    if summary.get("subtitle"):
        lines.append(f"Coverage:     {summary['subtitle']}")
    if summary.get("states"):
        lines.append(f"States:       {', '.join(summary['states'])}")
    if recipe.description:
        lines.append(f"Notes:        {recipe.description}")

    lines.extend(
        [
            "-" * 78,
            f"{'CH':>4}  {'LCD NAME':<16} {'CALL':<8} {'RX (MHz)':>10} {'DUP':>7} {'TONE':<11} {'MODE':<5} {'LOCATION'}",
            "-" * 78,
        ]
    )
    for ch in codeplug.channels:
        dup = "SIMPLEX" if ch.is_simplex else f"{ch.offsetDir}{ch.offset:.3f}"
        if ch.toneMode in {"Tone", "TSQL"} and ch.ctcss != "None":
            tone = f"{ch.toneMode[:4]} {ch.ctcss}"
        elif ch.toneMode in {"DCS", "DTCS"} and ch.dcs != "None":
            tone = f"DCS {ch.dcs}"
        else:
            tone = "CSQ"
        loc = f"{ch.city}, {ch.state}" if (ch.city and ch.state) else (ch.city or ch.comment[:24] or "-")
        lines.append(
            f"{ch.number:>4}  {ch.name[:16]:<16} {(ch.callsign or '-'):<8} {ch.rxFreq:>10.4f} {dup:>7} {tone:<11} {ch.mode:<5} {loc}"
        )
    lines.append("-" * 78)
    lines.append(f"Total Channels: {codeplug.total_channels}")
    return "\n".join(lines) + "\n"


def _parse_net_logger_json_to_template(
    *,
    clean_id: str,
    name: str,
    description: str,
    tag_text: str,
    raw_json: str,
) -> PresetTemplateFile:
    """Parse W5CDN Net Logger net_type_defaults or repeater preset JSON into a PresetTemplateFile."""
    parsed = json.loads(raw_json)
    records: list[tuple[str, dict[str, Any]]] = []
    if isinstance(parsed, dict):
        if isinstance(parsed.get("net_type_defaults"), dict):
            for label, cfg in parsed["net_type_defaults"].items():
                if isinstance(cfg, dict):
                    records.append((str(label), cfg))
        elif "frequency" in parsed:
            records.append((str(parsed.get("name") or parsed.get("callsign") or "Net Preset"), parsed))
        else:
            for label, cfg in parsed.items():
                if isinstance(cfg, dict) and ("frequency" in cfg or "rxFreq" in cfg):
                    records.append((str(cfg.get("name") or label), cfg))
    elif isinstance(parsed, list):
        for idx, cfg in enumerate(parsed, start=1):
            if isinstance(cfg, dict):
                records.append((str(cfg.get("name") or cfg.get("callsign") or f"Net {idx}"), cfg))

    channels: list[TemplateChannelItem] = []
    freq_re = re.compile(r"(\d{1,4}(?:\.\d{1,6})?)")
    off_re = re.compile(r"([+-])[ \t]{0,4}(\d{1,4}(?:\.\d{1,5})?)")
    pl_re = re.compile(r"\b(?:PL|CTCSS|TONE)[ \t:=]{0,6}(\d{2,3}\.\d)\b", re.IGNORECASE)
    dcs_re = re.compile(r"\b(?:DCS|DTCS|D)[ \t:=]{0,6}(\d{3})\b", re.IGNORECASE)

    for label, cfg in records:
        freq_raw = str(cfg.get("frequency") or cfg.get("rxFreq") or "").strip()[:40]
        fm = freq_re.search(freq_raw)
        if not fm:
            continue
        rx = round(float(fm.group(1)), 5)
        if rx <= 0.0 or rx >= 3000.0:
            continue

        tone_off = str(cfg.get("tone_offset") or "").strip()[:120]
        off_dir = "off"
        off_val = 0.0
        om = off_re.search(tone_off)
        if om:
            off_dir = om.group(1)
            raw_off = float(om.group(2))
            off_val = round(raw_off / 1000.0 if raw_off > 50.0 else raw_off, 5)
        elif "simplex" not in tone_off.lower() and off_dir == "off":
            pass

        tx = round(rx + off_val, 5) if off_dir == "+" else (round(rx - off_val, 5) if off_dir == "-" else rx)

        tone_mode = "None"
        ctcss = "None"
        dcs = "None"
        pm = pl_re.search(tone_off)
        dm = dcs_re.search(tone_off)
        if pm:
            tone_mode = "Tone"
            ctcss = pm.group(1)
        elif dm:
            tone_mode = "DCS"
            dcs = dm.group(1)

        mode_val = clean_single_line(cfg.get("mode") or "FM", max_len=12).upper() or "FM"
        comment_bits = [
            clean_single_line(cfg.get("callsign") or "", max_len=16),
            clean_single_line(cfg.get("location") or "", max_len=80),
            clean_single_line(tone_off, max_len=60),
        ]
        channels.append(
            TemplateChannelItem(
                name=clean_single_line(label, max_len=64) or f"Net {len(channels) + 1}",
                rxFreq=rx,
                txFreq=tx,
                offset=off_val if off_dir != "off" else None,
                offsetDir=off_dir,
                mode=mode_val,
                power="High",
                toneMode=tone_mode,
                ctcss=ctcss,
                rxCtcss="None",
                dcs=dcs,
                rxDcs=dcs if tone_mode == "DCS" else "None",
                comment=" | ".join(b for b in comment_bits if b)[:240],
            )
        )

    if not channels:
        raise ValueError("No valid frequency entries found in Net Logger JSON.")

    return PresetTemplateFile(
        id=clean_id,
        name=clean_single_line(name, max_len=100) or clean_id,
        description=clean_single_line(description, max_len=240),
        tagText=clean_single_line(tag_text, max_len=24).upper() or "NETLOG",
        tagColorHex="#38bdf8",
        channels=channels,
    )


def _create_config_backup_zip_bytes(*, include_tokens: bool = False) -> bytes:
    """Create a ZIP archive of RadioPlanner user preferences, recipes, radios, and templates."""
    home = get_radioplanner_home()
    buf = io.BytesIO()
    manifest = {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "exported_at": _utc_now_iso(),
        "include_tokens": include_tokens,
    }
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        prefs_file = get_preferences_file()
        if prefs_file.is_file():
            zf.write(prefs_file, arcname="preferences.yaml")
        if include_tokens:
            tokens_file = get_tokens_file()
            if tokens_file.is_file():
                zf.write(tokens_file, arcname="tokens")
        for folder, folder_path in (
            ("recipes", get_recipes_dir()),
            ("radios", get_radios_dir()),
            ("templates", get_templates_dir()),
        ):
            if folder_path.is_dir():
                for fp in sorted(folder_path.glob("*.yaml")):
                    if fp.is_file():
                        zf.write(fp, arcname=f"{folder}/{fp.name}")
    logger.debug("Created backup archive for %s (%d bytes)", home, buf.tell())
    return buf.getvalue()


def _restore_config_backup_zip_bytes(raw_bytes: bytes) -> dict[str, Any]:
    """Validate and restore a RadioPlanner backup ZIP archive with Zip-Slip & size hardening."""
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty backup upload.")
    if len(raw_bytes) > MAX_BACKUP_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Backup archive exceeds 50 MB upload limit.")

    try:
        zf_ctx = zipfile.ZipFile(io.BytesIO(raw_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive.") from exc

    allowed_subdirs = {"recipes", "radios", "templates"}
    validated_files: list[tuple[str, bytes]] = []
    with zf_ctx as zf:
        infos = zf.infolist()
        if len(infos) > MAX_BACKUP_FILES:
            raise HTTPException(status_code=400, detail="Backup archive contains too many files.")
        total_uncompressed = 0
        for info in infos:
            name = info.filename
            if (
                name.startswith(("/", "\\"))
                or ".." in re.split(r"[\\/]+", name)
                or WINDOWS_ABS_RE.match(name)
            ):
                raise HTTPException(status_code=400, detail="Backup archive contains an unsafe path.")
            total_uncompressed += max(0, info.file_size)
            if total_uncompressed > MAX_BACKUP_UNCOMPRESSED_BYTES:
                raise HTTPException(status_code=400, detail="Backup archive exceeds 100 MB uncompressed limit.")

            if info.is_dir():
                continue
            norm = name.replace("\\", "/")
            parts = norm.split("/")
            if norm in {"manifest.json"}:
                continue
            if norm in {"preferences.yaml", "tokens"}:
                content = zf.read(info)
                try:
                    parse_yaml_text(content.decode("utf-8"))
                except (UnicodeDecodeError, YamlDiagnosticError, ValueError) as exc:
                    raise HTTPException(status_code=400, detail=f"Invalid YAML in {norm}: {exc}") from exc
                validated_files.append((norm, content))
            elif len(parts) == 2 and parts[0] in allowed_subdirs and parts[1].lower().endswith((".yaml", ".yml")):
                content = zf.read(info)
                try:
                    parse_yaml_text(content.decode("utf-8"))
                except (UnicodeDecodeError, YamlDiagnosticError, ValueError) as exc:
                    raise HTTPException(status_code=400, detail=f"Invalid YAML in {norm}: {exc}") from exc
                validated_files.append((norm, content))

    if not validated_files:
        raise HTTPException(status_code=400, detail="Backup archive contained no restorable RadioPlanner files.")

    home = get_radioplanner_home()
    home.mkdir(parents=True, exist_ok=True)
    pre_restore_bak = home / "radioplanner.pre_restore.bak"
    pre_restore_bak.write_bytes(_create_config_backup_zip_bytes(include_tokens=False))

    home_abs = os.path.abspath(str(home))
    restored_names: list[str] = []
    for rel_norm, content in validated_files:
        dest_abs = os.path.normpath(os.path.join(home_abs, rel_norm))
        if not dest_abs.startswith(home_abs + os.sep):
            raise HTTPException(status_code=400, detail="Backup archive entry escapes configuration directory.")
        dest_path = Path(dest_abs)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(content)
        if rel_norm == "tokens" and hasattr(os, "chmod") and os.name != "nt":
            try:
                os.chmod(dest_path, 0o600)
            except OSError:
                pass
        restored_names.append(rel_norm)

    workspace.reload_all()
    return {
        "restored": True,
        "count": len(restored_names),
        "files": restored_names,
        "backup_saved": pre_restore_bak.name,
        "message": f"Restored {len(restored_names)} configuration file(s). Pre-restore snapshot saved to {pre_restore_bak.name}.",
    }


def _parse_template_channel_payloads(items: list[TemplateChannelPayload]) -> list[TemplateChannelItem]:
    channel_items: list[TemplateChannelItem] = []
    for idx, item in enumerate(items, start=1):
        r_name = clean_single_line(item.name, max_len=64) or f"CH {idx}"
        rx = round(float(item.rxFreq), 5)
        off_dir = item.offsetDir.strip() if item.offsetDir.strip() in {"off", "+", "-"} else "off"
        off_val = round(abs(float(item.offset or 0.0)), 5)
        if off_dir == "+":
            tx = round(rx + off_val, 5)
        elif off_dir == "-":
            tx = round(rx - off_val, 5)
        else:
            off_val = 0.0
            tx = rx

        mode_val = clean_single_line(item.mode, max_len=16).upper() or "FM"
        pwr_raw = clean_single_line(item.power, max_len=16).capitalize()
        power_val = pwr_raw if pwr_raw in {"High", "Mid", "Low"} else "High"
        t_mode = item.toneMode.strip() if item.toneMode.strip() in {"None", "Tone", "TSQL", "DCS"} else "None"
        t_val = clean_single_line(item.toneVal, max_len=16) or "None"

        ctcss = "None"
        rx_ctcss = "None"
        dcs = "None"
        rx_dcs = "None"
        if t_mode in {"Tone", "TSQL"}:
            ctcss = t_val if t_val.lower() != "none" else "88.5"
            rx_ctcss = ctcss if t_mode == "TSQL" else "None"
        elif t_mode == "DCS":
            dcs = t_val.lstrip("Dd") if t_val.lower() != "none" else "023"
            rx_dcs = dcs

        channel_items.append(
            TemplateChannelItem(
                name=r_name,
                rxFreq=rx,
                txFreq=tx,
                offset=off_val if off_dir != "off" else None,
                offsetDir=off_dir,
                mode=mode_val,
                power=power_val,
                toneMode=t_mode,
                ctcss=ctcss,
                rxCtcss=rx_ctcss,
                dcs=dcs,
                rxDcs=rx_dcs,
                comment=clean_single_line(item.comment, max_len=240),
            )
        )
    return channel_items


# ---------------------------------------------------------------------------
# FastAPI Application Factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the RadioPlanner FastAPI Cockpit application."""
    app = FastAPI(title="RadioPlanner Cockpit Studio", version=APP_VERSION)
    app.middleware("http")(security_middleware)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("Validation error: %s", exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def key_error_handler(_request: Request, exc: KeyError) -> JSONResponse:
        logger.warning("Lookup error: %s", exc)
        return JSONResponse(status_code=404, content={"detail": str(exc).strip("'")})

    @app.exception_handler(OSError)
    async def os_error_handler(_request: Request, exc: OSError) -> JSONResponse:
        logger.error("Filesystem I/O error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Local filesystem error occurred"})

    # ─── Static SPA Shell ────────────────────────────────────────────────────

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        cancel_pending_shutdown()
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="UI file static/index.html not found")
        return FileResponse(index_path)

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon() -> FileResponse:
        ico_path = STATIC_DIR / "icon.ico"
        if ico_path.is_file():
            return FileResponse(ico_path, media_type="image/x-icon")
        svg_path = STATIC_DIR / "icon.svg"
        if not svg_path.is_file():
            raise HTTPException(status_code=404, detail="Icon file static/icon.svg not found")
        return FileResponse(svg_path, media_type="image/svg+xml")

    @app.post("/api/client/unload")
    async def api_client_unload() -> dict[str, bool]:
        scheduled = shutdown_manager.schedule()
        return {"ok": True, "shutdown_scheduled": scheduled}

    # ─── Bootstrap Config & Preferences ──────────────────────────────────────

    @app.get("/api/config")
    async def api_config() -> dict[str, Any]:
        cancel_pending_shutdown()
        recipes = _serialize_recipes()
        return {
            "app_title": APP_TITLE,
            "version": APP_VERSION,
            "install_mode": detect_install_mode(BASE_DIR),
            "utc_now": _utc_now_iso(),
            "preferences": _serialize_preferences(),
            "radios": _serialize_radios(),
            "templates": _serialize_templates(),
            "recipes_count": len(recipes),
            "recipes_dir": str(get_recipes_dir()),
            "cached_states": workspace.repeater_provider.list_cached_state_files(),
            "band_colors": BAND_COLORS,
            "active_plan": _serialize_active_plan(),
        }

    @app.get("/api/preferences")
    async def api_get_preferences() -> dict[str, Any]:
        return {
            "preferences": _serialize_preferences(),
            "cached_states": workspace.repeater_provider.list_cached_state_files(),
        }

    @app.put("/api/preferences")
    async def api_update_preferences(payload: PreferencesUpdateRequest) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if payload.callsign is not None:
            updates["callsign"] = clean_single_line(payload.callsign, max_len=24)
        if payload.operatorName is not None:
            updates["operatorName"] = clean_single_line(payload.operatorName, max_len=80)
        if payload.primaryDmrId is not None:
            cleaned_dmr = clean_single_line(payload.primaryDmrId, max_len=16)
            updates["primaryDmrId"] = cleaned_dmr or None
        if payload.defaultRadioId is not None:
            cleaned_radio = clean_single_line(payload.defaultRadioId, max_len=64)
            updates["defaultRadioId"] = cleaned_radio or None
        if payload.channelNamingFormat is not None:
            updates["channelNamingFormat"] = clean_single_line(payload.channelNamingFormat, max_len=32)
        if payload.distanceUnit is not None:
            updates["distanceUnit"] = clean_single_line(payload.distanceUnit, max_len=16)
        if payload.repeaterMaxAgeDays is not None:
            updates["repeaterMaxAgeDays"] = payload.repeaterMaxAgeDays
        if payload.webPort is not None:
            updates["webPort"] = payload.webPort
        if payload.colorTheme is not None:
            updates["colorTheme"] = clean_single_line(payload.colorTheme, max_len=32)
        if payload.fontFamily is not None:
            updates["fontFamily"] = clean_single_line(payload.fontFamily, max_len=32)
        if payload.monoFont is not None:
            updates["monoFont"] = clean_single_line(payload.monoFont, max_len=32)
        if payload.uiFontSize is not None:
            updates["uiFontSize"] = payload.uiFontSize
        if payload.lcdFontSize is not None:
            updates["lcdFontSize"] = payload.lcdFontSize
        if payload.panelLayout is not None:
            current = sanitize_panel_layout(workspace.prefs_mgr.preferences.panelLayout)
            merged = {**current}
            for key, val in payload.panelLayout.items():
                if key in current and isinstance(val, dict):
                    merged[key] = {**current[key], **val}
            updates["panelLayout"] = sanitize_panel_layout(merged)

        if updates:
            new_prefs = workspace.prefs_mgr.preferences.update_settings(**updates)
            workspace.prefs_mgr.save_preferences(new_prefs)

        token_updates: dict[str, Any] = {}
        if payload.clearRepeaterBookApiKey:
            token_updates["repeaterBookApiKey"] = None
        elif payload.repeaterBookApiKey is not None and payload.repeaterBookApiKey.strip():
            token_updates["repeaterBookApiKey"] = clean_single_line(payload.repeaterBookApiKey, max_len=256)

        if payload.radioIdUsername is not None:
            cleaned_user = clean_single_line(payload.radioIdUsername, max_len=32).upper()
            token_updates["radioIdUsername"] = cleaned_user or None

        if payload.clearRadioIdApiKey:
            token_updates["radioIdApiKey"] = None
        elif payload.radioIdApiKey is not None and payload.radioIdApiKey.strip():
            token_updates["radioIdApiKey"] = clean_single_line(payload.radioIdApiKey, max_len=256)

        if payload.qrzUsername is not None:
            cleaned_qrz = clean_single_line(payload.qrzUsername, max_len=120)
            token_updates["qrzUsername"] = cleaned_qrz or None

        if payload.clearQrzPassword:
            token_updates["qrzPassword"] = None
        elif payload.qrzPassword is not None and payload.qrzPassword.strip():
            token_updates["qrzPassword"] = payload.qrzPassword.strip()[:200]

        if token_updates:
            new_tokens = workspace.prefs_mgr.tokens.model_copy(update=token_updates)
            workspace.prefs_mgr.save_tokens(new_tokens)
            workspace.repeater_provider.api_key = new_tokens.repeaterBookApiKey
            workspace.repeater_provider.last_status = "CONFIGURED" if new_tokens.repeaterBookApiKey else "NO_KEY"
            if any(k in token_updates for k in ("qrzUsername", "qrzPassword")):
                workspace.lookup_service.reset_qrz_session()

        return {
            "preferences": _serialize_preferences(),
            "cached_states": workspace.repeater_provider.list_cached_state_files(),
        }

    # ─── Callsign Lookup & QRZ Test ──────────────────────────────────────────

    @app.get("/api/lookup/{callsign:path}")
    async def api_lookup_callsign(callsign: str) -> dict[str, Any]:
        cleaned = clean_single_line(callsign, max_len=24).upper()
        tokens = workspace.prefs_mgr.tokens
        return await workspace.lookup_service.lookup(
            cleaned,
            qrz_user=tokens.qrzUsername,
            qrz_pass=tokens.qrzPassword,
        )

    @app.post("/api/preferences/test-qrz")
    async def api_test_qrz(payload: QrzTestRequest | None = None) -> dict[str, Any]:
        tokens = workspace.prefs_mgr.tokens
        user = (
            clean_single_line(payload.qrzUsername, max_len=120)
            if payload and payload.qrzUsername
            else (tokens.qrzUsername or "")
        )
        pwd = (
            payload.qrzPassword.strip()
            if payload and payload.qrzPassword
            else (tokens.qrzPassword or "")
        )
        return await workspace.lookup_service.test_qrz_login(user, pwd)

    # ─── NWS Route / Area Weather Alerts ─────────────────────────────────────

    @app.get("/api/nws/plan-alerts")
    async def api_nws_plan_alerts(states: str = "") -> dict[str, Any]:
        if states.strip():
            target_states = [s.strip().upper() for s in states.split(",") if s.strip()]
        else:
            target_states = list((workspace.session.summary_data or {}).get("states") or [])
        return await workspace.nws_service.get_alerts_for_states(target_states)

    # ─── Geolocation ─────────────────────────────────────────────────────────

    @app.get("/api/geolocate")
    async def api_geolocate(lat: float | None = None, lon: float | None = None) -> JSONResponse:
        """Resolve browser GPS coordinates (if provided) or detect current location via IP geolocation."""
        try:
            if lat is not None and lon is not None:
                loc_str = workspace.geocoder.reverse_geocode(lat, lon)
                return JSONResponse({"ok": True, "location": loc_str, "lat": lat, "lon": lon})
            detected = workspace.geocoder.detect_ip_location()
            return JSONResponse({"ok": True, **detected})
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Geolocation lookup failed: %s", exc)
            return JSONResponse({"ok": False, "error": "Unable to detect current location."}, status_code=200)

    # ─── Plan Assembly & Codeplug Operations ─────────────────────────────────

    @app.get("/api/plan/current")
    async def api_plan_current() -> dict[str, Any]:
        return _serialize_active_plan()

    @app.post("/api/plan/generate")
    async def api_plan_generate(payload: PlanGenerateRequest) -> dict[str, Any]:
        mode = payload.mode.strip().upper()
        if mode not in {"ROUTE_CORRIDOR", "PROXIMITY_SEARCH", "AVIATION_PLANNER"}:
            raise HTTPException(status_code=400, detail=f"Unsupported planner mode: {payload.mode}")

        include_simplex = bool(payload.include_simplex)
        repeater_access = [a.strip().upper() for a in payload.repeater_access if a.strip()] or ["OPEN"]
        sequence_order = [s.strip() for s in payload.sequence_order if s.strip()]

        all_radios = workspace.radio_mgr.list_radios()
        if not all_radios:
            raise HTTPException(status_code=500, detail="No target radio hardware specs configured")

        if payload.radio_id and workspace.radio_mgr.has_radio(payload.radio_id):
            radio_id = payload.radio_id
        elif workspace.session.radio_spec and workspace.radio_mgr.has_radio(workspace.session.radio_spec.id):
            radio_id = workspace.session.radio_spec.id
        else:
            default_pref = workspace.prefs_mgr.preferences.defaultRadioId
            radio_id = default_pref if (default_pref and workspace.radio_mgr.has_radio(default_pref)) else all_radios[0].id
            if mode == "AVIATION_PLANNER" and "Airband" not in workspace.radio_mgr.get_radio(radio_id).supportedBands:
                for r in all_radios:
                    if "Airband" in r.supportedBands:
                        radio_id = r.id
                        break

        radio_spec = workspace.radio_mgr.get_radio(radio_id)
        submitted_bands = [b.strip() for b in payload.bands if b.strip()]
        bands = submitted_bands or _default_bands_for_radio(radio_spec, mode, sequence_order)
        submitted_naming = payload.naming_format.strip().upper()
        naming_format = submitted_naming or _smart_default_naming(radio_spec, mode)

        workspace.session.deleted_keys = set()
        workspace.session.undo_stack = []

        max_age_days = getattr(workspace.prefs_mgr.preferences, "repeaterMaxAgeDays", 30)
        plan_description = clean_single_line(payload.plan_description, max_len=300)
        notices: list[dict[str, str]] = []
        map_data: dict[str, Any] = {"center": [32.35, -95.30], "zoom": 6, "channels": []}
        summary: dict[str, Any] = {
            "title": "Plan Summary",
            "subtitle": "",
            "metric_badge": "",
            "rows": [],
            "band_counts": {},
            "states": [],
        }

        if mode == "ROUTE_CORRIDOR":
            waypoints = [clean_single_line(w, max_len=120) for w in payload.waypoints if clean_single_line(w, max_len=120)]
            if len(waypoints) < 2:
                raise HTTPException(status_code=400, detail="At least 2 waypoints are required for a route corridor")
            corridor_width = float(payload.corridor_width)
            if not sequence_order:
                sequence_order = ["TEMPLATE:calling_channels", "ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"]
            if "GMRS" in radio_spec.supportedBands and "2m" not in radio_spec.supportedBands:
                if "TEMPLATE:gmrs_channels" not in sequence_order:
                    sequence_order = ["TEMPLATE:gmrs_channels"] + list(sequence_order)

            geo_points = []
            for wp in waypoints:
                try:
                    geo_points.append(workspace.geocoder.resolve(wp))
                except (ValueError, KeyError, OSError):
                    pass

            route_states = identify_states_for_route(
                waypoints,
                geo_points=geo_points,
                corridor_width_miles=corridor_width,
            )
            all_repeaters = workspace.repeater_provider.get_repeaters_for_states(
                states=route_states,
                max_age_days=max_age_days,
                allowed_use=repeater_access,
            )
            if not any(c.band == "GMRS" for c in all_repeaters):
                all_repeaters = list(all_repeaters) + workspace.repeater_provider.get_gmrs_repeaters_for_states(route_states)

            engine = RouteCorridorEngine(geocoder=workspace.geocoder)
            res = engine.plan_route(
                waypoint_names=waypoints,
                candidate_channels=all_repeaters,
                corridor_width_miles=corridor_width,
                include_simplex=include_simplex,
            )
            primary_channels = res.channels

            start_city = waypoints[0].split(",")[0].strip()
            end_city = waypoints[-1].split(",")[0].strip()
            custom_name = clean_single_line(payload.plan_name, max_len=100)
            plan_name = custom_name or f"{start_city}_to_{end_city}_Corridor"

            recipe = RadioPlannerRecipe(
                mode="ROUTE_CORRIDOR",
                name=plan_name,
                description=plan_description,
                corridor=CorridorConfig(waypoints=waypoints, corridor_width_miles=corridor_width),
                radio_target=RadioTargetConfig(
                    radio_id=radio_id,
                    programmer_format=radio_spec.programmerType,
                    include_simplex=include_simplex,
                    bands=bands,
                    modes=radio_spec.supportedModes,
                    repeater_access=repeater_access,
                    naming_format=naming_format,
                ),
                sequence_order=sequence_order,
            )

            map_data["route_coords"] = [[pt.lat, pt.lon] for pt in res.waypoints]
            map_data["waypoints"] = [
                {"name": pt.name or f"Stop {i + 1}", "lat": pt.lat, "lon": pt.lon}
                for i, pt in enumerate(res.waypoints)
            ]
            summary["title"] = "Route Waypoints & Distance"
            summary["subtitle"] = f"{len(res.waypoints)} stops • {res.total_distance_miles:.1f} miles"
            summary["metric_badge"] = f"{res.total_distance_miles:.1f} mi"
            summary["rows"] = [
                {"label": pt.name or f"Stop {i + 1}", "value": f"{dist:.1f} mi"}
                for i, (pt, dist) in enumerate(zip(res.waypoints, res.cumulative_mileages))
            ]
            summary["states"] = route_states

        elif mode == "PROXIMITY_SEARCH":
            center_loc = clean_single_line(payload.center_location, max_len=120) or "Dallas, TX"
            radius_miles = float(payload.radius_miles)
            if not sequence_order:
                sequence_order = ["TEMPLATE:calling_channels", "PROXIMITY_PLAN", "TEMPLATE:noaa_wx_channels"]
            if "GMRS" in radio_spec.supportedBands and "2m" not in radio_spec.supportedBands:
                if "TEMPLATE:gmrs_channels" not in sequence_order:
                    sequence_order = ["TEMPLATE:gmrs_channels"] + list(sequence_order)

            center_pt = None
            try:
                center_pt = workspace.geocoder.resolve(center_loc)
            except (ValueError, KeyError, OSError):
                center_pt = None

            prox_states = identify_states_for_proximity(
                center_loc,
                center_point=center_pt,
                radius_miles=radius_miles,
            )
            all_repeaters = workspace.repeater_provider.get_repeaters_for_states(
                states=prox_states,
                max_age_days=max_age_days,
                allowed_use=repeater_access,
            )
            if not any(c.band == "GMRS" for c in all_repeaters):
                all_repeaters = list(all_repeaters) + workspace.repeater_provider.get_gmrs_repeaters_for_states(prox_states)

            engine = ProximityEngine(geocoder=workspace.geocoder)
            res = engine.search_proximity(
                center_location=center_loc,
                candidate_channels=all_repeaters,
                radius_miles=radius_miles,
                include_simplex=include_simplex,
            )
            primary_channels = res.channels

            city_clean = center_loc.split(",")[0].strip()
            custom_name = clean_single_line(payload.plan_name, max_len=100)
            plan_name = custom_name or f"{city_clean}_Proximity_{int(radius_miles)}mi"
            recipe = RadioPlannerRecipe(
                mode="PROXIMITY_SEARCH",
                name=plan_name,
                description=plan_description,
                proximity=ProximityConfig(center_location=center_loc, radius_miles=radius_miles),
                radio_target=RadioTargetConfig(
                    radio_id=radio_id,
                    programmer_format=radio_spec.programmerType,
                    include_simplex=include_simplex,
                    bands=bands,
                    modes=radio_spec.supportedModes,
                    repeater_access=repeater_access,
                    naming_format=naming_format,
                ),
                sequence_order=sequence_order,
            )

            map_data["center"] = [res.center_point.lat, res.center_point.lon]
            map_data["waypoints"] = [{"name": center_loc, "lat": res.center_point.lat, "lon": res.center_point.lon}]
            map_data["rings"] = [
                {
                    "index": r_idx,
                    "start_mi": rng[0],
                    "end_mi": rng[1],
                    "color": RING_COLORS[(r_idx - 1) % len(RING_COLORS)],
                    "count": len(res.rings.get(r_idx, [])),
                }
                for r_idx, rng in sorted(res.ring_ranges.items())
            ]
            summary["title"] = "Concentric Proximity Rings"
            summary["subtitle"] = f"{center_loc} • {radius_miles:.0f} mi radius"
            summary["metric_badge"] = f"{radius_miles:.0f} mi radius"
            summary["rows"] = [
                {
                    "label": f"Ring {r_idx} ({res.ring_ranges[r_idx][0]:.0f}–{res.ring_ranges[r_idx][1]:.0f} mi)",
                    "value": f"{len(ch_list)} ch",
                    "color": RING_COLORS[(r_idx - 1) % len(RING_COLORS)],
                }
                for r_idx, ch_list in sorted(res.rings.items())
            ]
            summary["states"] = prox_states

        else:
            center_loc = clean_single_line(payload.center_location, max_len=120) or "Tyler, TX"
            radius_miles = float(payload.radius_miles)
            if not sequence_order:
                sequence_order = ["AVIATION_BLOCK"]

            if "Airband" not in radio_spec.supportedBands:
                notices.append(
                    {
                        "level": "warning",
                        "message": (
                            f"{radio_spec.brand} {radio_spec.model} does not list 'Airband' (108–137 MHz AM) in its supported hardware bands. "
                            "Airband channels are shown below for preview, or switch to an Airband-capable radio."
                        ),
                    }
                )

            has_templates = any(k.startswith("TEMPLATE:") for k in sequence_order)
            active_bands = list(set(radio_spec.supportedBands) | {"Airband"}) if has_templates else ["Airband"]
            active_modes = list(set(radio_spec.supportedModes) | {"AM"}) if has_templates else ["AM"]

            engine = AviationEngine(geocoder=workspace.geocoder, airports_provider=workspace.airports_provider)
            res = engine.plan_aviation(center_location=center_loc, radius_miles=radius_miles)
            primary_channels = res.channels

            if not res.matched_airports:
                notices.append(
                    {
                        "level": "warning",
                        "message": f"No airfields found within {radius_miles:.0f} miles of '{center_loc}'. Try increasing the search radius.",
                    }
                )

            city_clean = center_loc.split(",")[0].strip()
            custom_name = clean_single_line(payload.plan_name, max_len=100)
            plan_name = custom_name or f"{city_clean}_Aviation_{int(radius_miles)}mi"
            recipe = RadioPlannerRecipe(
                mode="AVIATION_PLANNER",
                name=plan_name,
                description=plan_description,
                aviation=AviationConfig(center_location=center_loc, radius_miles=radius_miles),
                radio_target=RadioTargetConfig(
                    radio_id=radio_id,
                    programmer_format=radio_spec.programmerType,
                    include_simplex=False,
                    bands=active_bands,
                    modes=active_modes,
                    naming_format=naming_format,
                ),
                sequence_order=sequence_order,
            )
            bands = active_bands
            map_data["center"] = [res.center_point.lat, res.center_point.lon]
            map_data["waypoints"] = [
                {"name": f"{arpt.ident} ({arpt.name})", "lat": arpt.latitude, "lon": arpt.longitude}
                for arpt in res.matched_airports
            ]
            summary["title"] = "Airfields Within Range"
            summary["subtitle"] = f"{len(res.matched_airports)} airfields within {radius_miles:.0f} mi"
            summary["metric_badge"] = f"{len(res.matched_airports)} airfields"
            summary["rows"] = [
                {"label": f"{arpt.ident} — {arpt.name}", "value": f"{dist:.1f} mi"}
                for arpt, dist in zip(res.matched_airports, res.airport_distances)
            ]

        assembly_spec = (
            radio_spec.model_copy(
                update={
                    "supportedBands": list(set(radio_spec.supportedBands) | {"Airband"}),
                    "supportedModes": list(set(radio_spec.supportedModes) | {"AM"}),
                }
            )
            if mode == "AVIATION_PLANNER"
            else radio_spec
        )

        uncondensed_spec = assembly_spec.model_copy(update={"maxNameLength": 64, "allowDots": True, "allowSpaces": True})
        raw_assembled = SequenceOrganizer.assemble(
            codeplug_name=recipe.name,
            sequence_keys=recipe.sequence_order,
            primary_channels=primary_channels,
            target_spec=uncondensed_spec,
            template_manager=workspace.template_mgr,
            allowed_bands=bands,
            allowed_modes=recipe.radio_target.modes,
            naming_format="STANDARD",
        )

        codeplug = SequenceOrganizer.assemble(
            codeplug_name=recipe.name,
            sequence_keys=recipe.sequence_order,
            primary_channels=primary_channels,
            target_spec=assembly_spec,
            template_manager=workspace.template_mgr,
            allowed_bands=bands,
            allowed_modes=recipe.radio_target.modes,
            naming_format=naming_format,
        )

        if codeplug.total_channels > radio_spec.maxChannels:
            notices.append(
                {
                    "level": "warning",
                    "message": (
                        f"Plan contains {codeplug.total_channels} channels, which exceeds {radio_spec.brand} {radio_spec.model}'s "
                        f"{radio_spec.maxChannels}-channel memory limit."
                    ),
                }
            )

        band_counts, map_channels = _compute_band_counts_and_map_channels(codeplug, bands)
        map_data["channels"] = map_channels
        summary["band_counts"] = band_counts

        workspace.session.recipe = recipe
        workspace.session.codeplug = codeplug
        workspace.session.radio_spec = radio_spec
        workspace.session.primary_channels = primary_channels
        workspace.session.raw_channels = list(raw_assembled.channels)
        workspace.session.map_data = map_data
        workspace.session.summary_data = summary
        workspace.session.notices = notices
        workspace.save_session()

        return _serialize_active_plan(
            message=f"Assembled {codeplug.total_channels} channels for {radio_spec.brand} {radio_spec.model}."
        )

    @app.post("/api/codeplug/update")
    async def api_codeplug_update(payload: CodeplugUpdateRequest) -> dict[str, Any]:
        recipe = workspace.session.recipe
        codeplug = workspace.session.codeplug
        if not recipe or not codeplug:
            raise HTTPException(status_code=400, detail="No active codeplug session.")

        spec = workspace.radio_mgr.get_radio(payload.radio_id)
        is_radio_switch = payload.radio_changed or (
            workspace.session.radio_spec is not None and workspace.session.radio_spec.id != spec.id and not payload.bands
        )
        is_gmrs_only_radio = "GMRS" in spec.supportedBands and "2m" not in spec.supportedBands

        if is_radio_switch:
            active_naming = (
                _smart_default_naming(spec, recipe.mode)
                if (not payload.naming_format or payload.radio_changed)
                else payload.naming_format.strip().upper()
            )
            active_bands = _default_bands_for_radio(spec, recipe.mode, recipe.sequence_order)
            if is_gmrs_only_radio and "TEMPLATE:gmrs_channels" not in recipe.sequence_order:
                recipe.sequence_order = ["TEMPLATE:gmrs_channels"] + list(recipe.sequence_order)
        else:
            active_naming = (
                payload.naming_format.strip().upper()
                or recipe.radio_target.naming_format
                or _smart_default_naming(spec, recipe.mode)
            )
            active_bands = (
                [b for b in payload.bands if b in spec.supportedBands]
                if payload.bands
                else [b for b in recipe.radio_target.bands if b in spec.supportedBands]
            )
            if not active_bands:
                active_bands = _default_bands_for_radio(spec, recipe.mode, recipe.sequence_order)
            if "GMRS" in spec.supportedBands:
                if payload.include_gmrs_std:
                    if "TEMPLATE:gmrs_channels" not in recipe.sequence_order:
                        recipe.sequence_order = ["TEMPLATE:gmrs_channels"] + list(recipe.sequence_order)
                    if "GMRS" not in active_bands:
                        active_bands.append("GMRS")
                else:
                    recipe.sequence_order = [k for k in recipe.sequence_order if k != "TEMPLATE:gmrs_channels"]

        recipe.radio_target.radio_id = spec.id
        recipe.radio_target.programmer_format = spec.programmerType
        recipe.radio_target.naming_format = active_naming
        recipe.radio_target.bands = active_bands
        recipe.radio_target.modes = list(
            set(spec.supportedModes) | ({"AM"} if recipe.mode == "AVIATION_PLANNER" else set())
        )

        assembly_spec = (
            spec.model_copy(
                update={
                    "supportedBands": list(set(spec.supportedBands) | {"Airband"}),
                    "supportedModes": list(set(spec.supportedModes) | {"AM"}),
                }
            )
            if recipe.mode == "AVIATION_PLANNER"
            else spec
        )

        updated_codeplug = SequenceOrganizer.assemble(
            codeplug_name=recipe.name,
            sequence_keys=recipe.sequence_order,
            primary_channels=workspace.session.primary_channels,
            target_spec=assembly_spec,
            template_manager=workspace.template_mgr,
            allowed_bands=active_bands,
            allowed_modes=recipe.radio_target.modes,
            naming_format=active_naming,
        )
        if workspace.session.deleted_keys:
            kept = [
                ch
                for ch in updated_codeplug.channels
                if (round(ch.rxFreq, 4), ch.callsign or "", ch.city or "") not in workspace.session.deleted_keys
            ]
            updated_codeplug = Codeplug(name=updated_codeplug.name, channels=kept).renumbered(
                start_slot=spec.startChannel
            )

        uncondensed_spec = assembly_spec.model_copy(update={"maxNameLength": 64, "allowDots": True, "allowSpaces": True})
        raw_assembled = SequenceOrganizer.assemble(
            codeplug_name=recipe.name,
            sequence_keys=recipe.sequence_order,
            primary_channels=workspace.session.primary_channels,
            target_spec=uncondensed_spec,
            template_manager=workspace.template_mgr,
            allowed_bands=active_bands,
            allowed_modes=recipe.radio_target.modes,
            naming_format="STANDARD",
        )

        notices: list[dict[str, str]] = []
        if recipe.mode == "AVIATION_PLANNER" and "Airband" not in spec.supportedBands:
            notices.append(
                {
                    "level": "warning",
                    "message": f"{spec.brand} {spec.model} does not list 'Airband' in its supported hardware bands.",
                }
            )
        if updated_codeplug.total_channels > spec.maxChannels:
            notices.append(
                {
                    "level": "warning",
                    "message": (
                        f"Plan contains {updated_codeplug.total_channels} channels, exceeding {spec.brand} {spec.model}'s "
                        f"{spec.maxChannels}-channel limit."
                    ),
                }
            )

        workspace.session.codeplug = updated_codeplug
        workspace.session.raw_channels = list(raw_assembled.channels)
        workspace.session.radio_spec = spec
        workspace.session.notices = notices

        band_counts, map_channels = _compute_band_counts_and_map_channels(updated_codeplug, active_bands)
        workspace.session.summary_data["band_counts"] = band_counts
        workspace.session.map_data["channels"] = map_channels
        workspace.save_session()

        end_slot = spec.startChannel + updated_codeplug.total_channels - 1 if updated_codeplug.total_channels else spec.startChannel
        return _serialize_active_plan(
            message=(
                f"Targeted {spec.brand} {spec.model} • Bands: {', '.join(active_bands)} • "
                f"Naming: {active_naming} (Slots {spec.startChannel}..{end_slot})"
            )
        )

    @app.post("/api/codeplug/delete-channels")
    async def api_delete_channels(payload: DeleteChannelsRequest) -> dict[str, Any]:
        codeplug = workspace.session.codeplug
        recipe = workspace.session.recipe
        spec = workspace.session.radio_spec
        if not codeplug or not recipe or not spec:
            raise HTTPException(status_code=400, detail="No active codeplug session.")

        selected_set = set(payload.slots)
        if not selected_set:
            raise HTTPException(status_code=400, detail="No channel slots selected for deletion.")

        deleted_channels = [ch for ch in codeplug.channels if ch.number in selected_set]
        if not deleted_channels:
            raise HTTPException(status_code=404, detail="Selected channel slot(s) not found.")

        workspace.session.push_undo(label=f"Delete {len(deleted_channels)} channel(s)")
        remaining_channels = [ch for ch in codeplug.channels if ch.number not in selected_set]

        if workspace.session.raw_channels and len(workspace.session.raw_channels) == len(codeplug.channels):
            workspace.session.raw_channels = [
                raw_ch
                for raw_ch, cur_ch in zip(workspace.session.raw_channels, codeplug.channels)
                if cur_ch.number not in selected_set
            ]

        del_keys = {(round(ch.rxFreq, 4), ch.callsign or "", ch.city or "") for ch in deleted_channels}
        workspace.session.deleted_keys.update(del_keys)
        if workspace.session.primary_channels:
            workspace.session.primary_channels = [
                ch
                for ch in workspace.session.primary_channels
                if (round(ch.rxFreq, 4), ch.callsign or "", ch.city or "") not in del_keys
            ]

        updated = Codeplug(name=codeplug.name, channels=remaining_channels).renumbered(start_slot=spec.startChannel)
        workspace.session.codeplug = updated

        band_counts, map_channels = _compute_band_counts_and_map_channels(updated, recipe.radio_target.bands)
        workspace.session.summary_data["band_counts"] = band_counts
        workspace.session.map_data["channels"] = map_channels
        workspace.save_session()

        return _serialize_active_plan(
            message=f"Deleted {len(deleted_channels)} channel(s). Renumbered {updated.total_channels} remaining channel(s)."
        )

    @app.post("/api/codeplug/undo-delete")
    async def api_undo_delete() -> dict[str, Any]:
        codeplug = workspace.session.codeplug
        recipe = workspace.session.recipe
        spec = workspace.session.radio_spec
        if not codeplug or not recipe or not spec:
            raise HTTPException(status_code=400, detail="No active codeplug session.")

        snap = workspace.session.pop_undo()
        if not snap:
            raise HTTPException(status_code=400, detail="Nothing to undo.")

        restored = Codeplug(name=codeplug.name, channels=snap.channels).renumbered(start_slot=spec.startChannel)
        workspace.session.codeplug = restored
        workspace.session.raw_channels = list(snap.raw_channels)
        workspace.session.primary_channels = list(snap.primary_channels)
        workspace.session.deleted_keys = set(snap.deleted_keys)

        band_counts, map_channels = _compute_band_counts_and_map_channels(restored, recipe.radio_target.bands)
        workspace.session.summary_data["band_counts"] = band_counts
        workspace.session.map_data["channels"] = map_channels
        workspace.save_session()

        return _serialize_active_plan(message=f"Undid: {snap.label} ({restored.total_channels} channels).")

    @app.patch("/api/codeplug/channels/{slot}")
    async def api_edit_channel(slot: int, payload: ChannelEditRequest) -> dict[str, Any]:
        """Inline channel editor: modify a single channel slot in the active codeplug."""
        codeplug = workspace.session.codeplug
        recipe = workspace.session.recipe
        spec = workspace.session.radio_spec
        if not codeplug or not recipe or not spec:
            raise HTTPException(status_code=400, detail="No active codeplug session.")

        idx = next((i for i, ch in enumerate(codeplug.channels) if ch.number == slot), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Channel slot {slot} not found.")

        cur = codeplug.channels[idx]
        workspace.session.push_undo(label=f"Edit slot #{slot} ({cur.name})")

        rx = round(float(payload.rxFreq), 5) if payload.rxFreq is not None else cur.rxFreq
        off_dir = cur.offsetDir
        if payload.offsetDir is not None:
            cand_dir = payload.offsetDir.strip()
            if cand_dir not in {"off", "+", "-"}:
                raise HTTPException(status_code=400, detail="offsetDir must be 'off', '+', or '-'")
            off_dir = cand_dir

        off_val = round(abs(float(payload.offset)), 5) if payload.offset is not None else cur.offset
        if off_dir == "+":
            tx = round(rx + off_val, 5)
        elif off_dir == "-":
            tx = round(rx - off_val, 5)
        else:
            off_val = 0.0
            tx = rx

        new_name = cur.name
        if payload.name is not None:
            cleaned_name = clean_single_line(payload.name, max_len=64)
            if not cleaned_name:
                raise HTTPException(status_code=400, detail="Channel LCD name cannot be empty.")
            if not spec.allowDots:
                cleaned_name = cleaned_name.replace(".", "")
            if not spec.allowSpaces:
                cleaned_name = cleaned_name.replace(" ", "")
            new_name = cleaned_name[: spec.maxNameLength]

        tone_mode = cur.toneMode
        if payload.toneMode is not None:
            cand_tm = payload.toneMode.strip()
            if cand_tm not in {"None", "Tone", "TSQL", "DCS", "DTCS"}:
                raise HTTPException(status_code=400, detail="Invalid toneMode.")
            tone_mode = cand_tm

        ctcss = cur.ctcss
        rx_ctcss = cur.rxCtcss
        dcs = cur.dcs
        rx_dcs = cur.rxDcs
        if tone_mode == "None":
            ctcss = "None"
            rx_ctcss = "None"
            dcs = "None"
            rx_dcs = "None"
        elif tone_mode in {"Tone", "TSQL"}:
            if payload.ctcss is not None:
                ctcss = clean_single_line(payload.ctcss, max_len=12) or "88.5"
            elif ctcss == "None":
                ctcss = "88.5"
            rx_ctcss = ctcss if tone_mode == "TSQL" else "None"
            dcs = "None"
            rx_dcs = "None"
        elif tone_mode in {"DCS", "DTCS"}:
            if payload.dcs is not None:
                dcs = clean_single_line(payload.dcs, max_len=12).lstrip("Dd") or "023"
            elif dcs == "None":
                dcs = "023"
            rx_dcs = dcs
            ctcss = "None"
            rx_ctcss = "None"

        mode_val = clean_single_line(payload.mode, max_len=12).upper() if payload.mode else cur.mode
        power_val = cur.power
        if payload.power is not None:
            p_cand = clean_single_line(payload.power, max_len=12).capitalize()
            if p_cand in {"High", "Mid", "Low"}:
                power_val = p_cand

        callsign_val = (
            (clean_single_line(payload.callsign, max_len=16).upper() or None)
            if payload.callsign is not None
            else cur.callsign
        )
        city_val = (
            (clean_single_line(payload.city, max_len=64) or None)
            if payload.city is not None
            else cur.city
        )
        state_val = (
            (clean_single_line(payload.state, max_len=8).upper() or None)
            if payload.state is not None
            else cur.state
        )
        comment_val = (
            clean_single_line(payload.comment, max_len=240)
            if payload.comment is not None
            else cur.comment
        )

        edited = cur.model_copy(
            update={
                "name": new_name,
                "callsign": callsign_val,
                "rxFreq": rx,
                "txFreq": tx,
                "offset": off_val,
                "offsetDir": off_dir,
                "mode": mode_val,
                "power": power_val,
                "toneMode": tone_mode,
                "ctcss": ctcss,
                "rxCtcss": rx_ctcss,
                "dcs": dcs,
                "rxDcs": rx_dcs,
                "city": city_val,
                "state": state_val,
                "comment": comment_val,
            }
        )

        updated_channels = list(codeplug.channels)
        updated_channels[idx] = edited
        updated_cp = Codeplug(name=codeplug.name, channels=updated_channels)
        workspace.session.codeplug = updated_cp
        if idx < len(workspace.session.raw_channels):
            workspace.session.raw_channels[idx] = edited

        band_counts, map_channels = _compute_band_counts_and_map_channels(updated_cp, recipe.radio_target.bands)
        workspace.session.summary_data["band_counts"] = band_counts
        workspace.session.map_data["channels"] = map_channels
        workspace.save_session()

        return _serialize_active_plan(message=f"Updated channel slot #{slot} ({edited.name}).")

    @app.get("/api/codeplug/channels/{slot}/net-logger-preset")
    async def api_channel_net_logger_preset(slot: int) -> dict[str, Any]:
        """Export a single codeplug channel as a W5CDN Net Logger repeater preset JSON object."""
        codeplug = workspace.session.codeplug
        if not codeplug:
            raise HTTPException(status_code=400, detail="No active codeplug session.")
        ch = next((c for c in codeplug.channels if c.number == slot), None)
        if ch is None:
            raise HTTPException(status_code=404, detail=f"Channel slot {slot} not found.")

        tone_parts: list[str] = []
        if not ch.is_simplex and ch.offsetDir in {"+", "-"} and ch.offset > 0:
            tone_parts.append(f"{ch.offsetDir}{ch.offset:.3f} MHz")
        if ch.toneMode in {"Tone", "TSQL"} and ch.ctcss and ch.ctcss != "None":
            tone_parts.append(f"PL {ch.ctcss}")
        elif ch.toneMode in {"DCS", "DTCS"} and ch.dcs and ch.dcs != "None":
            tone_parts.append(f"DCS {ch.dcs}")
        elif ch.is_simplex:
            tone_parts.append("Simplex")

        location = f"{ch.city}, {ch.state}".strip(", ") if (ch.city or ch.state) else ""
        preset = {
            "name": ch.name,
            "frequency": f"{ch.rxFreq:.4f} MHz",
            "band": ch.band,
            "mode": ch.mode,
            "tone_offset": " / ".join(tone_parts) or "CSQ",
            "callsign": ch.callsign or "",
            "location": location,
        }
        return {"slot": slot, "preset": preset}

    @app.post("/api/codeplug/expand-dmr")
    async def api_expand_dmr() -> dict[str, Any]:
        codeplug = workspace.session.codeplug
        recipe = workspace.session.recipe
        spec = workspace.session.radio_spec
        if not codeplug or not recipe or not spec:
            raise HTTPException(status_code=400, detail="No active codeplug session.")

        expanded: list[RadioChannel] = []
        dmr_count = 0
        for ch in codeplug.channels:
            if ch.mode.upper() == "DMR":
                dmr_count += 1
                expanded.extend(workspace.radio_id_provider.duplicate_channel_for_talkgroups(ch))
            else:
                expanded.append(ch)

        if dmr_count > 0:
            workspace.session.push_undo(label=f"Expand {dmr_count} DMR channel(s)")
            updated = Codeplug(name=codeplug.name, channels=expanded).renumbered(start_slot=spec.startChannel)
            workspace.session.codeplug = updated
            band_counts, map_channels = _compute_band_counts_and_map_channels(updated, recipe.radio_target.bands)
            workspace.session.summary_data["band_counts"] = band_counts
            workspace.session.map_data["channels"] = map_channels
            workspace.save_session()
            msg = f"Expanded {dmr_count} DMR channel(s) across standard Talkgroups ({updated.total_channels} total)."
        else:
            msg = "No DMR channels present in current codeplug."

        return _serialize_active_plan(message=msg)

    @app.get("/api/codeplug/report")
    async def api_codeplug_report() -> dict[str, Any]:
        """Generate printable pocket reference card and shareable plain-text plan report."""
        codeplug = workspace.session.codeplug
        recipe = workspace.session.recipe
        spec = workspace.session.radio_spec
        if not codeplug or not recipe or not spec:
            raise HTTPException(status_code=400, detail="No active codeplug session.")

        summary = workspace.session.summary_data or {}
        band_counts = summary.get("band_counts", {})
        repeater_cnt = sum(1 for c in codeplug.channels if c.specialType == "REPEATERS")
        simplex_cnt = sum(1 for c in codeplug.channels if c.is_simplex)
        dmr_cnt = sum(1 for c in codeplug.channels if c.mode.upper() == "DMR")
        report_text = _build_pocket_report_text(recipe, codeplug, spec, summary)

        return {
            "name": codeplug.name,
            "mode": recipe.mode,
            "description": recipe.description,
            "generated_at": _utc_now_iso(),
            "operator": workspace.prefs_mgr.preferences.callsign,
            "radio": f"{spec.brand} {spec.model}",
            "radio_id": spec.id,
            "max_channels": spec.maxChannels,
            "lcd_limit": spec.maxNameLength,
            "programmer": recipe.radio_target.programmer_format or spec.programmerType,
            "naming_format": recipe.radio_target.naming_format,
            "coverage": summary.get("subtitle", ""),
            "states": summary.get("states", []),
            "kpis": {
                "total_channels": codeplug.total_channels,
                "capacity_pct": round((codeplug.total_channels / max(spec.maxChannels, 1)) * 100, 1),
                "repeaters": repeater_cnt,
                "simplex": simplex_cnt,
                "dmr": dmr_cnt,
                "bands_active": sum(1 for cnt in band_counts.values() if cnt > 0),
            },
            "channels": [_serialize_channel(ch) for ch in codeplug.channels],
            "text": report_text,
            "filename": f"{DataSanitizer.sanitize_filename(codeplug.name)}_pocket_card.txt",
        }

    @app.post("/api/codeplug/export")
    async def api_codeplug_export(payload: ExportCsvRequest) -> Response:
        """Export active codeplug to ./exports/ AND return as a browser CSV download."""
        codeplug = workspace.session.codeplug
        spec = workspace.session.radio_spec
        if not codeplug or not spec:
            raise HTTPException(status_code=400, detail="No active codeplug to export.")

        raw_name = clean_single_line(payload.filename, max_len=140) or "codeplug.csv"
        if not raw_name.lower().endswith(".csv"):
            raw_name += ".csv"
        out_dir = Path("./exports").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        dest_path = safe_child_path(out_dir, raw_name)

        programmer = clean_single_line(payload.programmer_type, max_len=32).upper() or "CHIRP"
        export_codeplug(codeplug, spec, dest_path, programmer_type=programmer)
        exporter = get_exporter(programmer)
        csv_content = exporter.to_csv_string(codeplug, spec)

        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{dest_path.name}"'},
        )

    # ─── Saved Recipes API ───────────────────────────────────────────────────

    @app.get("/api/recipes")
    async def api_list_recipes() -> dict[str, Any]:
        return {
            "recipes_dir": str(get_recipes_dir()),
            "recipes": _serialize_recipes(),
        }

    @app.get("/api/recipes/{filename}")
    async def api_get_recipe(filename: str) -> dict[str, Any]:
        recipes_dir = get_recipes_dir()
        target = safe_child_path(recipes_dir, filename)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Recipe file not found")
        try:
            rec = RadioPlannerRecipe.from_yaml_file(target)
        except (OSError, ValueError, YamlDiagnosticError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid recipe YAML: {exc}") from exc
        return {
            "filename": target.name,
            "recipe": rec.model_dump(),
        }

    @app.post("/api/recipes/save")
    async def api_save_recipe(payload: RecipeSaveRequest) -> dict[str, Any]:
        recipe = workspace.session.recipe
        codeplug = workspace.session.codeplug
        spec = workspace.session.radio_spec
        if not recipe or not codeplug or not spec:
            raise HTTPException(status_code=400, detail="No active recipe to save.")

        recipe.name = clean_single_line(payload.name, max_len=100) or recipe.name
        recipe.description = clean_single_line(payload.description, max_len=300)
        recipes_dir = get_recipes_dir()
        recipes_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{DataSanitizer.sanitize_filename(recipe.name)}.yaml"
        dest_yaml = safe_child_path(recipes_dir, fname)
        recipe.to_yaml_file(dest_yaml)

        return {
            "saved": True,
            "filename": dest_yaml.name,
            "path": str(dest_yaml),
            "message": f"Saved radio-agnostic recipe '{recipe.name}' to {dest_yaml.name}",
            "recipes": _serialize_recipes(),
        }

    @app.post("/api/recipes/upload")
    async def api_upload_recipe(payload: RecipeUploadRequest) -> dict[str, Any]:
        try:
            recipe = RadioPlannerRecipe.from_yaml_text(payload.yaml_text)
        except (ValueError, YamlDiagnosticError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid YAML recipe: {exc}") from exc

        recipes_dir = get_recipes_dir()
        recipes_dir.mkdir(parents=True, exist_ok=True)
        base_name = clean_single_line(payload.filename, max_len=120) or f"{DataSanitizer.sanitize_filename(recipe.name)}.yaml"
        if not base_name.lower().endswith((".yaml", ".yml")):
            base_name += ".yaml"
        dest = safe_child_path(recipes_dir, base_name)
        recipe.to_yaml_file(dest)
        return {
            "uploaded": True,
            "filename": dest.name,
            "recipe": recipe.model_dump(),
            "recipes": _serialize_recipes(),
        }

    @app.delete("/api/recipes/{filename}")
    async def api_delete_recipe(filename: str) -> dict[str, Any]:
        recipes_dir = get_recipes_dir()
        target = safe_child_path(recipes_dir, filename)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Recipe file not found")
        target.unlink()
        return {"deleted": True, "filename": target.name, "recipes": _serialize_recipes()}

    # ─── Preset Templates API ────────────────────────────────────────────────

    @app.get("/api/templates")
    async def api_list_templates() -> dict[str, Any]:
        return {
            "core_templates_dir": str(workspace.template_mgr.app_dir),
            "user_templates_dir": str(workspace.template_mgr.user_dir),
            "templates": _serialize_templates(),
        }

    @app.post("/api/templates")
    async def api_save_template(payload: TemplateSaveRequest) -> dict[str, Any]:
        clean_id = DataSanitizer.sanitize_filename(payload.id.strip().lower()).replace("-", "_")
        if not clean_id:
            raise HTTPException(status_code=400, detail="Template ID slug is required.")
        channel_items = _parse_template_channel_payloads(payload.channels)
        updated_tpl = PresetTemplateFile(
            id=clean_id,
            name=clean_single_line(payload.name, max_len=100) or clean_id,
            description=clean_single_line(payload.description, max_len=240),
            tagText=clean_single_line(payload.tagText, max_len=24).upper() or "PRESET",
            tagColorHex=clean_single_line(payload.tagColorHex, max_len=16) or "#00BCD4",
            channels=channel_items,
        )
        dest = workspace.template_mgr.save_core_template(updated_tpl)
        return {
            "saved": True,
            "id": clean_id,
            "filename": dest.name,
            "message": f"Saved {len(channel_items)} channel(s) to template {dest.name}",
            "templates": _serialize_templates(),
        }

    @app.post("/api/templates/import")
    async def api_import_template(payload: TemplateImportRequest) -> dict[str, Any]:
        clean_id = DataSanitizer.sanitize_filename(payload.id.strip().lower()).replace("-", "_")
        if not clean_id:
            raise HTTPException(status_code=400, detail="Template ID slug is required.")
        fname = payload.filename.lower()
        try:
            if fname.endswith((".yaml", ".yml")):
                data = parse_yaml_text(payload.content)
                new_tpl = PresetTemplateFile.model_validate(data)
            elif fname.endswith(".json") or payload.content.lstrip().startswith(("{", "[")):
                new_tpl = _parse_net_logger_json_to_template(
                    clean_id=clean_id,
                    name=payload.name,
                    description=payload.description,
                    tag_text=payload.tagText or "NETLOG",
                    raw_json=payload.content,
                )
            else:
                new_tpl = PresetTemplateFile(
                    id=clean_id,
                    name=clean_single_line(payload.name, max_len=100) or clean_id,
                    description=clean_single_line(payload.description, max_len=240),
                    tagText=clean_single_line(payload.tagText, max_len=24).upper() or "CUSTOM",
                    tagColorHex="#4CAF50",
                    rawCsvContent=payload.content,
                )
        except (ValueError, YamlDiagnosticError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=f"Failed to parse imported template: {exc}") from exc
        workspace.template_mgr.save_core_template(new_tpl)
        return {
            "imported": True,
            "id": new_tpl.id,
            "message": f"Imported template '{new_tpl.name}' ({len(new_tpl.channels)} channels).",
            "templates": _serialize_templates(),
        }

    @app.post("/api/templates/import-net-logger")
    async def api_import_net_logger_template(payload: NetLoggerImportRequest) -> dict[str, Any]:
        clean_id = DataSanitizer.sanitize_filename(payload.id.strip().lower()).replace("-", "_")
        if not clean_id:
            raise HTTPException(status_code=400, detail="Template ID slug is required.")
        try:
            new_tpl = _parse_net_logger_json_to_template(
                clean_id=clean_id,
                name=payload.name,
                description=payload.description,
                tag_text=payload.tagText,
                raw_json=payload.json_text,
            )
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=f"Failed to parse Net Logger JSON: {exc}") from exc
        workspace.template_mgr.save_core_template(new_tpl)
        return {
            "imported": True,
            "id": new_tpl.id,
            "message": f"Imported {len(new_tpl.channels)} Net Logger preset(s) into template '{new_tpl.name}'.",
            "templates": _serialize_templates(),
        }

    @app.delete("/api/templates/{tpl_id}")
    async def api_delete_template(tpl_id: str) -> dict[str, Any]:
        clean_id = clean_single_line(tpl_id, max_len=64)
        if clean_id in {"calling_channels", "noaa_wx_channels", "gmrs_channels"}:
            raise HTTPException(status_code=400, detail="Built-in system templates cannot be deleted.")
        deleted = workspace.template_mgr.delete_template(clean_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Template '{clean_id}' not found.")
        return {"deleted": True, "id": clean_id, "templates": _serialize_templates()}

    # ─── Radios & Hardware Specs API ─────────────────────────────────────────

    @app.get("/api/radios")
    async def api_list_radios() -> dict[str, Any]:
        return {"radios": _serialize_radios()}

    @app.get("/api/radios/{radio_id}/naming-previews")
    async def api_radio_naming_previews(radio_id: str, mode: str = "ROUTE_CORRIDOR") -> dict[str, Any]:
        spec = workspace.radio_mgr.get_radio(radio_id)
        return {
            "radio": spec.model_dump(),
            "naming_previews": _build_naming_previews(spec, mode=mode),
        }

    @app.post("/api/radios")
    async def api_save_radio(payload: RadioSaveRequest) -> dict[str, Any]:
        clean_id = DataSanitizer.sanitize_filename(payload.id.strip().lower()).replace("-", "_")
        if not clean_id:
            raise HTTPException(status_code=400, detail="Unique radio ID slug is required.")
        existing_cols: list[str] = []
        if workspace.radio_mgr.has_radio(clean_id):
            existing_cols = workspace.radio_mgr.get_radio(clean_id).columns

        bands = [clean_single_line(b, max_len=24) for b in payload.supportedBands if clean_single_line(b, max_len=24)]
        modes = [clean_single_line(m, max_len=16).upper() for m in payload.supportedModes if clean_single_line(m, max_len=16)]
        if not bands:
            bands = ["2m", "70cm", "WX"]
        if not modes:
            modes = ["FM"]

        spec = TargetRadioSpec(
            id=clean_id,
            brand=clean_single_line(payload.brand, max_len=64),
            model=clean_single_line(payload.model, max_len=64),
            description=clean_single_line(payload.description, max_len=200) or f"{payload.brand} {payload.model}",
            startChannel=payload.startChannel,
            maxChannels=payload.maxChannels,
            maxNameLength=payload.maxNameLength,
            programmerType=clean_single_line(payload.programmerType, max_len=32).upper() or "RT_SYSTEMS",
            allowDots=payload.allowDots,
            allowSpaces=payload.allowSpaces,
            supportedBands=bands,
            supportedModes=modes,
            columns=existing_cols,
        )
        workspace.radio_mgr.save_user_radio(spec)
        return {
            "saved": True,
            "radio": spec.model_dump(),
            "message": f"Saved radio specification {spec.brand} {spec.model}",
            "radios": _serialize_radios(),
        }

    @app.delete("/api/radios/{radio_id}")
    async def api_delete_radio(radio_id: str) -> dict[str, Any]:
        clean_id = clean_single_line(radio_id, max_len=64)
        deleted = workspace.radio_mgr.delete_user_radio(clean_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Custom user radio '{clean_id}' not found.")
        return {"deleted": True, "id": clean_id, "radios": _serialize_radios()}

    # ─── Backup & Restore Archive API ────────────────────────────────────────

    @app.get("/api/backup/export")
    async def api_backup_export(include_tokens: bool = False) -> Response:
        archive = _create_config_backup_zip_bytes(include_tokens=include_tokens)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        fname = f"radioplanner_backup_{stamp}.zip"
        return Response(
            content=archive,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    @app.post("/api/backup/restore")
    async def api_backup_restore(request: Request) -> dict[str, Any]:
        raw = await request.body()
        res = _restore_config_backup_zip_bytes(raw)
        res["preferences"] = _serialize_preferences()
        res["radios"] = _serialize_radios()
        res["templates"] = _serialize_templates()
        res["recipes"] = _serialize_recipes()
        return res

    # ─── Self-Update API ─────────────────────────────────────────────────────

    @app.get("/api/update/check")
    async def api_update_check() -> dict[str, Any]:
        return await check_for_update(current_version=APP_VERSION, data_dir=BASE_DIR)

    @app.post("/api/update/apply")
    async def api_update_apply() -> dict[str, Any]:
        mode = detect_install_mode(BASE_DIR)
        config_home = get_radioplanner_home()
        if mode == "git":
            try:
                res = apply_git_update(BASE_DIR, config_home)
            except UpdateError as exc:
                raise HTTPException(status_code=400, detail=safe_error_message(exc)) from exc
            shutdown_manager.schedule(delay_seconds=1.5)
            return res

        if mode == "standalone":
            info = await check_for_update(current_version=APP_VERSION, data_dir=BASE_DIR)
            if not info.get("update_available"):
                return {
                    "ok": True,
                    "mode": "standalone",
                    "restart_required": False,
                    "message": info.get("message") or "Already up to date.",
                }
            if not info.get("asset_url") or not info.get("checksum_url"):
                raise HTTPException(
                    status_code=400,
                    detail="No matching standalone bundle or SHA256SUMS.txt found on the latest GitHub release.",
                )
            try:
                res = await apply_standalone_update(
                    data_dir=BASE_DIR,
                    config_home=config_home,
                    asset_name=str(info["asset_name"]),
                    asset_url=str(info["asset_url"]),
                    checksum_url=str(info["checksum_url"]),
                    current_version=APP_VERSION,
                )
            except UpdateError as exc:
                raise HTTPException(status_code=400, detail=safe_error_message(exc)) from exc
            shutdown_manager.schedule(delay_seconds=1.2)
            return res

        raise HTTPException(
            status_code=400,
            detail="Automatic self-update is only available for Git checkouts or Standalone bundles.",
        )

    return app


app = create_app()
