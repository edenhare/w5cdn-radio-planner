"""FastAPI + HTMX Web Application for RadioPlanner."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cli.wizard.band_selector import (
    AVIATION_NAMING_FORMAT_OPTIONS,
    NAMING_FORMAT_OPTIONS,
)
from core.config.paths import get_recipes_dir
from core.config.recipe import (
    AviationConfig,
    CorridorConfig,
    ProximityConfig,
    RadioPlannerRecipe,
    RadioTargetConfig,
)
from core.config.yaml_loader import parse_yaml_text
from core.engines.aviation import AviationEngine
from core.engines.proximity import ProximityEngine
from core.engines.route_corridor import RouteCorridorEngine
from core.engines.sequence import SequenceOrganizer
from core.exporters import export_codeplug, get_exporter
from core.models.channel import RadioChannel
from core.models.codeplug import Codeplug
from core.models.radio_spec import TargetRadioSpec
from core.models.template import PresetTemplateFile, TemplateChannelItem
from core.providers.repeaterbook import (
    identify_states_for_proximity,
    identify_states_for_route,
)
from core.sanitizers.condenser import NameCondenser
from core.sanitizers.sanitizer import DataSanitizer
from web.state import workspace

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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
    "#10b981",  # Ring 1: Emerald
    "#06b6d4",  # Ring 2: Cyan
    "#3b82f6",  # Ring 3: Blue
    "#a855f7",  # Ring 4: Purple
    "#f59e0b",  # Ring 5: Amber
    "#f43f5e",  # Ring 6: Rose
    "#ec4899",  # Ring 7: Pink
    "#84cc16",  # Ring 8: Lime
]


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


def _base_context(request: Request, active_nav: str = "ROUTE_CORRIDOR") -> dict[str, Any]:
    """Build standard template context shared across all views."""
    return {
        "request": request,
        "active_nav": active_nav,
        "prefs": workspace.prefs_mgr.preferences,
        "tokens": workspace.prefs_mgr.tokens,
        "has_api_key": workspace.repeater_provider.has_api_key(),
        "all_radios": workspace.radio_mgr.list_radios(),
    }


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


def _build_sequence_blocks(
    sequence_keys: list[str],
    mode: str = "ROUTE_CORRIDOR",
) -> list[dict[str, Any]]:
    """Hydrate sequence keys into displayable block descriptors."""
    primary_map = {
        "ROUTE_CORRIDOR": ("ROUTE_PLAN", "Highway Route Corridor Repeaters", "Primary Route"),
        "PROXIMITY_SEARCH": ("PROXIMITY_PLAN", "Radial Proximity Ring Repeaters", "Primary Rings"),
        "AVIATION_PLANNER": ("AVIATION_BLOCK", "Local Airport Aviation Channels", "Primary Aviation"),
    }
    prim_key, prim_title, prim_badge = primary_map.get(mode, primary_map["ROUTE_CORRIDOR"])

    blocks: list[dict[str, Any]] = []
    for key in sequence_keys:
        if key in {"ROUTE_PLAN", "PROXIMITY_PLAN", "AVIATION_BLOCK"}:
            blocks.append(
                {
                    "key": prim_key,
                    "title": prim_title,
                    "badge": prim_badge,
                    "is_primary": True,
                }
            )
        elif key.startswith("TEMPLATE:"):
            tpl_id = key.split(":", 1)[1]
            if workspace.template_mgr.has_template(tpl_id):
                tpl = workspace.template_mgr.get_template(tpl_id)
                blocks.append(
                    {
                        "key": key,
                        "title": tpl.name,
                        "badge": tpl.tagText,
                        "is_primary": False,
                    }
                )
            else:
                blocks.append(
                    {
                        "key": key,
                        "title": f"Template ({tpl_id})",
                        "badge": "TEMPLATE",
                        "is_primary": False,
                    }
                )
    return blocks


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


def _default_bands_for_radio(spec: TargetRadioSpec, mode: str, sequence_order: list[str] | None = None) -> list[str]:
    """Return default active frequency bands for a target radio and operating mode."""
    if mode.upper() == "AVIATION_PLANNER":
        has_templates = any(k.startswith("TEMPLATE:") for k in (sequence_order or []))
        return list(set(spec.supportedBands) | {"Airband"}) if has_templates else ["Airband"]
    non_air = [b for b in spec.supportedBands if b.lower() != "airband"]
    return non_air if non_air else list(spec.supportedBands)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="RadioPlanner Web Studio", version="0.2.0")
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    @app.get("/planner", response_class=HTMLResponse)
    async def planner_page(
        request: Request,
        mode: str = "ROUTE_CORRIDOR",
        recipe_file: str | None = None,
    ) -> HTMLResponse:
        initial_recipe: RadioPlannerRecipe | None = None
        loaded_recipe_file: str | None = None

        if recipe_file:
            target_path = get_recipes_dir() / Path(recipe_file).name
            if target_path.is_file():
                try:
                    initial_recipe = RadioPlannerRecipe.from_yaml_file(target_path)
                    mode = initial_recipe.mode
                    if mode == "PRESET_TEMPLATES":
                        mode = "ROUTE_CORRIDOR"
                    loaded_recipe_file = target_path.name
                except Exception:
                    initial_recipe = None

        mode_upper = mode.upper()
        if mode_upper not in {"ROUTE_CORRIDOR", "PROXIMITY_SEARCH", "AVIATION_PLANNER"}:
            mode_upper = "ROUTE_CORRIDOR"

        # Determine initial values from recipe or preferences
        prefs = workspace.prefs_mgr.preferences
        all_radios = workspace.radio_mgr.list_radios()
        radios_by_brand: dict[str, list[TargetRadioSpec]] = {}
        for r in all_radios:
            radios_by_brand.setdefault(r.brand, []).append(r)

        # Saved recipes are radio-agnostic; default to user preference defaultRadioId or first available radio
        radio_id = prefs.defaultRadioId or (all_radios[0].id if all_radios else "baofeng_5rm")
        if not workspace.radio_mgr.has_radio(radio_id):
            radio_id = all_radios[0].id
        selected_radio = workspace.radio_mgr.get_radio(radio_id)

        # In Aviation mode, if default radio does not support Airband, prefer an Airband-capable radio
        if mode_upper == "AVIATION_PLANNER" and "Airband" not in selected_radio.supportedBands:
            for r in all_radios:
                if "Airband" in r.supportedBands:
                    selected_radio = r
                    radio_id = r.id
                    break

        if initial_recipe and initial_recipe.radio_target.bands:
            active_bands = [b for b in selected_radio.supportedBands if b in initial_recipe.radio_target.bands]
            if not active_bands:
                active_bands = [b for b in selected_radio.supportedBands if b.lower() != "airband"]
        elif mode_upper == "AVIATION_PLANNER":
            active_bands = ["Airband"] if "Airband" in selected_radio.supportedBands else list(selected_radio.supportedBands)
        else:
            active_bands = [b for b in selected_radio.supportedBands if b.lower() != "airband"]

        raw_naming = (
            getattr(initial_recipe.radio_target, "naming_format", None)
            if initial_recipe
            else None
        )
        if mode_upper == "AVIATION_PLANNER":
            valid_air_codes = {c for c, _, _ in AVIATION_NAMING_FORMAT_OPTIONS}
            active_naming = raw_naming if raw_naming in valid_air_codes else "IDENT_TYPE"
        else:
            active_naming = raw_naming or getattr(prefs, "channelNamingFormat", "CITY_FREQ")

        active_access = (
            initial_recipe.radio_target.repeater_access
            if (initial_recipe and initial_recipe.radio_target.repeater_access)
            else getattr(prefs, "repeaterAccess", ["OPEN"])
        )

        waypoints = (
            list(initial_recipe.corridor.waypoints)
            if (initial_recipe and initial_recipe.corridor and initial_recipe.corridor.waypoints)
            else ["Tyler, TX", "Shreveport, LA", "Jackson, MS"]
        )
        corridor_width = (
            initial_recipe.corridor.corridor_width_miles
            if (initial_recipe and initial_recipe.corridor)
            else 25.0
        )
        if mode_upper == "PROXIMITY_SEARCH":
            center_location = (
                initial_recipe.proximity.center_location
                if (initial_recipe and initial_recipe.proximity)
                else "Dallas, TX"
            )
            radius_miles = (
                initial_recipe.proximity.radius_miles
                if (initial_recipe and initial_recipe.proximity)
                else 50.0
            )
        else:
            center_location = (
                initial_recipe.aviation.center_location
                if (initial_recipe and initial_recipe.aviation)
                else "Tyler, TX"
            )
            radius_miles = (
                initial_recipe.aviation.radius_miles
                if (initial_recipe and initial_recipe.aviation)
                else 35.0
            )

        include_simplex = initial_recipe.radio_target.include_simplex if initial_recipe else True

        if initial_recipe and initial_recipe.sequence_order:
            seq_keys = list(initial_recipe.sequence_order)
        elif mode_upper == "AVIATION_PLANNER":
            seq_keys = ["AVIATION_BLOCK", "TEMPLATE:noaa_wx_channels"]
        elif mode_upper == "PROXIMITY_SEARCH":
            seq_keys = ["TEMPLATE:calling_channels", "PROXIMITY_PLAN", "TEMPLATE:noaa_wx_channels"]
        else:
            seq_keys = ["TEMPLATE:calling_channels", "ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"]

        ctx = _base_context(request, active_nav=mode_upper)
        ctx.update(
            {
                "mode": mode_upper,
                "initial_recipe": initial_recipe,
                "loaded_recipe_file": loaded_recipe_file,
                "waypoints": waypoints,
                "corridor_width": corridor_width,
                "center_location": center_location,
                "radius_miles": radius_miles,
                "include_simplex": include_simplex,
                "sequence_blocks": _build_sequence_blocks(seq_keys, mode=mode_upper),
                "available_templates": workspace.template_mgr.list_templates(),
                "radios_by_brand": dict(sorted(radios_by_brand.items())),
                "selected_radio": selected_radio,
                "active_bands": active_bands,
                "active_naming": active_naming,
                "active_access": active_access,
                "naming_previews": _build_naming_previews(selected_radio, mode=mode_upper),
                "has_active_plan": False,
                "auto_submit": False,
            }
        )
        return templates.TemplateResponse(request, "planner.html", ctx)

    @app.get("/htmx/radio-options", response_class=HTMLResponse)
    async def htmx_radio_options(
        request: Request,
        radio_id: str,
        naming_format: str = "CITY_FREQ",
        mode: str = "ROUTE_CORRIDOR",
    ) -> HTMLResponse:
        spec = workspace.radio_mgr.get_radio(radio_id)
        mode_upper = mode.upper()
        if mode_upper == "AVIATION_PLANNER":
            active_bands = ["Airband"] if "Airband" in spec.supportedBands else list(spec.supportedBands)
            valid_air_codes = {c for c, _, _ in AVIATION_NAMING_FORMAT_OPTIONS}
            active_naming = naming_format if naming_format in valid_air_codes else "IDENT_TYPE"
        else:
            active_bands = [b for b in spec.supportedBands if b.lower() != "airband"] or list(spec.supportedBands)
            active_naming = naming_format

        ctx = {
            "request": request,
            "selected_radio": spec,
            "active_bands": active_bands,
            "active_naming": active_naming,
            "naming_previews": _build_naming_previews(spec, mode=mode_upper),
        }
        return templates.TemplateResponse(request, "partials/radio_options.html", ctx)

    @app.get("/api/geolocate", response_class=JSONResponse)
    async def api_geolocate(lat: float | None = None, lon: float | None = None) -> JSONResponse:
        """Resolve browser GPS coordinates (if provided) or detect current location via IP geolocation."""
        try:
            if lat is not None and lon is not None:
                loc_str = workspace.geocoder.reverse_geocode(lat, lon)
                return JSONResponse({"ok": True, "location": loc_str, "lat": lat, "lon": lon})
            detected = workspace.geocoder.detect_ip_location()
            return JSONResponse({"ok": True, **detected})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=200)

    @app.post("/htmx/plan/generate", response_class=HTMLResponse)
    async def htmx_generate_plan(request: Request) -> HTMLResponse:
        try:
            return await _execute_htmx_generate_plan(request)
        except Exception as exc:
            err_html = f"""
            <div class="p-5 rounded-xl bg-rose-950/80 border border-rose-500/60 text-rose-200 space-y-2 text-xs">
              <div class="font-bold text-sm text-rose-300">✖ Failed to Assemble Codeplug Plan</div>
              <p class="font-mono bg-slate-950/80 p-3 rounded border border-rose-500/30">{exc}</p>
              <p class="text-slate-300">Verify your location/waypoint inputs and try again.</p>
            </div>
            """
            return HTMLResponse(
                content=err_html,
                status_code=200,
                headers={"HX-Trigger": json.dumps({"showNotification": {"message": str(exc), "level": "error"}})},
            )

    async def _execute_htmx_generate_plan(request: Request) -> HTMLResponse:
        form = await request.form()
        mode = str(form.get("mode", "ROUTE_CORRIDOR")).upper()
        include_simplex = form.get("include_simplex") == "true"
        repeater_access = [str(a) for a in form.getlist("repeater_access")] or ["OPEN"]
        sequence_order = [str(s) for s in form.getlist("sequence_order")]

        # Determine initial target radio for Codeplug View (Planner itself is radio-agnostic)
        submitted_radio_id = form.get("radio_id")
        if submitted_radio_id and workspace.radio_mgr.has_radio(str(submitted_radio_id)):
            radio_id = str(submitted_radio_id)
        elif workspace.session.radio_spec and workspace.radio_mgr.has_radio(workspace.session.radio_spec.id):
            radio_id = workspace.session.radio_spec.id
        else:
            all_radios = workspace.radio_mgr.list_radios()
            default_pref = workspace.prefs_mgr.preferences.defaultRadioId
            radio_id = default_pref if (default_pref and workspace.radio_mgr.has_radio(default_pref)) else all_radios[0].id
            if mode == "AVIATION_PLANNER" and "Airband" not in workspace.radio_mgr.get_radio(radio_id).supportedBands:
                for r in all_radios:
                    if "Airband" in r.supportedBands:
                        radio_id = r.id
                        break

        radio_spec = workspace.radio_mgr.get_radio(radio_id)
        submitted_bands = [str(b) for b in form.getlist("bands") if str(b)]
        bands = submitted_bands or _default_bands_for_radio(radio_spec, mode, sequence_order)

        submitted_naming = str(form.get("naming_format") or "").strip().upper()
        naming_format = submitted_naming or _smart_default_naming(radio_spec, mode)
        workspace.session.deleted_keys = set()

        max_age_days = getattr(workspace.prefs_mgr.preferences, "repeaterMaxAgeDays", 30)
        plan_description = str(form.get("plan_description") or "").strip()
        notices: list[dict[str, str]] = []
        map_data: dict[str, Any] = {"center": [32.35, -95.30], "zoom": 6, "channels": []}
        summary: dict[str, Any] = {"title": "Plan Summary", "subtitle": "", "metric_badge": "", "rows": [], "band_counts": {}, "states": []}

        if mode == "ROUTE_CORRIDOR":
            waypoints = [str(w).strip() for w in form.getlist("waypoints") if str(w).strip()]
            if len(waypoints) < 2:
                waypoints = ["Tyler, TX", "Shreveport, LA"]
            corridor_width = float(form.get("corridor_width") or 25.0)
            if not sequence_order:
                sequence_order = ["TEMPLATE:calling_channels", "ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"]
            if "GMRS" in radio_spec.supportedBands and "2m" not in radio_spec.supportedBands:
                if "TEMPLATE:gmrs_channels" not in sequence_order:
                    sequence_order = ["TEMPLATE:gmrs_channels"] + list(sequence_order)

            geo_points = []
            for wp in waypoints:
                try:
                    geo_points.append(workspace.geocoder.resolve(wp))
                except Exception:
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
            custom_name = str(form.get("plan_name") or "").strip()
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
            map_data["waypoints"] = [{"name": pt.name or f"Stop {i+1}", "lat": pt.lat, "lon": pt.lon} for i, pt in enumerate(res.waypoints)]
            summary["title"] = "Route Waypoints & Distance"
            summary["subtitle"] = f"{len(res.waypoints)} stops • {res.total_distance_miles:.1f} miles"
            summary["metric_badge"] = f"{res.total_distance_miles:.1f} mi"
            summary["rows"] = [
                {"label": pt.name or f"Stop {i+1}", "value": f"{dist:.1f} mi"}
                for i, (pt, dist) in enumerate(zip(res.waypoints, res.cumulative_mileages))
            ]
            summary["states"] = route_states

        elif mode == "PROXIMITY_SEARCH":
            center_loc = str(form.get("center_location") or "Dallas, TX").strip()
            radius_miles = float(form.get("radius_miles") or 50.0)
            if not sequence_order:
                sequence_order = ["TEMPLATE:calling_channels", "PROXIMITY_PLAN", "TEMPLATE:noaa_wx_channels"]
            if "GMRS" in radio_spec.supportedBands and "2m" not in radio_spec.supportedBands:
                if "TEMPLATE:gmrs_channels" not in sequence_order:
                    sequence_order = ["TEMPLATE:gmrs_channels"] + list(sequence_order)

            try:
                center_pt = workspace.geocoder.resolve(center_loc)
            except Exception:
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
            plan_name = f"{city_clean}_Proximity_{int(radius_miles)}mi"
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
            center_loc = str(form.get("center_location") or "Tyler, TX").strip()
            radius_miles = float(form.get("radius_miles") or 35.0)
            if not sequence_order:
                sequence_order = ["AVIATION_BLOCK"]

            if "Airband" not in radio_spec.supportedBands:
                notices.append(
                    {
                        "level": "warning",
                        "message": (
                            f"{radio_spec.brand} {radio_spec.model} does not list 'Airband' (108–137 MHz AM) in its supported hardware bands. "
                            "Airband channels are shown below for preview, or you can switch to an Airband-capable radio (e.g. Alinco DR-735T, Baofeng 5RM, Wouxun KG-UV980P)."
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
                        "message": f"No airfields found within {radius_miles:.0f} miles of '{center_loc}'. Try increasing the search radius or using 'Tyler, TX', 'Dallas, TX', or 'Shreveport, LA'.",
                    }
                )

            city_clean = center_loc.split(",")[0].strip()
            plan_name = f"{city_clean}_Aviation_{int(radius_miles)}mi"
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

        # For Aviation mode, ensure radio_spec allows Airband/AM during assembly so preview isn't empty
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

        # Keep a copy of assembled channels before radio-specific condensation so live re-naming is lossless
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
                        f"{radio_spec.maxChannels}-channel memory limit. Delete unwanted channels or export will clamp to {radio_spec.maxChannels} channels."
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

        ctx = {
            "request": request,
            "recipe": recipe,
            "codeplug": codeplug,
            "radio_spec": radio_spec,
            "all_radios": workspace.radio_mgr.list_radios(),
            "summary": summary,
            "band_colors": BAND_COLORS,
            "notices": notices,
            "map_data_json": json.dumps(map_data),
            "default_export_filename": _default_export_filename(recipe, radio_spec),
            "flash_message": None,
            "is_standalone_view": False,
        }
        return templates.TemplateResponse(request, "partials/plan_results.html", ctx)

    @app.get("/codeplug", response_class=HTMLResponse)
    async def codeplug_standalone_page(request: Request) -> HTMLResponse:
        """Render the dedicated full-page Codeplug View and Channel Editor."""
        ctx = _base_context(request, active_nav="codeplug")
        recipe = workspace.session.recipe
        codeplug = workspace.session.codeplug
        spec = workspace.session.radio_spec
        ctx.update(
            {
                "recipe": recipe,
                "codeplug": codeplug,
                "radio_spec": spec,
                "default_export_filename": _default_export_filename(recipe, spec) if (recipe and spec) else "codeplug.csv",
                "flash_message": None,
                "is_standalone_view": True,
            }
        )
        return templates.TemplateResponse(request, "codeplug_view.html", ctx)

    @app.get("/htmx/codeplug/table", response_class=HTMLResponse)
    async def htmx_codeplug_table(request: Request) -> HTMLResponse:
        """Return the current channel_table.html partial to sync the main window after popup edits."""
        recipe = workspace.session.recipe
        codeplug = workspace.session.codeplug
        spec = workspace.session.radio_spec
        if not codeplug or not recipe or not spec:
            return HTMLResponse("")
        ctx = {
            "request": request,
            "recipe": recipe,
            "codeplug": codeplug,
            "radio_spec": spec,
            "all_radios": workspace.radio_mgr.list_radios(),
            "default_export_filename": _default_export_filename(recipe, spec),
            "flash_message": None,
            "is_standalone_view": False,
        }
        return templates.TemplateResponse(request, "partials/channel_table.html", ctx)

    @app.post("/htmx/codeplug/delete-channels", response_class=HTMLResponse)
    async def htmx_delete_channels(
        request: Request,
        selected_slots: list[int] = Form(default=[]),
        is_standalone: str = Form("false"),
    ) -> HTMLResponse:
        """Delete one or more selected channels by slot number and renumber remaining channels."""
        is_standalone_flag = is_standalone.lower() == "true"
        selected_set = set(selected_slots)

        codeplug = workspace.session.codeplug
        recipe = workspace.session.recipe
        spec = workspace.session.radio_spec
        if not codeplug or not recipe or not spec:
            return HTMLResponse("<div class='text-xs text-rose-400'>No active codeplug session.</div>")

        deleted_channels = [ch for ch in codeplug.channels if ch.number in selected_set]
        remaining_channels = [ch for ch in codeplug.channels if ch.number not in selected_set]
        deleted_count = len(codeplug.channels) - len(remaining_channels)

        if workspace.session.raw_channels and len(workspace.session.raw_channels) == len(codeplug.channels):
            workspace.session.raw_channels = [
                raw_ch
                for raw_ch, cur_ch in zip(workspace.session.raw_channels, codeplug.channels)
                if cur_ch.number not in selected_set
            ]

        # Also record deleted channel keys so subsequent naming/radio updates keep deletions across all blocks
        if deleted_channels:
            del_keys = {(round(ch.rxFreq, 4), ch.callsign or "", ch.city or "") for ch in deleted_channels}
            workspace.session.deleted_keys.update(del_keys)
            if workspace.session.primary_channels:
                workspace.session.primary_channels = [
                    ch
                    for ch in workspace.session.primary_channels
                    if (round(ch.rxFreq, 4), ch.callsign or "", ch.city or "") not in del_keys
                ]

        updated_codeplug = Codeplug(name=codeplug.name, channels=remaining_channels).renumbered(
            start_slot=spec.startChannel
        )
        workspace.session.codeplug = updated_codeplug

        band_counts, map_channels = _compute_band_counts_and_map_channels(
            updated_codeplug, recipe.radio_target.bands
        )
        if workspace.session.summary_data is not None:
            workspace.session.summary_data["band_counts"] = band_counts
        if workspace.session.map_data is not None:
            workspace.session.map_data["channels"] = map_channels

        ctx = {
            "request": request,
            "recipe": recipe,
            "codeplug": updated_codeplug,
            "radio_spec": spec,
            "all_radios": workspace.radio_mgr.list_radios(),
            "band_counts": band_counts,
            "band_colors": BAND_COLORS,
            "map_channels_json": json.dumps(map_channels),
            "oob_update_summary": not is_standalone_flag,
            "default_export_filename": _default_export_filename(recipe, spec),
            "flash_message": f"Deleted {deleted_count} channel(s). Renumbered {updated_codeplug.total_channels} remaining channel(s) starting at slot {spec.startChannel}.",
            "is_standalone_view": is_standalone_flag,
        }
        return templates.TemplateResponse(request, "partials/channel_table.html", ctx)

    @app.post("/htmx/codeplug/update", response_class=HTMLResponse)
    async def htmx_update_codeplug(
        request: Request,
        radio_id: str = Form(...),
        naming_format: str = Form(""),
        bands: list[str] = Form(default=[]),
        include_gmrs_std: str = Form("false"),
        radio_changed: str = Form("false"),
        is_standalone: str = Form("false"),
    ) -> HTMLResponse:
        """Instantly re-target radio, toggle bands, and/or update channel naming format from the master channel pool."""
        recipe = workspace.session.recipe
        codeplug = workspace.session.codeplug
        if not recipe or not codeplug:
            return HTMLResponse("<div class='text-xs text-rose-400'>No active codeplug session.</div>")

        spec = workspace.radio_mgr.get_radio(radio_id)
        is_radio_switch = radio_changed.lower() == "true" or (
            workspace.session.radio_spec is not None and workspace.session.radio_spec.id != spec.id and not bands
        )
        is_gmrs_only_radio = "GMRS" in spec.supportedBands and "2m" not in spec.supportedBands

        if is_radio_switch:
            active_naming = _smart_default_naming(spec, recipe.mode) if not naming_format or radio_changed.lower() == "true" else naming_format
            active_bands = _default_bands_for_radio(spec, recipe.mode, recipe.sequence_order)
            if is_gmrs_only_radio and "TEMPLATE:gmrs_channels" not in recipe.sequence_order:
                recipe.sequence_order = ["TEMPLATE:gmrs_channels"] + list(recipe.sequence_order)
        else:
            active_naming = naming_format or recipe.radio_target.naming_format or _smart_default_naming(spec, recipe.mode)
            active_bands = [b for b in bands if b in spec.supportedBands] if bands else [
                b for b in recipe.radio_target.bands if b in spec.supportedBands
            ]
            if not active_bands:
                active_bands = _default_bands_for_radio(spec, recipe.mode, recipe.sequence_order)
            if "GMRS" in spec.supportedBands:
                if include_gmrs_std.lower() == "true":
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
        recipe.radio_target.modes = list(set(spec.supportedModes) | ({"AM"} if recipe.mode == "AVIATION_PLANNER" else set()))

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

        # Re-assemble from master primary_channels (which preserves manual deletions and brings back newly supported bands!)
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

        workspace.session.codeplug = updated_codeplug
        workspace.session.raw_channels = list(raw_assembled.channels)
        workspace.session.radio_spec = spec

        band_counts, map_channels = _compute_band_counts_and_map_channels(updated_codeplug, active_bands)
        if workspace.session.summary_data is not None:
            workspace.session.summary_data["band_counts"] = band_counts
        if workspace.session.map_data is not None:
            workspace.session.map_data["channels"] = map_channels

        ctx = {
            "request": request,
            "recipe": recipe,
            "codeplug": updated_codeplug,
            "radio_spec": spec,
            "all_radios": workspace.radio_mgr.list_radios(),
            "band_counts": band_counts,
            "band_colors": BAND_COLORS,
            "map_channels_json": json.dumps(map_channels),
            "oob_update_summary": not (is_standalone.lower() == "true"),
            "default_export_filename": _default_export_filename(recipe, spec),
            "flash_message": (
                f"Targeted {spec.brand} {spec.model} • Bands: {', '.join(active_bands)} • "
                f"Naming: {active_naming} (Slots {spec.startChannel}..{spec.startChannel + updated_codeplug.total_channels - 1 if updated_codeplug.total_channels else spec.startChannel})"
            ),
            "is_standalone_view": is_standalone.lower() == "true",
        }
        return templates.TemplateResponse(request, "partials/channel_table.html", ctx)

    @app.post("/htmx/codeplug/expand-dmr", response_class=HTMLResponse)
    async def htmx_expand_dmr(request: Request) -> HTMLResponse:
        codeplug = workspace.session.codeplug
        recipe = workspace.session.recipe
        spec = workspace.session.radio_spec
        if not codeplug or not recipe or not spec:
            return HTMLResponse("<div class='text-xs text-rose-400'>No active codeplug session.</div>")

        expanded = []
        dmr_count = 0
        for ch in codeplug.channels:
            if ch.mode.upper() == "DMR":
                dmr_count += 1
                expanded.extend(workspace.radio_id_provider.duplicate_channel_for_talkgroups(ch))
            else:
                expanded.append(ch)

        if dmr_count > 0:
            codeplug = Codeplug(name=codeplug.name, channels=expanded).renumbered(start_slot=spec.startChannel)
            workspace.session.codeplug = codeplug
            msg = f"Expanded {dmr_count} DMR channel(s) across standard Talkgroups ({codeplug.total_channels} total channels)."
        else:
            msg = "No DMR channels present in current codeplug."

        ctx = {
            "request": request,
            "recipe": recipe,
            "codeplug": codeplug,
            "radio_spec": spec,
            "all_radios": workspace.radio_mgr.list_radios(),
            "default_export_filename": _default_export_filename(recipe, spec),
            "flash_message": msg,
        }
        return templates.TemplateResponse(request, "partials/channel_table.html", ctx)

    @app.post("/htmx/recipes/save", response_class=HTMLResponse)
    async def htmx_save_recipe(
        request: Request,
        recipe_name: str = Form("Saved_Plan"),
        recipe_description: str = Form(""),
    ) -> HTMLResponse:
        recipe = workspace.session.recipe
        codeplug = workspace.session.codeplug
        spec = workspace.session.radio_spec
        if not recipe or not codeplug or not spec:
            return HTMLResponse("<div class='text-xs text-rose-400'>No active recipe to save.</div>")

        recipe.name = recipe_name.strip() or recipe.name
        recipe.description = recipe_description.strip()
        recipes_dir = get_recipes_dir()
        recipes_dir.mkdir(parents=True, exist_ok=True)
        dest_yaml = recipes_dir / f"{DataSanitizer.sanitize_filename(recipe.name)}.yaml"
        recipe.to_yaml_file(dest_yaml)

        ctx = {
            "request": request,
            "recipe": recipe,
            "codeplug": codeplug,
            "radio_spec": spec,
            "all_radios": workspace.radio_mgr.list_radios(),
            "default_export_filename": _default_export_filename(recipe, spec),
            "flash_message": f"Saved radio-agnostic configuration recipe '{recipe.name}' to {dest_yaml}",
        }
        return templates.TemplateResponse(request, "partials/channel_table.html", ctx)

    @app.post("/export/csv")
    async def export_csv_download(
        programmer_type: str = Form("CHIRP"),
        filename: str = Form("codeplug.csv"),
    ) -> Response:
        """Export active codeplug to ./exports/ AND return as a browser file download."""
        codeplug = workspace.session.codeplug
        spec = workspace.session.radio_spec
        if not codeplug or not spec:
            return Response("No active codeplug to export.", status_code=400)

        clean_name = Path(filename).name
        if not clean_name.lower().endswith(".csv"):
            clean_name += ".csv"

        out_dir = Path("./exports").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        dest_path = out_dir / clean_name

        export_codeplug(codeplug, spec, dest_path, programmer_type=programmer_type)
        exporter = get_exporter(programmer_type)
        csv_content = exporter.to_csv_string(codeplug, spec)

        return Response(
            content=csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{clean_name}"'},
        )

    # ─── Saved Recipes Manager ─────────────────────────────────────────────────
    @app.get("/recipes", response_class=HTMLResponse)
    async def recipes_page(request: Request, msg: str | None = None) -> HTMLResponse:
        recipes_dir = get_recipes_dir()
        recipes_dir.mkdir(parents=True, exist_ok=True)
        items = []
        for f in sorted(recipes_dir.glob("*.yaml")):
            try:
                rec = RadioPlannerRecipe.from_yaml_file(f)
                items.append({"filename": f.name, "recipe": rec})
            except Exception:
                pass
        ctx = _base_context(request, active_nav="recipes")
        ctx.update({"recipes": items, "recipes_dir": recipes_dir, "flash_message": msg})
        return templates.TemplateResponse(request, "recipes.html", ctx)

    @app.post("/recipes/upload")
    async def upload_recipe(recipe_file: UploadFile) -> RedirectResponse:
        content = (await recipe_file.read()).decode("utf-8")
        recipe = RadioPlannerRecipe.from_yaml_text(content)
        recipes_dir = get_recipes_dir()
        recipes_dir.mkdir(parents=True, exist_ok=True)
        fname = Path(recipe_file.filename or f"{recipe.name}.yaml").name
        dest = recipes_dir / fname
        recipe.to_yaml_file(dest)
        return RedirectResponse(url=f"/?recipe_file={fname}", status_code=303)

    @app.post("/recipes/delete")
    async def delete_recipe(filename: str = Form(...)) -> RedirectResponse:
        target = get_recipes_dir() / Path(filename).name
        if target.is_file():
            target.unlink()
        return RedirectResponse(url="/recipes?msg=Recipe+deleted", status_code=303)

    # ─── Preset Codeplug Templates Manager ─────────────────────────────────────
    @app.get("/templates", response_class=HTMLResponse)
    async def templates_page(
        request: Request,
        msg: str | None = None,
        expanded: str | None = None,
    ) -> HTMLResponse:
        workspace.template_mgr.reload()
        tpl_items = []
        for tpl in workspace.template_mgr.list_templates():
            try:
                chans = workspace.template_mgr.get_template_channels(tpl.id)
            except Exception:
                chans = []
            tpl_items.append(
                {
                    "tpl": tpl,
                    "channels": chans,
                    "is_user": workspace.template_mgr.is_user_template(tpl.id),
                    "is_builtin": tpl.id in {"calling_channels", "noaa_wx_channels", "gmrs_channels"},
                }
            )
        ctx = _base_context(request, active_nav="templates")
        ctx.update(
            {
                "templates": tpl_items,
                "core_templates_dir": workspace.template_mgr.app_dir,
                "user_templates_dir": workspace.template_mgr.user_dir,
                "flash_message": msg,
                "expanded_id": expanded or "",
            }
        )
        return templates.TemplateResponse(request, "templates_mgr.html", ctx)

    @app.post("/templates/save")
    async def save_template_editor(
        tpl_id: str = Form(...),
        name: str = Form(...),
        tag_text: str = Form("PRESET"),
        tag_color_hex: str = Form("#00BCD4"),
        description: str = Form(""),
        channels_json: str = Form(""),
        ch_name: list[str] = Form(default=[]),
        ch_rx_freq: list[str] = Form(default=[]),
        ch_offset_dir: list[str] = Form(default=[]),
        ch_offset: list[str] = Form(default=[]),
        ch_mode: list[str] = Form(default=[]),
        ch_power: list[str] = Form(default=[]),
        ch_tone_mode: list[str] = Form(default=[]),
        ch_tone_val: list[str] = Form(default=[]),
        ch_comment: list[str] = Form(default=[]),
    ) -> RedirectResponse:
        clean_id = DataSanitizer.sanitize_filename(tpl_id.strip().lower()).replace("-", "_")
        if not clean_id:
            clean_id = "custom_template"

        channel_items: list[TemplateChannelItem] = []

        if channels_json.strip():
            try:
                raw_rows = json.loads(channels_json)
            except Exception:
                raw_rows = []
            for idx, r in enumerate(raw_rows, start=1):
                if not isinstance(r, dict):
                    continue
                r_name = str(r.get("name", "")).strip() or f"CH {idx}"
                try:
                    rx = round(float(r.get("rxFreq", 146.520)), 5)
                except (ValueError, TypeError):
                    continue
                off_dir = str(r.get("offsetDir", "off")).strip()
                if off_dir not in ("off", "+", "-"):
                    off_dir = "off"
                try:
                    off_val = round(abs(float(r.get("offset", 0.0) or 0.0)), 5)
                except (ValueError, TypeError):
                    off_val = 0.0
                if off_dir == "+":
                    tx = round(rx + off_val, 5)
                elif off_dir == "-":
                    tx = round(rx - off_val, 5)
                else:
                    off_val = 0.0
                    tx = rx

                mode_val = str(r.get("mode", "FM")).strip().upper() or "FM"
                pwr_raw = str(r.get("power", "High")).strip().capitalize()
                power_val = pwr_raw if pwr_raw in ("High", "Mid", "Low") else "High"
                t_mode = str(r.get("toneMode", "None")).strip()
                if t_mode not in ("None", "Tone", "TSQL", "DCS"):
                    t_mode = "None"
                t_val = str(r.get("toneVal", "None")).strip() or "None"

                ctcss = "None"
                rx_ctcss = "None"
                dcs = "None"
                rx_dcs = "None"
                if t_mode in ("Tone", "TSQL"):
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
                        comment=str(r.get("comment", "")).strip(),
                    )
                )
        else:
            row_count = max(len(ch_name), len(ch_rx_freq))
            for idx in range(row_count):
                r_name = (ch_name[idx] if idx < len(ch_name) else "").strip()
                r_rx_str = (ch_rx_freq[idx] if idx < len(ch_rx_freq) else "").strip()
                if not r_name and not r_rx_str:
                    continue
                try:
                    rx = round(float(r_rx_str), 5)
                except ValueError:
                    continue
                r_name = r_name or f"CH {idx + 1}"
                off_dir = (ch_offset_dir[idx] if idx < len(ch_offset_dir) else "off").strip()
                if off_dir not in ("off", "+", "-"):
                    off_dir = "off"
                off_str = (ch_offset[idx] if idx < len(ch_offset) else "0").strip()
                try:
                    off_val = round(abs(float(off_str or 0.0)), 5)
                except ValueError:
                    off_val = 0.0

                if off_dir == "+":
                    tx = round(rx + off_val, 5)
                elif off_dir == "-":
                    tx = round(rx - off_val, 5)
                else:
                    off_val = 0.0
                    tx = rx

                mode_val = (ch_mode[idx] if idx < len(ch_mode) else "FM").strip().upper() or "FM"
                pwr_raw = (ch_power[idx] if idx < len(ch_power) else "High").strip().capitalize()
                power_val = pwr_raw if pwr_raw in ("High", "Mid", "Low") else "High"
                t_mode = (ch_tone_mode[idx] if idx < len(ch_tone_mode) else "None").strip()
                if t_mode not in ("None", "Tone", "TSQL", "DCS"):
                    t_mode = "None"
                t_val = (ch_tone_val[idx] if idx < len(ch_tone_val) else "None").strip() or "None"

                ctcss = "None"
                rx_ctcss = "None"
                dcs = "None"
                rx_dcs = "None"
                if t_mode in ("Tone", "TSQL"):
                    ctcss = t_val if t_val.lower() != "none" else "88.5"
                    rx_ctcss = ctcss if t_mode == "TSQL" else "None"
                elif t_mode == "DCS":
                    dcs = t_val.lstrip("Dd") if t_val.lower() != "none" else "023"
                    rx_dcs = dcs

                comment_val = (ch_comment[idx] if idx < len(ch_comment) else "").strip()
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
                        comment=comment_val,
                    )
                )

        updated_tpl = PresetTemplateFile(
            id=clean_id,
            name=name.strip() or clean_id,
            description=description.strip(),
            tagText=tag_text.strip().upper() or "PRESET",
            tagColorHex=tag_color_hex.strip() or "#00BCD4",
            channels=channel_items,
        )
        dest = workspace.template_mgr.save_core_template(updated_tpl)
        return RedirectResponse(
            url=f"/templates?msg=Saved+{len(channel_items)}+channels+to+core+template+{dest.name}&expanded={clean_id}",
            status_code=303,
        )

    @app.post("/templates/customize")
    async def customize_template(template_id: str = Form(...)) -> RedirectResponse:
        dest = workspace.template_mgr.copy_to_user_directory(template_id)
        return RedirectResponse(url=f"/templates?msg=Copied+to+{dest.id}", status_code=303)

    @app.post("/templates/delete")
    async def delete_template(template_id: str = Form(...)) -> RedirectResponse:
        workspace.template_mgr.delete_template(template_id)
        return RedirectResponse(url="/templates?msg=Template+deleted", status_code=303)

    @app.post("/templates/import")
    async def import_template(
        tpl_id: str = Form(...),
        name: str = Form(...),
        tag_text: str = Form("CUSTOM"),
        description: str = Form(""),
        template_file: UploadFile = ...,
    ) -> RedirectResponse:
        raw_text = (await template_file.read()).decode("utf-8")
        fname = (template_file.filename or "").lower()
        clean_id = DataSanitizer.sanitize_filename(tpl_id.strip().lower()).replace("-", "_")
        if fname.endswith((".yaml", ".yml")):
            data = parse_yaml_text(raw_text)
            new_tpl = PresetTemplateFile.model_validate(data)
        else:
            new_tpl = PresetTemplateFile(
                id=clean_id or "custom_template",
                name=name.strip(),
                description=description.strip(),
                tagText=tag_text.strip().upper(),
                tagColorHex="#4CAF50",
                rawCsvContent=raw_text,
            )
        workspace.template_mgr.save_core_template(new_tpl)
        return RedirectResponse(
            url=f"/templates?msg=Imported+core+template+{new_tpl.name}&expanded={new_tpl.id}",
            status_code=303,
        )

    # ─── Radios & Hardware Specs Manager ───────────────────────────────────────
    @app.get("/radios", response_class=HTMLResponse)
    async def radios_page(request: Request, msg: str | None = None) -> HTMLResponse:
        items = []
        for r in workspace.radio_mgr.list_radios():
            items.append(
                {
                    "spec": r,
                    "spec_json": json.dumps(r.model_dump()),
                    "is_user": workspace.radio_mgr.is_user_radio(r.id),
                }
            )
        ctx = _base_context(request, active_nav="radios")
        ctx.update({"radios": items, "flash_message": msg})
        return templates.TemplateResponse(request, "radios.html", ctx)

    @app.post("/radios/save")
    async def save_radio(
        brand: str = Form(...),
        model: str = Form(...),
        radio_id: str = Form(...),
        description: str = Form(""),
        start_channel: int = Form(1),
        max_channels: int = Form(128),
        max_name_length: int = Form(8),
        programmer_type: str = Form("RT_SYSTEMS"),
        supported_bands: str = Form("2m, 70cm, WX"),
        supported_modes: str = Form("FM, AM"),
        allow_dots: bool = Form(False),
        allow_spaces: bool = Form(False),
    ) -> RedirectResponse:
        bands = [b.strip() for b in supported_bands.split(",") if b.strip()]
        modes = [m.strip() for m in supported_modes.split(",") if m.strip()]
        existing_cols: list[str] = []
        if workspace.radio_mgr.has_radio(radio_id):
            existing_cols = workspace.radio_mgr.get_radio(radio_id).columns

        spec = TargetRadioSpec(
            id=radio_id.strip(),
            brand=brand.strip(),
            model=model.strip(),
            description=description.strip() or f"{brand} {model}",
            startChannel=start_channel,
            maxChannels=max_channels,
            maxNameLength=max_name_length,
            programmerType=programmer_type.strip().upper(),
            allowDots=allow_dots,
            allowSpaces=allow_spaces,
            supportedBands=bands,
            supportedModes=modes,
            columns=existing_cols,
        )
        workspace.radio_mgr.save_user_radio(spec)
        return RedirectResponse(url=f"/radios?msg=Saved+radio+{spec.brand}+{spec.model}", status_code=303)

    @app.post("/radios/delete")
    async def delete_radio(radio_id: str = Form(...)) -> RedirectResponse:
        workspace.radio_mgr.delete_user_radio(radio_id)
        return RedirectResponse(url="/radios?msg=Custom+radio+deleted", status_code=303)

    # ─── User Preferences & API Keys Manager ───────────────────────────────────
    @app.get("/preferences", response_class=HTMLResponse)
    async def preferences_page(request: Request, msg: str | None = None) -> HTMLResponse:
        ctx = _base_context(request, active_nav="preferences")
        ctx.update(
            {
                "cached_states": workspace.repeater_provider.list_cached_state_files(),
                "flash_message": msg,
            }
        )
        return templates.TemplateResponse(request, "preferences.html", ctx)

    @app.post("/preferences/save")
    async def save_preferences(
        callsign: str = Form("N0CALL"),
        operator_name: str = Form("Radio Operator"),
        primary_dmr_id: str = Form(""),
        default_radio_id: str = Form(""),
        channel_naming_format: str = Form("CITY_FREQ"),
        distance_unit: str = Form("MILES"),
        repeater_max_age_days: int = Form(30),
        web_port: int = Form(8000),
        color_theme: str = Form("DARK"),
        font_family: str = Form("SANS"),
        font_size: str = Form("MEDIUM"),
        repeaterbook_api_key: str = Form(""),
        radioid_username: str = Form(""),
        radioid_api_key: str = Form(""),
    ) -> RedirectResponse:
        new_prefs = workspace.prefs_mgr.preferences.update_settings(
            callsign=callsign.strip(),
            operatorName=operator_name.strip(),
            primaryDmrId=primary_dmr_id.strip() or None,
            defaultRadioId=default_radio_id.strip() or None,
            channelNamingFormat=channel_naming_format.strip(),
            distanceUnit=distance_unit.strip(),
            repeaterMaxAgeDays=max(1, repeater_max_age_days),
            webPort=max(1, min(65535, web_port)),
            colorTheme=color_theme.strip().upper(),
            fontFamily=font_family.strip().upper(),
            fontSize=font_size.strip().upper(),
        )
        workspace.prefs_mgr.save_preferences(new_prefs)

        rb_key = repeaterbook_api_key.strip() or None
        new_tokens = workspace.prefs_mgr.tokens.model_copy(
            update={
                "repeaterBookApiKey": rb_key,
                "radioIdUsername": radioid_username.strip().upper() or None,
                "radioIdApiKey": radioid_api_key.strip() or None,
            }
        )
        workspace.prefs_mgr.save_tokens(new_tokens)
        workspace.repeater_provider.api_key = rb_key
        workspace.repeater_provider.last_status = "CONFIGURED" if rb_key else "NO_KEY"

        return RedirectResponse(url="/preferences?msg=Preferences+and+API+tokens+saved", status_code=303)

    return app


app = create_app()
