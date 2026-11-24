(() => {
  "use strict";

  const UI_FONTS = {
    system: '"Segoe UI", "Ubuntu", "Cantarell", "Noto Sans", system-ui, -apple-system, BlinkMacSystemFont, "Liberation Sans", sans-serif',
    humanist: '"Calibri", "Ubuntu", "Cantarell", "Trebuchet MS", "Liberation Sans", "DejaVu Sans", sans-serif',
    geometric: '"Verdana", "DejaVu Sans", "Liberation Sans", "Tahoma", "Segoe UI", sans-serif',
    serif: '"Georgia", "Liberation Serif", "DejaVu Serif", "Cambria", "Times New Roman", serif',
    mono: '"Cascadia Mono", "JetBrains Mono", "Ubuntu Mono", "Liberation Mono", "DejaVu Sans Mono", "Consolas", monospace',
  };

  const MONO_FONTS = {
    cascadia: '"Cascadia Mono", "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", "Consolas", monospace',
    consolas: '"Consolas", "Liberation Mono", "DejaVu Sans Mono", "Lucida Console", monospace',
    courier: '"Courier New", "Liberation Mono", "DejaVu Sans Mono", Courier, monospace',
  };

  const DEFAULT_PANEL_LAYOUT = {
    builder: { visible: true, position: "left" },
    map: { visible: true, position: "right" },
    summary: { visible: true, position: "right" },
    templates: { visible: false, position: "right" },
    radios: { visible: false, position: "right" },
    vfo: { visible: true },
    footer: { visible: true },
  };

  const LAYOUT_PRESETS = {
    studio: {
      builder: { visible: true, position: "left" },
      map: { visible: true, position: "right" },
      summary: { visible: true, position: "right" },
      templates: { visible: false, position: "right" },
      radios: { visible: false, position: "right" },
      vfo: { visible: true },
      footer: { visible: true },
    },
    mapFocus: {
      builder: { visible: false, position: "left" },
      map: { visible: true, position: "top" },
      summary: { visible: true, position: "right" },
      templates: { visible: false, position: "right" },
      radios: { visible: false, position: "right" },
      vfo: { visible: true },
      footer: { visible: true },
    },
    managers: {
      builder: { visible: false, position: "left" },
      map: { visible: false, position: "right" },
      summary: { visible: false, position: "right" },
      templates: { visible: true, position: "left" },
      radios: { visible: true, position: "right" },
      vfo: { visible: true },
      footer: { visible: true },
    },
    codeplug: {
      builder: { visible: false, position: "left" },
      map: { visible: false, position: "right" },
      summary: { visible: false, position: "right" },
      templates: { visible: false, position: "right" },
      radios: { visible: false, position: "right" },
      vfo: { visible: true },
      footer: { visible: true },
    },
  };

  const DOCKABLE_PANELS = {
    builder: "panelBuilder",
    map: "panelMap",
    summary: "panelSummary",
    templates: "panelTemplates",
    radios: "panelRadios",
  };

  const DOCK_ZONES = {
    left: "dockLeft",
    right: "dockRight",
    top: "dockTop",
    bottom: "dockBottom",
  };

  const DOCK_RESIZERS = {
    left: "resizerLeft",
    right: "resizerRight",
    top: "resizerTop",
    bottom: "resizerBottom",
  };

  const VALID_DOCK_POSITIONS = ["left", "right", "top", "bottom"];

  const BAND_PALETTE = {
    "10m": "#f97316",
    "6m": "#ec4899",
    "2m": "#10b981",
    "1.25m": "#14b8a6",
    "70cm": "#a855f7",
    GMRS: "#eab308",
    Airband: "#6366f1",
    WX: "#38bdf8",
    Other: "#94a3b8",
  };

  const PRIMARY_SEQ_META = {
    ROUTE_CORRIDOR: { key: "ROUTE_PLAN", title: "Highway Route Corridor Repeaters", badge: "PRIMARY" },
    PROXIMITY_SEARCH: { key: "PROXIMITY_PLAN", title: "Radial Proximity Ring Repeaters", badge: "PRIMARY" },
    AVIATION_PLANNER: { key: "AVIATION_BLOCK", title: "Local Airport Aviation Channels", badge: "PRIMARY" },
  };

  const $ = (id) => document.getElementById(id);

  function sanitizePanelLayout(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const out = {};
    for (const key of Object.keys(DEFAULT_PANEL_LAYOUT)) {
      const def = DEFAULT_PANEL_LAYOUT[key];
      const item = src[key] && typeof src[key] === "object" ? src[key] : {};
      const entry = { visible: typeof item.visible === "boolean" ? item.visible : def.visible };
      if ("position" in def) {
        const pos = String(item.position || def.position).toLowerCase();
        entry.position = VALID_DOCK_POSITIONS.includes(pos) ? pos : def.position;
      }
      out[key] = entry;
    }
    return out;
  }

  const state = {
    prefs: {
      callsign: "N0CALL",
      operatorName: "Radio Operator",
      primaryDmrId: "",
      distanceUnit: "MILES",
      defaultRadioId: "",
      channelNamingFormat: "CITY_FREQ",
      repeaterAccess: ["OPEN"],
      repeaterMaxAgeDays: 30,
      webPort: 8000,
      theme: "shack-dark",
      ui_font: "system",
      mono_font: "cascadia",
      font_size: 14,
      lcd_font_size: 15,
      panel_layout: sanitizePanelLayout(DEFAULT_PANEL_LAYOUT),
      repeaterBookApiKeySet: false,
      radioIdUsername: "",
      radioIdApiKeySet: false,
      qrzUsername: "",
      qrzConfigured: false,
      has_api_key: false,
    },
    appVersion: "0.2.0",
    installMode: "source",
    updateInfo: null,
    nwsBriefingText: "",
    draftTheme: "shack-dark",
    radios: [],
    templates: [],
    recipes: [],
    cachedStates: [],
    activePlan: null,
    activeReport: null,
    builderMode: "ROUTE_CORRIDOR",
    waypoints: ["Tyler, TX", "Shreveport, LA", "Jackson, MS"],
    sequenceOrder: ["TEMPLATE:calling_channels", "ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"],
    loadedRecipeFile: null,
    channelFilter: "ALL",
    bandFilter: "ALL",
    searchQuery: "",
    selectedSlot: null,
    checkedSlots: new Set(),
    lastCheckedSlot: null,
    leafletMap: null,
    leafletOverlayGroup: null,
    leafletChannelGroup: null,
    markerBySlot: new Map(),
    draggedEl: null,
    editingTemplateId: null,
  };

  // -------------------------------------------------------------------------
  // Helpers: API, Escaping, Toasts, Clocks
  // -------------------------------------------------------------------------
  async function api(path, options = {}) {
    const opts = {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    };
    const resp = await fetch(path, opts);
    if (resp.status === 204) return null;
    const contentType = resp.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const body = isJson ? await resp.json() : await resp.text();
    if (!resp.ok) {
      const msg =
        body && body.detail
          ? typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail)
          : `HTTP ${resp.status}`;
      throw new Error(msg);
    }
    return body;
  }

  function escHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toast(message, type = "info") {
    const stack = $("toastStack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity 0.25s";
      setTimeout(() => el.remove(), 260);
    }, 3000);
  }

  function updateClocks() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    $("clockUtc").textContent = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}Z`;
    const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
    $("clockDate").textContent = `${pad(now.getUTCDate())} ${months[now.getUTCMonth()]}`;
    $("clockLocal").textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  }

  async function downloadTextFile(filename, content, mime = "text/plain;charset=utf-8") {
    const ext = (filename.split(".").pop() || "txt").toLowerCase();
    if (window.desktopApi && typeof window.desktopApi.saveTextFile === "function") {
      try {
        const res = await window.desktopApi.saveTextFile(filename, content);
        if (res && res.saved) return true;
        if (res && res.cancelled) return false;
      } catch {
        // fallback below
      }
    }
    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.save_text_file === "function") {
      try {
        const res = await window.pywebview.api.save_text_file(filename, content, ext);
        if (res && res.saved) return true;
        if (res && res.cancelled) return false;
      } catch {
        // fallback to browser download below
      }
    }
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return true;
  }

  // -------------------------------------------------------------------------
  // Theme, Fonts & 5-Zone Dockable Panel Engine (1:1 with w5cdn-net-logger)
  // -------------------------------------------------------------------------
  function invalidateMapSoon() {
    if (state.leafletMap) {
      setTimeout(() => state.leafletMap && state.leafletMap.invalidateSize(), 100);
    }
  }

  function syncPanelsModalControls(layout) {
    const clean = sanitizePanelLayout(layout);
    document.querySelectorAll("[data-panel-vis]").forEach((chk) => {
      const key = chk.dataset.panelVis;
      if (clean[key]) chk.checked = Boolean(clean[key].visible);
    });
    document.querySelectorAll("[data-set-panel-pos]").forEach((btn) => {
      const [key, pos] = (btn.dataset.setPanelPos || "").split(":");
      if (clean[key]) btn.classList.toggle("active", clean[key].position === pos);
    });
  }

  function applyPanelLayout(layout) {
    const clean = sanitizePanelLayout(layout);

    for (const [key, panelDomId] of Object.entries(DOCKABLE_PANELS)) {
      const panelEl = $(panelDomId);
      const cfg = clean[key];
      if (!panelEl || !cfg) continue;
      const zoneEl = $(DOCK_ZONES[cfg.position] || "dockRight");
      if (zoneEl && panelEl.parentElement !== zoneEl) {
        zoneEl.appendChild(panelEl);
      }
      panelEl.classList.toggle("hidden", !cfg.visible);
    }

    for (const [zoneKey, zoneDomId] of Object.entries(DOCK_ZONES)) {
      const zoneEl = $(zoneDomId);
      if (!zoneEl) continue;
      const hasVisible = Boolean(zoneEl.querySelector(".dock-panel:not(.hidden)"));
      zoneEl.classList.toggle("hidden", !hasVisible);
      const resizerEl = $(DOCK_RESIZERS[zoneKey]);
      if (resizerEl) resizerEl.classList.toggle("hidden", !hasVisible);
    }

    document.querySelectorAll("[data-panel-dock]").forEach((btn) => {
      const [key, pos] = (btn.dataset.panelDock || "").split(":");
      if (clean[key]) btn.classList.toggle("active", clean[key].position === pos);
    });

    $("btnToggleBuilder")?.classList.toggle("active", Boolean(clean.builder.visible));
    $("btnToggleMap")?.classList.toggle("active", Boolean(clean.map.visible));
    $("btnToggleSummary")?.classList.toggle("active", Boolean(clean.summary.visible));
    $("btnToggleTemplates")?.classList.toggle("active", Boolean(clean.templates.visible));
    $("btnToggleRadios")?.classList.toggle("active", Boolean(clean.radios.visible));

    $("shortcutFooter")?.classList.toggle("hidden", !clean.footer.visible);
    const vfoEl = $("vfoCluster");
    if (vfoEl) {
      const showVfo = Boolean(clean.vfo.visible) && Boolean(state.activePlan && state.activePlan.active);
      vfoEl.classList.toggle("hidden", !showVfo);
    }

    syncPanelsModalControls(clean);
    if (clean.map.visible) invalidateMapSoon();
  }

  async function savePanelLayout(nextLayout, quiet = true) {
    const clean = sanitizePanelLayout(nextLayout);
    state.prefs.panel_layout = clean;
    applyPanelLayout(clean);

    try {
      const cached = JSON.parse(localStorage.getItem("rp_visual_prefs") || "{}") || {};
      cached.panel_layout = clean;
      localStorage.setItem("rp_visual_prefs", JSON.stringify(cached));
    } catch {
      // ignore storage errors
    }

    try {
      const resp = await api("/api/preferences", {
        method: "PUT",
        body: JSON.stringify({ panelLayout: clean }),
      });
      if (resp && resp.preferences) {
        state.prefs = { ...state.prefs, ...resp.preferences };
      }
      if (!quiet) toast("Panel layout saved", "success");
    } catch (err) {
      toast(`Layout save error: ${err.message}`, "error");
    }
  }

  function togglePanel(panelKey, forceVisible = null) {
    const next = sanitizePanelLayout(state.prefs.panel_layout);
    if (!next[panelKey]) return;
    const willShow = forceVisible === null ? !next[panelKey].visible : Boolean(forceVisible);
    next[panelKey] = { ...next[panelKey], visible: willShow };
    savePanelLayout(next, true);
  }

  function movePanel(panelKey, position, ensureVisible = false) {
    if (!VALID_DOCK_POSITIONS.includes(position)) return;
    const next = sanitizePanelLayout(state.prefs.panel_layout);
    if (!next[panelKey] || !("position" in next[panelKey])) return;
    next[panelKey] = {
      ...next[panelKey],
      position,
      ...(ensureVisible ? { visible: true } : {}),
    };
    savePanelLayout(next, true);
  }

  function applyLayoutPreset(presetName) {
    const preset = LAYOUT_PRESETS[presetName];
    if (!preset) return;
    savePanelLayout(preset, false);
  }

  function applyVisualPrefs(p) {
    const root = document.documentElement;
    root.setAttribute("data-theme", p.theme || "shack-dark");
    root.style.setProperty("--font-sans", UI_FONTS[p.ui_font] || UI_FONTS.system);
    root.style.setProperty("--font-mono", MONO_FONTS[p.mono_font] || MONO_FONTS.cascadia);
    root.style.setProperty("--font-size", `${Number(p.font_size) || 14}px`);
    root.style.setProperty("--callsign-size", `${Number(p.lcd_font_size) || 15}px`);
    if (p.panel_layout) applyPanelLayout(p.panel_layout);
  }

  function applySavedPrefs(prefs) {
    const nextLayout = sanitizePanelLayout(prefs.panel_layout || state.prefs.panel_layout);
    state.prefs = { ...state.prefs, ...prefs, panel_layout: nextLayout };
    applyVisualPrefs(state.prefs);

    try {
      localStorage.setItem(
        "rp_visual_prefs",
        JSON.stringify({
          theme: state.prefs.theme,
          ui_font: state.prefs.ui_font,
          mono_font: state.prefs.mono_font,
          font_size: state.prefs.font_size,
          lcd_font_size: state.prefs.lcd_font_size,
          panel_layout: state.prefs.panel_layout,
        })
      );
    } catch {
      // ignore storage errors
    }

    $("operatorCallBadge").textContent = `OP: ${state.prefs.callsign || "N0CALL"}`;
    const apiPill = $("apiStatusPill");
    if (state.prefs.has_api_key) {
      apiPill.textContent = "REPEATERBOOK LIVE";
      apiPill.classList.add("live");
    } else {
      apiPill.textContent = "OFFLINE CACHE";
      apiPill.classList.remove("live");
    }
  }

  // Flash-free localStorage visual bootstrap
  try {
    const cachedVisual = JSON.parse(localStorage.getItem("rp_visual_prefs") || "null");
    if (cachedVisual) {
      if (cachedVisual.panel_layout) {
        state.prefs.panel_layout = sanitizePanelLayout(cachedVisual.panel_layout);
      }
      applyVisualPrefs(cachedVisual);
    }
  } catch {
    // ignore invalid cache
  }

  // -------------------------------------------------------------------------
  // Plan Builder Panel (Modes, Waypoints, Sequence Blocks, Geolocation)
  // -------------------------------------------------------------------------
  function defaultSequenceForMode(mode) {
    if (mode === "AVIATION_PLANNER") return ["AVIATION_BLOCK", "TEMPLATE:noaa_wx_channels"];
    if (mode === "PROXIMITY_SEARCH") return ["TEMPLATE:calling_channels", "PROXIMITY_PLAN", "TEMPLATE:noaa_wx_channels"];
    return ["TEMPLATE:calling_channels", "ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"];
  }

  function setBuilderMode(mode, keepSequence = false) {
    const upper = String(mode || "ROUTE_CORRIDOR").toUpperCase();
    state.builderMode = ["ROUTE_CORRIDOR", "PROXIMITY_SEARCH", "AVIATION_PLANNER"].includes(upper)
      ? upper
      : "ROUTE_CORRIDOR";

    document.querySelectorAll("[data-builder-mode]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.builderMode === state.builderMode);
    });

    const isCorridor = state.builderMode === "ROUTE_CORRIDOR";
    const isAviation = state.builderMode === "AVIATION_PLANNER";
    $("builderCorridorSection").classList.toggle("hidden", !isCorridor);
    $("builderRadialSection").classList.toggle("hidden", isCorridor);
    $("builderAccessSection").classList.toggle("hidden", isAviation);
    $("radialSimplexWrap").classList.toggle("hidden", isAviation);
    $("lblCenterLocation").textContent = isAviation ? "Target City or Airport" : "Center Location / City";

    if (!keepSequence) {
      const primMeta = PRIMARY_SEQ_META[state.builderMode];
      const hasAnyPrim = state.sequenceOrder.some((k) => ["ROUTE_PLAN", "PROXIMITY_PLAN", "AVIATION_BLOCK"].includes(k));
      if (hasAnyPrim) {
        state.sequenceOrder = state.sequenceOrder.map((k) =>
          ["ROUTE_PLAN", "PROXIMITY_PLAN", "AVIATION_BLOCK"].includes(k) ? primMeta.key : k
        );
      } else {
        state.sequenceOrder = defaultSequenceForMode(state.builderMode);
      }
      if (isAviation && $("inRadiusMiles").value === "50") {
        $("inRadiusMiles").value = "35";
        if ($("inCenterLocation").value === "Dallas, TX") $("inCenterLocation").value = "Tyler, TX";
      } else if (!isAviation && !isCorridor && $("inRadiusMiles").value === "35") {
        $("inRadiusMiles").value = "50";
      }
    }
    renderSequenceList();
  }

  function renderWaypointsList() {
    const list = $("waypointsList");
    list.innerHTML = state.waypoints
      .map(
        (wp, idx) => `
      <div class="drag-row" draggable="true" data-wp-idx="${idx}">
        <span class="drag-handle" title="Drag to reorder">☰</span>
        <input type="text" class="input input-sm" data-wp-input="${idx}" value="${escHtml(wp)}" placeholder="City, ST (e.g. Tyler, TX)" required />
        <button type="button" class="btn btn-ghost btn-xs" data-wp-remove="${idx}" title="Remove stop">✕</button>
      </div>`
      )
      .join("");
  }

  function syncWaypointsFromDom() {
    const inputs = Array.from($("waypointsList").querySelectorAll("[data-wp-input]"));
    state.waypoints = inputs.map((el) => el.value);
  }

  function renderSequenceList() {
    const list = $("sequenceList");
    const primMeta = PRIMARY_SEQ_META[state.builderMode];
    list.innerHTML = state.sequenceOrder
      .map((key, idx) => {
        const isPrimary = ["ROUTE_PLAN", "PROXIMITY_PLAN", "AVIATION_BLOCK"].includes(key);
        let title = key;
        let badge = "TPL";
        if (isPrimary) {
          title = primMeta.title;
          badge = primMeta.badge;
        } else if (key.startsWith("TEMPLATE:")) {
          const tplId = key.slice(9);
          const tpl = state.templates.find((t) => t.id === tplId);
          title = tpl ? tpl.name : `Template (${tplId})`;
          badge = tpl ? tpl.tagText : "TPL";
        }
        return `
        <div class="drag-row" draggable="true" data-seq-key="${escHtml(key)}" data-seq-idx="${idx}">
          <span class="drag-handle" title="Drag to reorder">☰</span>
          <span class="seq-row-label">${escHtml(title)}</span>
          <span class="pill ${isPrimary ? "pill-emerald" : "pill-cyan"} mono">${escHtml(badge)}</span>
          ${isPrimary ? "" : `<button type="button" class="btn btn-ghost btn-xs" data-seq-remove="${idx}" title="Remove block">✕</button>`}
        </div>`;
      })
      .join("");
  }

  function syncSequenceFromDom() {
    const rows = Array.from($("sequenceList").querySelectorAll("[data-seq-key]"));
    state.sequenceOrder = rows.map((el) => el.dataset.seqKey);
  }

  function renderTemplatePicker() {
    const sel = $("addTemplateSelect");
    if (!sel) return;
    sel.innerHTML = state.templates
      .map((t) => `<option value="TEMPLATE:${escHtml(t.id)}">+ ${escHtml(t.name)} [${escHtml(t.tagText)}]</option>`)
      .join("");
  }

  function bindDragSort(containerEl, onOrderChanged) {
    containerEl.addEventListener("dragstart", (e) => {
      const row = e.target.closest(".drag-row");
      if (!row) return;
      state.draggedEl = row;
      row.classList.add("dragging");
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
    });
    containerEl.addEventListener("dragend", () => {
      if (state.draggedEl) {
        state.draggedEl.classList.remove("dragging");
        state.draggedEl = null;
        onOrderChanged();
      }
    });
    containerEl.addEventListener("dragover", (e) => {
      e.preventDefault();
      const target = e.target.closest(".drag-row");
      if (!state.draggedEl || !target || state.draggedEl === target || target.parentElement !== containerEl) return;
      const rect = target.getBoundingClientRect();
      const after = e.clientY - rect.top > rect.height / 2;
      containerEl.insertBefore(state.draggedEl, after ? target.nextSibling : target);
    });
  }

  async function detectCurrentLocation() {
    const btn = $("btnUseCurrentLocation");
    const orig = btn.textContent;
    btn.disabled = true;
    btn.textContent = "⏳ Locating...";
    const resolveViaServer = async (url) => {
      try {
        const res = await api(url);
        if (res && res.ok && res.location) {
          $("inCenterLocation").value = res.location;
          toast(`Detected location: ${res.location}`, "success");
          return true;
        }
      } catch {
        // fallback below
      }
      return false;
    };

    const done = () => {
      btn.disabled = false;
      btn.textContent = orig;
    };

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const ok = await resolveViaServer(`/api/geolocate?lat=${pos.coords.latitude}&lon=${pos.coords.longitude}`);
          if (!ok) await resolveViaServer("/api/geolocate");
          done();
        },
        async () => {
          const ok = await resolveViaServer("/api/geolocate");
          if (!ok) toast("Could not detect current location automatically", "error");
          done();
        },
        { timeout: 4000 }
      );
    } else {
      const ok = await resolveViaServer("/api/geolocate");
      if (!ok) toast("Could not detect current location automatically", "error");
      done();
    }
  }

  async function assemblePlan() {
    syncWaypointsFromDom();
    syncSequenceFromDom();
    const btn = $("btnAssemblePlan");
    const topBtn = $("btnTopAssemble");
    btn.disabled = true;
    topBtn.disabled = true;

    const accessOpts = Array.from(document.querySelectorAll("[data-access-opt]:checked")).map(
      (el) => el.dataset.accessOpt
    );

    const payload = {
      mode: state.builderMode,
      plan_name: $("inPlanName").value.trim(),
      plan_description: $("inPlanDesc").value.trim(),
      waypoints: state.waypoints.map((w) => w.trim()).filter(Boolean),
      corridor_width: Number($("inCorridorWidth").value) || 25,
      center_location: $("inCenterLocation").value.trim() || "Dallas, TX",
      radius_miles: Number($("inRadiusMiles").value) || 50,
      include_simplex:
        state.builderMode === "ROUTE_CORRIDOR" ? $("chkCorridorSimplex").checked : $("chkRadialSimplex").checked,
      repeater_access: accessOpts.length ? accessOpts : ["OPEN"],
      sequence_order: state.sequenceOrder,
      radio_id: state.activePlan?.radio_spec?.id || state.prefs.defaultRadioId || null,
    };

    try {
      const result = await api("/api/plan/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.checkedSlots.clear();
      state.selectedSlot = null;
      state.channelFilter = "ALL";
      state.bandFilter = "ALL";
      renderActivePlan(result);
      toast(result.message || "Plan assembled", "success");
    } catch (err) {
      toast(`Plan assembly failed: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      topBtn.disabled = false;
    }
  }

  // -------------------------------------------------------------------------
  // Active Plan, Target Radio Controls, Channel Table & Undo Delete
  // -------------------------------------------------------------------------
  function renderActivePlan(plan) {
    state.activePlan = plan && plan.active ? plan : null;
    const hasPlan = Boolean(state.activePlan);

    $("emptyWorkspace").classList.toggle("hidden", hasPlan);
    $("activePlanWorkspace").classList.toggle("hidden", !hasPlan);

    const showVfo = Boolean(state.prefs.panel_layout?.vfo?.visible) && hasPlan;
    $("vfoCluster").classList.toggle("hidden", !showVfo);

    if (!hasPlan) {
      $("footerStatus").textContent = "RadioPlanner Cockpit • Ready";
      $("summaryMetricBadge").textContent = "No Plan";
      $("summaryRowsList").innerHTML = `<div class="mgr-card-sub">Assemble a plan to view stops, rings, and band distribution.</div>`;
      $("summaryBandBreakdown").innerHTML = "";
      $("summaryStatesLine").textContent = "";
      $("mapSubtitle").textContent = "Ready";
      clearMapLayers();
      return;
    }

    const { recipe, codeplug, radio_spec: spec, summary, notices, map_data: mapData } = state.activePlan;

    // Topbar VFO Readout
    $("vfoRadio").textContent = `${spec.brand} ${spec.model}`;
    $("vfoSlots").textContent = `${codeplug.total_channels} / ${spec.maxChannels} CH`;
    $("vfoLcd").textContent = `${spec.maxNameLength}c LCD`;
    $("vfoFormat").textContent = recipe.radio_target.programmer_format || spec.programmerType;
    const overLimit = codeplug.total_channels > spec.maxChannels;
    const beacon = $("vfoBeacon");
    beacon.textContent = overLimit ? "⚠ OVER LIMIT" : "● READY";
    beacon.classList.toggle("warn", overLimit);

    // Header
    $("planTitle").textContent = codeplug.name;
    $("planModePill").textContent = recipe.mode;
    const endSlot = codeplug.total_channels > 0 ? spec.startChannel + codeplug.total_channels - 1 : spec.startChannel;
    $("planSpecsLine").innerHTML = `
      <span>Radio: <strong>${escHtml(spec.brand)} ${escHtml(spec.model)}</strong></span>
      <span>Slots: <strong class="mono">${spec.startChannel}..${endSlot}</strong> (${codeplug.total_channels}/${spec.maxChannels})</span>
      <span>LCD: <strong class="mono">${spec.maxNameLength} chars</strong></span>
      <span>Naming: <strong class="mono">${escHtml(recipe.radio_target.naming_format)}</strong></span>
    `;

    // Export controls
    $("exportProgrammerSelect").value = recipe.radio_target.programmer_format || spec.programmerType || "CHIRP";
    $("exportFilenameInput").value = state.activePlan.default_export_filename || "codeplug.csv";

    // Notices
    const noticesWrap = $("planNoticesWrap");
    if (notices && notices.length) {
      noticesWrap.classList.remove("hidden");
      noticesWrap.innerHTML = notices
        .map(
          (n) => `
        <div class="notice-banner ${n.level === "error" ? "error" : ""}">
          <span>⚠ ${escHtml(n.message)}</span>
        </div>`
        )
        .join("");
    } else {
      noticesWrap.classList.add("hidden");
      noticesWrap.innerHTML = "";
    }

    // Target Radio Dropdown
    $("targetRadioSelect").innerHTML = state.radios
      .map(
        (r) =>
          `<option value="${escHtml(r.id)}" ${r.id === spec.id ? "selected" : ""}>${escHtml(r.brand)} ${escHtml(r.model)} (${r.maxChannels} ch, ${r.maxNameLength}c LCD)</option>`
      )
      .join("");

    // Naming Format Dropdown & Sample Preview
    const previews = state.activePlan.naming_previews || [];
    const curNaming = recipe.radio_target.naming_format || "CITY_FREQ";
    $("targetLcdHint").textContent = `Max ${spec.maxNameLength}c LCD`;
    $("lcdColHeader").textContent = `LCD Name (${spec.maxNameLength}c)`;
    $("targetNamingSelect").innerHTML = previews
      .map(
        (p) =>
          `<option value="${escHtml(p.code)}" ${p.code === curNaming ? "selected" : ""}>${escHtml(p.label)} ("${escHtml(p.sample)}")</option>`
      )
      .join("");
    const activePrev = previews.find((p) => p.code === curNaming) || previews[0];
    $("targetNamingSample").textContent = activePrev ? activePrev.sample : "";

    // Band Checkboxes + Optional Standard GMRS Toggle
    const activeBands = new Set(recipe.radio_target.bands || []);
    const hasGmrsCapable = (spec.supportedBands || []).includes("GMRS");
    const hasGmrsStd = (recipe.sequence_order || []).includes("TEMPLATE:gmrs_channels");
    let bandsHtml = `<span class="section-label">Bands:</span>`;
    bandsHtml += (spec.supportedBands || [])
      .map((band) => {
        const checked = activeBands.has(band);
        const dotColor = BAND_PALETTE[band] || "#10b981";
        return `
        <label class="band-chip-label ${checked ? "active" : ""}">
          <input type="checkbox" data-target-band="${escHtml(band)}" ${checked ? "checked" : ""} />
          <span class="band-dot" style="background:${dotColor};"></span>
          <span>${escHtml(band)}</span>
        </label>`;
      })
      .join("");
    if (hasGmrsCapable) {
      bandsHtml += `
        <label class="band-chip-label ${hasGmrsStd ? "active" : ""}" style="margin-left:auto;" title="Include 30 official FCC GMRS channels (Ch 1-22 &amp; 15R-22R)">
          <input type="checkbox" id="chkTargetGmrsStd" ${hasGmrsStd ? "checked" : ""} />
          <span>Std GMRS (30 ch)</span>
        </label>`;
    }
    $("targetBandsRow").innerHTML = bandsHtml;

    // Undo button state
    const canUndo = Boolean(state.activePlan.can_undo);
    $("btnUndoDelete").disabled = !canUndo;
    $("undoCountBadge").textContent = canUndo ? `(${state.activePlan.undo_count})` : "";

    // Summary Panel
    renderSummaryPanel(summary || {});

    // Map Panel
    renderMapData(mapData || {}, summary?.subtitle || "");

    // KPIs & Channels Table
    renderBandKpiStrip();
    renderChannelsTable();

    // Footer status
    const statesStr = summary?.states?.length ? ` • ${summary.states.join(", ")}` : "";
    $("footerStatus").textContent = `${spec.brand} ${spec.model} • ${codeplug.total_channels}/${spec.maxChannels} ch${statesStr}`;
  }

  function renderSummaryPanel(summary) {
    $("summaryTitle").textContent = summary.title || "Plan Summary";
    $("summaryMetricBadge").textContent = summary.metric_badge || "Active";
    const rows = summary.rows || [];
    $("summaryRowsList").innerHTML = rows.length
      ? rows
          .map(
            (r, idx) => `
          <div class="summary-row-item">
            <span style="display:flex; align-items:center; gap:6px; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
              ${r.color ? `<span class="band-dot" style="background:${escHtml(r.color)};"></span>` : ""}
              <span>${idx + 1}. ${escHtml(r.label)}</span>
            </span>
            <span class="mono freq-rx">${escHtml(r.value)}</span>
          </div>`
          )
          .join("")
      : `<div class="mgr-card-sub">No route or ring rows available.</div>`;

    const bandCounts = summary.band_counts || {};
    $("summaryBandBreakdown").innerHTML = Object.entries(bandCounts)
      .map(
        ([band, count]) => `
        <div class="summary-band-card">
          <span style="display:flex; align-items:center; gap:6px; font-weight:700;">
            <span class="band-dot" style="background:${BAND_PALETTE[band] || "#10b981"};"></span>
            <span>${escHtml(band)}</span>
          </span>
          <strong class="mono">${count}</strong>
        </div>`
      )
      .join("");

    $("summaryStatesLine").textContent = summary.states?.length
      ? `State Datasets: ${summary.states.join(", ")}`
      : "";
  }

  function renderBandKpiStrip() {
    const strip = $("bandKpiStrip");
    if (!state.activePlan) {
      strip.innerHTML = "";
      return;
    }
    const channels = state.activePlan.codeplug.channels || [];
    const bandCounts = state.activePlan.summary?.band_counts || {};
    let html = `<button type="button" class="stat-chip ${state.bandFilter === "ALL" ? "active" : ""}" data-kpi-band="ALL">Total <strong>${channels.length}</strong></button>`;
    for (const [band, count] of Object.entries(bandCounts)) {
      if (count > 0 || state.bandFilter === band) {
        html += `<button type="button" class="stat-chip ${state.bandFilter === band ? "active" : ""}" data-kpi-band="${escHtml(band)}">
          <span class="band-dot" style="background:${BAND_PALETTE[band] || "#10b981"};"></span>
          ${escHtml(band)} <strong>${count}</strong>
        </button>`;
      }
    }
    strip.innerHTML = html;
  }

  function getFilteredChannels() {
    if (!state.activePlan) return [];
    const q = state.searchQuery.trim().toLowerCase();
    return (state.activePlan.codeplug.channels || []).filter((ch) => {
      if (state.bandFilter !== "ALL" && ch.band !== state.bandFilter) return false;
      if (state.channelFilter === "REPEATERS" && ch.specialType !== "REPEATERS") return false;
      if (state.channelFilter === "CALLING" && ch.specialType !== "CALLING") return false;
      if (state.channelFilter === "WX" && ch.specialType !== "WX") return false;
      if (state.channelFilter === "AVIATION" && ch.specialType !== "AVIATION") return false;
      if (state.channelFilter === "SIMPLEX" && !ch.is_simplex) return false;
      if (state.channelFilter === "DMR" && String(ch.mode || "").toUpperCase() !== "DMR") return false;
      if (q) {
        const hay = `${ch.number} ${ch.name} ${ch.callsign || ""} ${ch.rxFreq} ${ch.city || ""} ${ch.state || ""} ${ch.comment || ""} ${ch.band} ${ch.mode}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function updateSelectedCountUi() {
    const count = state.checkedSlots.size;
    $("selectedCount").textContent = String(count);
    $("btnDeleteSelected").disabled = count === 0;
  }

  function renderChannelsTable() {
    const tbody = $("channelsTbody");
    const rows = getFilteredChannels();

    document.querySelectorAll("[data-ch-filter]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.chFilter === state.channelFilter);
    });

    if (!rows.length) {
      tbody.innerHTML = "";
      $("tableEmpty").classList.remove("hidden");
      $("selectAllChannels").checked = false;
      updateSelectedCountUi();
      return;
    }

    $("tableEmpty").classList.add("hidden");
    const allVisibleChecked = rows.every((ch) => state.checkedSlots.has(ch.number));
    $("selectAllChannels").checked = allVisibleChecked;

    tbody.innerHTML = rows
      .map((ch) => {
        const isSelected = state.selectedSlot === ch.number;
        const isChecked = state.checkedSlots.has(ch.number);
        let typePill = `<span class="pill pill-emerald">${escHtml(ch.band)}</span>`;
        if (ch.specialType === "CALLING") typePill = `<span class="pill pill-amber">CALL</span>`;
        else if (ch.specialType === "WX") typePill = `<span class="pill pill-cyan">WX</span>`;
        else if (ch.specialType === "AVIATION") typePill = `<span class="pill pill-violet">AIR</span>`;

        const dupText = ch.is_simplex ? "Simplex" : `${ch.offsetDir} ${Number(ch.offset).toFixed(3)}`;
        let toneText = "-";
        if (["Tone", "TSQL"].includes(ch.toneMode) && ch.ctcss && ch.ctcss !== "None") {
          toneText = `${ch.toneMode} ${ch.ctcss}`;
        } else if (["DCS", "DTCS"].includes(ch.toneMode) && ch.dcs && ch.dcs !== "None") {
          toneText = `DCS ${ch.dcs}`;
        }
        const locText =
          ch.city && ch.state ? `${ch.city}, ${ch.state}` : ch.city || ch.comment || "-";
        const hasCoords = Boolean(ch.lat && ch.lon);

        return `
        <tr data-slot="${ch.number}" class="${isSelected ? "selected" : ""}">
          <td class="col-chk">
            <input type="checkbox" class="ch-row-chk" data-chk-slot="${ch.number}" ${isChecked ? "checked" : ""} aria-label="Select slot ${ch.number}" />
          </td>
          <td class="col-slot mono">${ch.number}</td>
          <td class="col-badges">${typePill} <span class="pill mono">${escHtml(ch.mode)}</span></td>
          <td class="col-lcd"><span class="lcd-badge">${escHtml(ch.name)}</span></td>
          <td class="col-call mono">${escHtml(ch.callsign || "-")}</td>
          <td class="col-freq mono freq-rx">${Number(ch.rxFreq).toFixed(5)}</td>
          <td class="col-freq mono freq-tx">${Number(ch.txFreq).toFixed(5)}</td>
          <td class="col-dup mono">${escHtml(dupText)}</td>
          <td class="col-tone mono">${escHtml(toneText)}</td>
          <td class="col-loc" title="${escHtml(locText)}">${escHtml(locText)}</td>
          <td class="col-act">
            <div class="row-actions">
              <button type="button" class="btn btn-ghost btn-xs" data-row-action="edit" title="Edit channel (E)">Edit</button>
              <button type="button" class="btn btn-ghost btn-xs" data-row-action="net-logger" title="Copy W5CDN Net Logger repeater preset JSON">NetLog</button>
              ${hasCoords ? `<button type="button" class="btn btn-ghost btn-xs" data-row-action="locate" title="Locate on map (L)">📍</button>` : ""}
              <button type="button" class="btn btn-ghost btn-xs" data-row-action="delete" title="Delete channel (Del)">✕</button>
            </div>
          </td>
        </tr>`;
      })
      .join("");
    updateSelectedCountUi();
  }

  async function updateCodeplugTarget(radioChanged = false) {
    if (!state.activePlan) return;
    const radioId = $("targetRadioSelect").value;
    const namingFormat = $("targetNamingSelect").value;
    const bands = Array.from(document.querySelectorAll("[data-target-band]:checked")).map(
      (el) => el.dataset.targetBand
    );
    const gmrsChk = $("chkTargetGmrsStd");
    const includeGmrsStd = gmrsChk ? gmrsChk.checked : false;

    try {
      const updated = await api("/api/codeplug/update", {
        method: "POST",
        body: JSON.stringify({
          radio_id: radioId,
          naming_format: namingFormat,
          bands,
          include_gmrs_std: includeGmrsStd,
          radio_changed: radioChanged,
        }),
      });
      state.checkedSlots.clear();
      renderActivePlan(updated);
      toast(updated.message || "Target radio updated", "success");
    } catch (err) {
      toast(`Update failed: ${err.message}`, "error");
    }
  }

  async function deleteSlots(slots) {
    if (!slots.length) return;
    try {
      const updated = await api("/api/codeplug/delete-channels", {
        method: "POST",
        body: JSON.stringify({ slots }),
      });
      state.checkedSlots.clear();
      state.selectedSlot = null;
      renderActivePlan(updated);
      toast(updated.message || "Channels deleted", "success");
    } catch (err) {
      toast(`Delete failed: ${err.message}`, "error");
    }
  }

  async function undoLastChannelChange() {
    if (!state.activePlan || !state.activePlan.can_undo) return;
    try {
      const updated = await api("/api/codeplug/undo-delete", { method: "POST" });
      state.checkedSlots.clear();
      renderActivePlan(updated);
      toast(updated.message || "Undone", "success");
    } catch (err) {
      toast(`Undo failed: ${err.message}`, "error");
    }
  }

  async function expandDmrTalkgroups() {
    if (!state.activePlan) return;
    try {
      const updated = await api("/api/codeplug/expand-dmr", { method: "POST" });
      renderActivePlan(updated);
      toast(updated.message || "DMR talkgroups expanded", "success");
    } catch (err) {
      toast(`DMR expansion failed: ${err.message}`, "error");
    }
  }

  async function exportActiveCsv() {
    if (!state.activePlan) return;
    const programmer = $("exportProgrammerSelect").value;
    const filename = $("exportFilenameInput").value.trim() || "codeplug.csv";
    try {
      const resp = await fetch("/api/codeplug/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ programmer_type: programmer, filename }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const csvText = await resp.text();
      const outName = filename.toLowerCase().endsWith(".csv") ? filename : `${filename}.csv`;
      downloadTextFile(outName, csvText, "text/csv;charset=utf-8");
      toast(`Exported ${outName} (${programmer}) & saved to ./exports/`, "success");
    } catch (err) {
      toast(`Export failed: ${err.message}`, "error");
    }
  }

  // -------------------------------------------------------------------------
  // Inline Channel Editor Modal
  // -------------------------------------------------------------------------
  function updateEditChannelNameCounter() {
    const maxLen = state.activePlan?.radio_spec?.maxNameLength || 8;
    const len = $("editChName").value.length;
    const el = $("editChNameCount");
    el.textContent = `${len} / ${maxLen}`;
    el.style.color = len > maxLen ? "var(--accent-rose-text)" : "var(--text-muted)";
  }

  function syncEditChannelControls() {
    const dir = $("editChOffsetDir").value;
    const offInput = $("editChOffset");
    if (dir === "off") {
      offInput.value = "0.000";
      offInput.readOnly = true;
    } else {
      offInput.readOnly = false;
      if (Number(offInput.value || 0) === 0) {
        const rx = Number($("editChRx").value || 146.52);
        offInput.value = rx >= 420 && rx <= 470 ? "5.000" : "0.600";
      }
    }

    const tm = $("editChToneMode").value;
    const tv = $("editChToneVal");
    if (tm === "None") {
      tv.value = "None";
      tv.readOnly = true;
    } else {
      tv.readOnly = false;
      if (!tv.value || tv.value === "None") {
        tv.value = tm === "DCS" ? "023" : "100.0";
      }
    }
  }

  function openEditChannelModal(slot) {
    if (!state.activePlan) return;
    const ch = (state.activePlan.codeplug.channels || []).find((c) => c.number === slot);
    if (!ch) return;
    const maxLen = state.activePlan.radio_spec.maxNameLength || 8;

    $("editChannelTitle").textContent = `Edit Channel — Slot #${ch.number}`;
    $("editChSlot").value = String(ch.number);
    $("editChName").value = ch.name || "";
    $("editChName").maxLength = maxLen;
    $("editChCallsign").value = ch.callsign || "";
    $("editChRx").value = Number(ch.rxFreq).toFixed(5);
    $("editChOffsetDir").value = ch.is_simplex ? "off" : ch.offsetDir || "off";
    $("editChOffset").value = ch.is_simplex ? "0.000" : Number(ch.offset || 0).toFixed(3);
    $("editChMode").value = ch.mode || "FM";
    $("editChPower").value = ch.power || "High";
    $("editChToneMode").value = ch.toneMode || "None";
    $("editChToneVal").value =
      ch.toneMode === "DCS" || ch.toneMode === "DTCS"
        ? ch.dcs || "023"
        : ch.toneMode === "Tone" || ch.toneMode === "TSQL"
          ? ch.ctcss || "88.5"
          : "None";
    $("editChCity").value = ch.city || "";
    $("editChState").value = ch.state || "";
    $("editChComment").value = ch.comment || "";

    updateEditChannelNameCounter();
    syncEditChannelControls();
    $("editChannelBackdrop").classList.remove("hidden");
    $("editChName").focus();
    $("editChName").select();
  }

  // -------------------------------------------------------------------------
  // Printable Pocket Reference Card / Plan Report Modal
  // -------------------------------------------------------------------------
  function populatePrintCard(report) {
    const rowsHtml = (report.channels || [])
      .map((ch) => {
        const dup = ch.is_simplex ? "Simplex" : `${ch.offsetDir}${Number(ch.offset).toFixed(3)}`;
        const tone =
          ["Tone", "TSQL"].includes(ch.toneMode) && ch.ctcss !== "None"
            ? `${ch.toneMode} ${ch.ctcss}`
            : ["DCS", "DTCS"].includes(ch.toneMode) && ch.dcs !== "None"
              ? `DCS ${ch.dcs}`
              : "CSQ";
        const loc = ch.city && ch.state ? `${ch.city}, ${ch.state}` : ch.city || ch.comment || "-";
        return `
          <tr>
            <td class="mono">${ch.number}</td>
            <td class="mono"><strong>${escHtml(ch.name)}</strong></td>
            <td class="mono">${escHtml(ch.callsign || "-")}</td>
            <td class="mono">${Number(ch.rxFreq).toFixed(4)}</td>
            <td class="mono">${escHtml(dup)}</td>
            <td class="mono">${escHtml(tone)}</td>
            <td class="mono">${escHtml(ch.mode)}</td>
            <td>${escHtml(loc)}</td>
          </tr>`;
      })
      .join("");

    $("printCardContainer").innerHTML = `
      <div class="print-card-header">
        <h2 style="margin:0 0 4px 0;">RadioPlanner Pocket Reference Card — ${escHtml(report.name)}</h2>
        <div class="mono" style="font-size:9pt;">
          Target: ${escHtml(report.radio)} | Mode: ${escHtml(report.mode)} | Operator: ${escHtml(report.operator)} | Generated: ${escHtml(report.generated_at)}
        </div>
        ${report.coverage ? `<div style="font-size:9pt; margin-top:2px;">Coverage: ${escHtml(report.coverage)}</div>` : ""}
      </div>
      <table class="print-card-table">
        <thead>
          <tr>
            <th>Ch</th>
            <th>LCD Name</th>
            <th>Callsign</th>
            <th>RX (MHz)</th>
            <th>Duplex</th>
            <th>Tone / DCS</th>
            <th>Mode</th>
            <th>Location / Notes</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    `;
  }

  async function openPlanReportModal() {
    if (!state.activePlan) return;
    try {
      const report = await api("/api/codeplug/report");
      state.activeReport = report;
      $("planReportTitle").textContent = `Pocket Reference Card — ${report.name}`;
      $("reportModePill").textContent = report.mode;
      $("reportMetaStrip").innerHTML = `
        <span>Radio: <strong>${escHtml(report.radio)}</strong></span>
        <span>Programmer: <strong class="mono">${escHtml(report.programmer)}</strong></span>
        <span>LCD: <strong class="mono">${report.lcd_limit} chars</strong></span>
        <span>Operator: <strong class="mono">${escHtml(report.operator)}</strong></span>
        ${report.coverage ? `<span>Coverage: <strong>${escHtml(report.coverage)}</strong></span>` : ""}
      `;
      const k = report.kpis || {};
      $("reportKpiGrid").innerHTML = `
        <div class="report-kpi-card"><span class="report-kpi-label">Total Channels</span><span class="report-kpi-value">${k.total_channels ?? 0}</span></div>
        <div class="report-kpi-card"><span class="report-kpi-label">Memory Used</span><span class="report-kpi-value">${k.capacity_pct ?? 0}%</span></div>
        <div class="report-kpi-card"><span class="report-kpi-label">Repeaters</span><span class="report-kpi-value">${k.repeaters ?? 0}</span></div>
        <div class="report-kpi-card"><span class="report-kpi-label">Simplex</span><span class="report-kpi-value">${k.simplex ?? 0}</span></div>
        <div class="report-kpi-card"><span class="report-kpi-label">DMR</span><span class="report-kpi-value">${k.dmr ?? 0}</span></div>
        <div class="report-kpi-card"><span class="report-kpi-label">Active Bands</span><span class="report-kpi-value">${k.bands_active ?? 0}</span></div>
      `;
      $("planReportText").value = report.text || "";
      populatePrintCard(report);
      $("planReportBackdrop").classList.remove("hidden");
    } catch (err) {
      toast(`Could not load report: ${err.message}`, "error");
    }
  }

  // -------------------------------------------------------------------------
  // Interactive Leaflet Coverage Map (Offline-Graceful + Spiderfying)
  // -------------------------------------------------------------------------
  function ensureLeafletMap() {
    if (state.leafletMap || typeof window.L === "undefined") return;
    const mapEl = $("planLeafletMap");
    if (!mapEl) return;
    const L = window.L;
    const map = L.map(mapEl).setView([32.35, -95.3], 6);

    const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    });
    const cartoDark = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap &copy; CARTO",
      maxZoom: 19,
    });
    osm.addTo(map);
    L.control.layers({ "Highway / Street (OSM)": osm, "Dark Radar": cartoDark }).addTo(map);

    state.leafletMap = map;
    state.leafletOverlayGroup = L.layerGroup().addTo(map);
    state.leafletChannelGroup = L.layerGroup().addTo(map);

    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(() => map.invalidateSize());
      ro.observe(mapEl);
    }
  }

  function clearMapLayers() {
    if (state.leafletOverlayGroup) state.leafletOverlayGroup.clearLayers();
    if (state.leafletChannelGroup) state.leafletChannelGroup.clearLayers();
    state.markerBySlot.clear();
  }

  function renderMapData(mapData, subtitle) {
    $("mapSubtitle").textContent = subtitle || "Active";
    ensureLeafletMap();
    if (!state.leafletMap || typeof window.L === "undefined") return;
    const L = window.L;

    clearMapLayers();
    const bounds = [];

    if (mapData.route_coords && mapData.route_coords.length >= 2) {
      L.polyline(mapData.route_coords, { color: "#22d3ee", weight: 4, opacity: 0.85 }).addTo(state.leafletOverlayGroup);
      mapData.route_coords.forEach((c) => bounds.push(c));
    }

    if (mapData.rings && mapData.center) {
      [...mapData.rings].reverse().forEach((rObj) => {
        const rMiles = typeof rObj === "object" ? rObj.end_mi : rObj;
        const rColor = (typeof rObj === "object" && rObj.color) || "#38bdf8";
        const circle = L.circle(mapData.center, {
          radius: rMiles * 1609.34,
          color: rColor,
          weight: 2.5,
          fillColor: rColor,
          fillOpacity: 0.06,
          dashArray: "6 4",
        }).addTo(state.leafletOverlayGroup);
        if (typeof rObj === "object" && rObj.index) {
          circle.bindTooltip(
            `<b>Ring ${rObj.index}</b> (${Number(rObj.start_mi).toFixed(0)}–${Number(rObj.end_mi).toFixed(0)} mi): ${rObj.count} ch`,
            { sticky: true }
          );
        }
      });
    }

    const wpSet = new Set();
    if (mapData.waypoints) {
      mapData.waypoints.forEach((wp, idx) => {
        bounds.push([wp.lat, wp.lon]);
        wpSet.add(`${Number(wp.lat).toFixed(3)},${Number(wp.lon).toFixed(3)}`);
        L.circleMarker([wp.lat, wp.lon], {
          radius: 7,
          fillColor: "#f59e0b",
          color: "#ffffff",
          weight: 2,
          fillOpacity: 1,
        })
          .addTo(state.leafletOverlayGroup)
          .bindPopup(`<b>Stop ${idx + 1}: ${escHtml(wp.name)}</b>`);
      });
    }

    const groups = {};
    const validChannels = (mapData.channels || []).filter((ch) => ch.lat && ch.lon);
    validChannels.forEach((ch) => {
      bounds.push([ch.lat, ch.lon]);
      const key = `${Number(ch.lat).toFixed(3)},${Number(ch.lon).toFixed(3)}`;
      if (!groups[key]) groups[key] = [];
      groups[key].push(ch);
    });

    Object.entries(groups).forEach(([key, group]) => {
      const overlapsWp = wpSet.has(key);
      const count = group.length;
      group.forEach((ch, idx) => {
        let plotLat = ch.lat;
        let plotLon = ch.lon;
        if (count > 1 || overlapsWp) {
          const ringNum = Math.floor(idx / 8) + 1;
          const itemsInRing = Math.min(8, count - (ringNum - 1) * 8);
          const angle = (2 * Math.PI * (idx % 8)) / Math.max(1, itemsInRing) + ringNum * 0.35;
          const radiusDeg = 0.014 * ringNum;
          const cosLat = Math.max(0.2, Math.cos((ch.lat * Math.PI) / 180));
          plotLat = ch.lat + radiusDeg * Math.sin(angle);
          plotLon = ch.lon + (radiusDeg / cosLat) * Math.cos(angle);
          L.polyline(
            [
              [ch.lat, ch.lon],
              [plotLat, plotLon],
            ],
            { color: "#94a3b8", weight: 1.2, opacity: 0.7, dashArray: "2 3" }
          ).addTo(state.leafletChannelGroup);
        }

        const color = ch.color || BAND_PALETTE[ch.band] || "#10b981";
        const marker = L.circleMarker([plotLat, plotLon], {
          radius: 6.5,
          fillColor: color,
          color: "#0f172a",
          weight: 1.5,
          fillOpacity: 0.95,
        }).addTo(state.leafletChannelGroup);

        marker.bindTooltip(
          `<b>#${ch.number} ${escHtml(ch.callsign || ch.name)}</b> (${Number(ch.rxFreq).toFixed(3)} MHz • ${escHtml(ch.band)})`,
          { direction: "top", offset: [0, -6] }
        );
        marker.bindPopup(
          `<div>
            <b>#${ch.number} ${escHtml(ch.name)}</b> <b>[${escHtml(ch.band)}]</b><br/>
            Callsign: <b>${escHtml(ch.callsign || "-")}</b> | RX: <b>${Number(ch.rxFreq).toFixed(4)} MHz</b> (${escHtml(ch.mode)})<br/>
            Tone: ${escHtml(ch.tone || "CSQ")} | ${escHtml(ch.location || "")}
          </div>`
        );
        state.markerBySlot.set(ch.number, marker);
      });
    });

    if (bounds.length >= 2) {
      state.leafletMap.fitBounds(bounds, { padding: [26, 26] });
    } else if (bounds.length === 1) {
      state.leafletMap.setView(bounds[0], 10);
    }
    invalidateMapSoon();
  }

  function locateSlotOnMap(slot) {
    const marker = state.markerBySlot.get(slot);
    if (!marker || !state.leafletMap) {
      toast("This channel does not have map coordinates", "info");
      return;
    }
    if (!state.prefs.panel_layout?.map?.visible) {
      togglePanel("map", true);
    }
    const ll = marker.getLatLng();
    state.leafletMap.setView(ll, Math.max(state.leafletMap.getZoom(), 11));
    marker.openPopup();
  }

  // -------------------------------------------------------------------------
  // Saved Recipes Slide-Out Drawer
  // -------------------------------------------------------------------------
  function toggleRecipesDrawer(forceOpen = null) {
    const backdrop = $("recipesDrawerBackdrop");
    const isHidden = backdrop.classList.contains("hidden");
    const nextOpen = forceOpen === null ? isHidden : Boolean(forceOpen);
    backdrop.classList.toggle("hidden", !nextOpen);
    $("btnToggleRecipes").classList.toggle("active", nextOpen);
    if (nextOpen) {
      loadRecipes();
      setTimeout(() => $("recipesSearch").focus(), 40);
    }
  }

  async function loadRecipes() {
    try {
      const data = await api("/api/recipes");
      state.recipes = data.recipes || [];
      renderRecipesList();
    } catch (err) {
      toast(`Could not load recipes: ${err.message}`, "error");
    }
  }

  function renderRecipesList() {
    const q = $("recipesSearch").value.trim().toLowerCase();
    const filtered = state.recipes.filter((r) => {
      if (!q) return true;
      return `${r.name} ${r.filename} ${r.mode} ${r.description || ""}`.toLowerCase().includes(q);
    });
    $("recipeCountLabel").textContent = String(state.recipes.length);
    $("railRecipeBadge").textContent = String(state.recipes.length);

    if (!filtered.length) {
      $("recipesList").innerHTML = `<div class="table-empty">No saved recipes match your search.</div>`;
      return;
    }

    $("recipesList").innerHTML = filtered
      .map((item) => {
        let meta = "";
        if (item.mode === "ROUTE_CORRIDOR" && item.corridor) {
          meta = `${(item.corridor.waypoints || []).join(" → ")} (${item.corridor.corridor_width_miles} mi)`;
        } else if (item.mode === "PROXIMITY_SEARCH" && item.proximity) {
          meta = `${item.proximity.center_location} (${item.proximity.radius_miles} mi)`;
        } else if (item.mode === "AVIATION_PLANNER" && item.aviation) {
          meta = `${item.aviation.center_location} (${item.aviation.radius_miles} mi)`;
        }
        return `
        <div class="recipe-card ${state.loadedRecipeFile === item.filename ? "active" : ""}" data-recipe-file="${escHtml(item.filename)}">
          <div class="recipe-card-top">
            <span class="recipe-card-name" title="${escHtml(item.name)}">${escHtml(item.name)}</span>
            <span class="pill pill-blue mono">${escHtml(item.mode)}</span>
          </div>
          ${item.description ? `<div class="recipe-card-meta">${escHtml(item.description)}</div>` : ""}
          <div class="recipe-card-meta mono">${escHtml(meta || item.filename)}</div>
          <div class="recipe-card-actions">
            <button type="button" class="btn btn-primary btn-xs" data-recipe-action="load">▶ Load in Builder</button>
            <div class="plan-actions">
              <button type="button" class="btn btn-xs" data-recipe-action="export" title="Export YAML copy for hand-editing">YAML</button>
              <button type="button" class="btn btn-danger btn-xs" data-recipe-action="delete">Delete</button>
            </div>
          </div>
        </div>`;
      })
      .join("");
  }

  function applyRecipeToBuilder(filename, rec) {
    state.loadedRecipeFile = filename;
    const mode = rec.mode === "PRESET_TEMPLATES" ? "ROUTE_CORRIDOR" : rec.mode;
    if (rec.corridor) {
      state.waypoints = rec.corridor.waypoints?.length ? [...rec.corridor.waypoints] : ["Tyler, TX", "Shreveport, LA"];
      $("inCorridorWidth").value = String(rec.corridor.corridor_width_miles ?? 25);
    }
    if (rec.proximity && mode === "PROXIMITY_SEARCH") {
      $("inCenterLocation").value = rec.proximity.center_location || "Dallas, TX";
      $("inRadiusMiles").value = String(rec.proximity.radius_miles ?? 50);
    }
    if (rec.aviation && mode === "AVIATION_PLANNER") {
      $("inCenterLocation").value = rec.aviation.center_location || "Tyler, TX";
      $("inRadiusMiles").value = String(rec.aviation.radius_miles ?? 35);
    }
    const simplex = rec.radio_target?.include_simplex !== false;
    $("chkCorridorSimplex").checked = simplex;
    $("chkRadialSimplex").checked = simplex;
    const acc = new Set(rec.radio_target?.repeater_access || ["OPEN"]);
    document.querySelectorAll("[data-access-opt]").forEach((cb) => {
      cb.checked = acc.has(cb.dataset.accessOpt);
    });
    $("inPlanName").value = rec.name || "";
    $("inPlanDesc").value = rec.description || "";
    state.sequenceOrder = rec.sequence_order?.length ? [...rec.sequence_order] : defaultSequenceForMode(mode);

    setBuilderMode(mode, true);
    renderWaypointsList();
    $("loadedRecipeText").textContent = `Loaded: ${filename}`;
    $("loadedRecipeBanner").classList.remove("hidden");
    if (!state.prefs.panel_layout?.builder?.visible) togglePanel("builder", true);
    toggleRecipesDrawer(false);
    toast(`Loaded recipe '${rec.name}' — click Assemble Plan & Map`, "success");
  }

  // -------------------------------------------------------------------------
  // Preset Templates Panel & Spreadsheet Editor Modal
  // -------------------------------------------------------------------------
  function renderTemplatesPanel() {
    $("railTplBadge").textContent = String(state.templates.length);
    renderTemplatePicker();
    const q = $("templatesSearch").value.trim().toLowerCase();
    const filtered = state.templates.filter((t) => {
      if (!q) return true;
      return `${t.name} ${t.id} ${t.tagText} ${t.description}`.toLowerCase().includes(q);
    });
    $("templatesList").innerHTML = filtered.length
      ? filtered
          .map(
            (t) => `
        <div class="mgr-card" data-tpl-id="${escHtml(t.id)}">
          <div class="mgr-card-head">
            <span class="mgr-card-title">${escHtml(t.name)}</span>
            <span class="pill pill-cyan mono">${escHtml(t.tagText)} • ${t.channelCount} ch</span>
          </div>
          <div class="mgr-card-sub">${escHtml(t.description || t.id)}</div>
          <div class="recipe-card-actions">
            <button type="button" class="btn btn-primary btn-xs" data-tpl-action="edit">Edit Channels</button>
            <div class="plan-actions">
              <button type="button" class="btn btn-xs" data-tpl-action="export" title="Export YAML copy for hand-editing">YAML</button>
              <button type="button" class="btn btn-xs" data-tpl-action="insert">+ Sequence</button>
              ${t.is_builtin ? "" : `<button type="button" class="btn btn-danger btn-xs" data-tpl-action="delete">Delete</button>`}
            </div>
          </div>
        </div>`
          )
          .join("")
      : `<div class="table-empty">No matching templates.</div>`;
  }

  function createTplSheetRowHtml(ch = {}) {
    const offDir = ch.offsetDir || "off";
    const toneMode = ch.toneMode || "None";
    const modes = ["FM", "NFM", "AM", "DMR", "USB", "LSB", "CW"];
    const powers = ["High", "Mid", "Low"];
    const toneModes = ["None", "Tone", "TSQL", "DCS"];
    return `
      <tr class="tpl-sheet-row">
        <td>
          <div class="row-actions">
            <button type="button" class="btn btn-ghost btn-xs" data-tpl-row="up" title="Move Up">▲</button>
            <button type="button" class="btn btn-ghost btn-xs" data-tpl-row="down" title="Move Down">▼</button>
          </div>
        </td>
        <td><input type="text" class="input input-sm mono" data-f="name" value="${escHtml(ch.name || "CH")}" required /></td>
        <td><input type="number" class="input input-sm mono" data-f="rxFreq" step="0.00001" value="${Number(ch.rxFreq ?? 146.52).toFixed(5)}" required /></td>
        <td>
          <select class="select select-sm" data-f="offsetDir">
            <option value="off" ${offDir === "off" ? "selected" : ""}>Simplex</option>
            <option value="+" ${offDir === "+" ? "selected" : ""}>+ Offset</option>
            <option value="-" ${offDir === "-" ? "selected" : ""}>- Offset</option>
          </select>
        </td>
        <td><input type="number" class="input input-sm mono" data-f="offset" step="0.005" value="${Number(ch.offset ?? 0).toFixed(3)}" ${offDir === "off" ? "readonly" : ""} /></td>
        <td>
          <select class="select select-sm" data-f="mode">
            ${modes.map((m) => `<option value="${m}" ${(ch.mode || "FM") === m ? "selected" : ""}>${m}</option>`).join("")}
          </select>
        </td>
        <td>
          <select class="select select-sm" data-f="power">
            ${powers.map((p) => `<option value="${p}" ${(ch.power || "High") === p ? "selected" : ""}>${p}</option>`).join("")}
          </select>
        </td>
        <td>
          <select class="select select-sm" data-f="toneMode">
            ${toneModes.map((tm) => `<option value="${tm}" ${toneMode === tm ? "selected" : ""}>${tm}</option>`).join("")}
          </select>
        </td>
        <td><input type="text" class="input input-sm mono" data-f="toneVal" list="standardTonesList" value="${escHtml(ch.toneVal || "None")}" ${toneMode === "None" ? "readonly" : ""} /></td>
        <td><input type="text" class="input input-sm" data-f="comment" value="${escHtml(ch.comment || "")}" /></td>
        <td><button type="button" class="btn btn-danger btn-xs" data-tpl-row="del" title="Remove row">✕</button></td>
      </tr>`;
  }

  function openTemplateEditorModal(tpl = null) {
    state.editingTemplateId = tpl ? tpl.id : null;
    $("tplEditorTitle").textContent = tpl ? `Edit Template — ${tpl.name}` : "New Blank Preset Template";
    $("tplEditId").value = tpl ? tpl.id : "";
    $("tplEditId").readOnly = Boolean(tpl);
    $("tplEditName").value = tpl ? tpl.name : "";
    $("tplEditTag").value = tpl ? tpl.tagText : "CUSTOM";
    $("tplEditColor").value = tpl && tpl.tagColorHex ? tpl.tagColorHex : "#00BCD4";
    $("tplEditDesc").value = tpl ? tpl.description || "" : "";

    const channels = tpl && tpl.channels?.length
      ? tpl.channels
      : [{ name: "2m CALL", rxFreq: 146.52, offsetDir: "off", offset: 0, mode: "FM", power: "High", toneMode: "None", toneVal: "None", comment: "Simplex" }];
    $("tplEditorTbody").innerHTML = channels.map((c) => createTplSheetRowHtml(c)).join("");
    $("templateEditorBackdrop").classList.remove("hidden");
  }

  // -------------------------------------------------------------------------
  // Radios & Hardware Specs Panel & Editor Modal
  // -------------------------------------------------------------------------
  function renderRadiosPanel() {
    $("railRadioBadge").textContent = String(state.radios.length);
    const q = $("radiosSearch").value.trim().toLowerCase();
    const filtered = state.radios.filter((r) => {
      if (!q) return true;
      return `${r.brand} ${r.model} ${r.id} ${(r.supportedBands || []).join(" ")}`.toLowerCase().includes(q);
    });
    $("radiosList").innerHTML = filtered.length
      ? filtered
          .map(
            (r) => `
        <div class="mgr-card" data-radio-id="${escHtml(r.id)}">
          <div class="mgr-card-head">
            <span class="mgr-card-title">${escHtml(r.brand)} ${escHtml(r.model)}</span>
            <span class="pill pill-emerald mono">${r.maxChannels} ch • ${r.maxNameLength}c</span>
          </div>
          <div class="mgr-card-sub mono">Start ${r.startChannel} • ${escHtml(r.programmerType)} • ${(r.supportedBands || []).join(", ")}</div>
          <div class="recipe-card-actions">
            <button type="button" class="btn btn-primary btn-xs" data-radio-action="edit">Edit Spec</button>
            <div class="plan-actions">
              <button type="button" class="btn btn-xs" data-radio-action="export" title="Export YAML copy for hand-editing">YAML</button>
              ${state.activePlan ? `<button type="button" class="btn btn-xs" data-radio-action="target">Target</button>` : ""}
              ${r.is_user ? `<button type="button" class="btn btn-danger btn-xs" data-radio-action="delete">Delete</button>` : ""}
            </div>
          </div>
        </div>`
          )
          .join("")
      : `<div class="table-empty">No matching radio hardware models.</div>`;
  }

  function openRadioEditorModal(spec = null) {
    $("radioEditorTitle").textContent = spec ? `Edit Radio — ${spec.brand} ${spec.model}` : "Add Custom Radio Model";
    $("radBrand").value = spec ? spec.brand : "";
    $("radModel").value = spec ? spec.model : "";
    $("radId").value = spec ? spec.id : "";
    $("radDesc").value = spec ? spec.description || "" : "";
    $("radStart").value = String(spec ? spec.startChannel : 1);
    $("radMaxCh").value = String(spec ? spec.maxChannels : 128);
    $("radMaxName").value = String(spec ? spec.maxNameLength : 8);
    $("radProg").value = spec ? spec.programmerType : "RT_SYSTEMS";
    $("radBands").value = spec ? (spec.supportedBands || []).join(", ") : "2m, 70cm, WX";
    $("radModes").value = spec ? (spec.supportedModes || []).join(", ") : "FM, AM";
    $("radAllowDots").checked = spec ? Boolean(spec.allowDots) : true;
    $("radAllowSpaces").checked = spec ? Boolean(spec.allowSpaces) : true;
    $("radioEditorBackdrop").classList.remove("hidden");
  }

  // -------------------------------------------------------------------------
  // Preferences Modal (9 Themes, Fonts, Operator, API Keys & State Cache)
  // -------------------------------------------------------------------------
  function setPrefTab(tabName) {
    document.querySelectorAll("[data-pref-tab]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.prefTab === tabName);
    });
    $("prefTabAppearance").classList.toggle("hidden", tabName !== "appearance");
    $("prefTabOperator").classList.toggle("hidden", tabName !== "operator");
    $("prefTabApi").classList.toggle("hidden", tabName !== "api");
    $("prefTabSystem").classList.toggle("hidden", tabName !== "system");
  }

  function updateSliderTip(sliderEl, tipEl, valEl) {
    const val = Number(sliderEl.value);
    const min = Number(sliderEl.min);
    const max = Number(sliderEl.max);
    const pct = ((val - min) / Math.max(1, max - min)) * 100;
    tipEl.textContent = `${val}px`;
    tipEl.style.left = `${pct}%`;
    valEl.textContent = `${val}px`;
  }

  function previewDraftVisuals() {
    applyVisualPrefs({
      theme: state.draftTheme,
      ui_font: $("prefUiFont").value,
      mono_font: $("prefMonoFont").value,
      font_size: Number($("prefFontSize").value),
      lcd_font_size: Number($("prefLcdSize").value),
    });
  }

  function openPreferencesModal(tab = "appearance") {
    state.draftTheme = state.prefs.theme || "shack-dark";
    document.querySelectorAll("[data-theme-pick]").forEach((card) => {
      card.classList.toggle("active", card.dataset.themePick === state.draftTheme);
    });
    $("prefUiFont").value = state.prefs.ui_font || "system";
    $("prefMonoFont").value = state.prefs.mono_font || "cascadia";
    $("prefFontSize").value = String(state.prefs.font_size || 14);
    $("prefLcdSize").value = String(state.prefs.lcd_font_size || 15);
    updateSliderTip($("prefFontSize"), $("prefFontSizeTip"), $("prefFontSizeVal"));
    updateSliderTip($("prefLcdSize"), $("prefLcdSizeTip"), $("prefLcdSizeVal"));

    $("prefCallsign").value = state.prefs.callsign || "N0CALL";
    $("prefOperatorName").value = state.prefs.operatorName || "Radio Operator";
    $("prefDmrId").value = state.prefs.primaryDmrId || "";
    $("prefDefaultRadio").innerHTML =
      `<option value="">(None — Auto-Select)</option>` +
      state.radios
        .map(
          (r) =>
            `<option value="${escHtml(r.id)}" ${r.id === state.prefs.defaultRadioId ? "selected" : ""}>${escHtml(r.brand)} ${escHtml(r.model)} (${escHtml(r.id)})</option>`
        )
        .join("");
    $("prefNamingFormat").value = state.prefs.channelNamingFormat || "CITY_FREQ";
    $("prefDistanceUnit").value = state.prefs.distanceUnit || "MILES";
    $("prefCacheAge").value = String(state.prefs.repeaterMaxAgeDays || 30);
    $("prefWebPort").value = String(state.prefs.webPort || 8000);

    $("prefRbKey").value = "";
    $("prefRbKeyStatus").textContent = state.prefs.repeaterBookApiKeySet ? "Configured" : "Not Set";
    $("prefClearRbKey").checked = false;
    $("prefRadioIdUser").value = state.prefs.radioIdUsername || "";
    $("prefRadioIdKey").value = "";
    $("prefRadioIdKeyStatus").textContent = state.prefs.radioIdApiKeySet ? "Configured" : "Not Set";
    $("prefClearRadioIdKey").checked = false;
    $("prefQrzUser").value = state.prefs.qrzUsername || "";
    $("prefQrzPass").value = "";
    $("prefQrzStatus").textContent = state.prefs.qrzConfigured ? "Configured" : "Not Set";
    $("prefClearQrzPass").checked = false;
    $("qrzTestBanner").classList.add("hidden");
    $("updateVersionPill").textContent = `v${state.appVersion}`;
    $("updateModePill").textContent = state.installMode || "source";
    if ($("configDirPath")) {
      $("configDirPath").textContent = state.prefs.config_dir || state.configDir || "(default config folder)";
    }
    if ($("btnOpenConfigFolder")) {
      $("btnOpenConfigFolder").classList.toggle(
        "hidden",
        !(window.desktopApi && typeof window.desktopApi.openDataFolder === "function")
      );
    }

    $("cachedStatesCount").textContent = String(state.cachedStates.length);
    $("cachedStatesList").innerHTML = state.cachedStates.length
      ? state.cachedStates
          .map(
            (st) => `
          <div class="summary-row-item">
            <span class="mono"><strong>${escHtml(st.state)}</strong> — ${escHtml(st.filename)}</span>
            <span class="mono freq-rx">${st.count} rpt (${escHtml(st.date)})</span>
          </div>`
          )
          .join("")
      : `<div class="mgr-card-sub">No cached state files on disk yet.</div>`;

    setPrefTab(tab);
    $("prefsModalBackdrop").classList.remove("hidden");
  }

  function cancelPreferencesModal() {
    applyVisualPrefs(state.prefs);
    $("prefsModalBackdrop").classList.add("hidden");
  }

  // -------------------------------------------------------------------------
  // Ham-Suite Extensions: Callsign Lookup, NWS Weather, Net Logger, Backup & Updates
  // -------------------------------------------------------------------------
  async function lookupCallsign(callsign) {
    const clean = String(callsign || "").trim().toUpperCase();
    if (!clean) {
      toast("Enter a callsign first", "error");
      return null;
    }
    try {
      return await api(`/api/lookup/${encodeURIComponent(clean)}`);
    } catch (err) {
      toast(`Lookup failed: ${err.message}`, "error");
      return null;
    }
  }

  async function copyChannelNetLoggerPreset(slot) {
    try {
      const data = await api(`/api/codeplug/channels/${slot}/net-logger-preset`);
      const jsonText = JSON.stringify(data.preset, null, 2);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(jsonText);
        toast(`Copied Net Logger preset JSON for #${slot} (${data.preset.name})`, "success");
      } else {
        await downloadTextFile(`net_logger_preset_ch${slot}.json`, jsonText, "application/json;charset=utf-8");
        toast(`Saved Net Logger preset JSON for #${slot}`, "success");
      }
    } catch (err) {
      toast(`Net Logger preset export failed: ${err.message}`, "error");
    }
  }

  async function fetchNwsPlanAlerts() {
    const listEl = $("nwsAlertsList");
    $("nwsMetaLine").textContent = "Querying api.weather.gov...";
    listEl.innerHTML = `<div class="table-empty">Loading active National Weather Service alerts...</div>`;
    try {
      const data = await api("/api/nws/plan-alerts");
      state.nwsBriefingText = data.briefing_text || "";
      const states = data.states || [];
      $("nwsStatesPill").textContent = states.length ? states.join(", ") : "NONE";
      if (!data.online) {
        $("nwsMetaLine").textContent = data.error || "Offline / NWS unreachable";
        listEl.innerHTML = `<div class="notice-banner warning">${escHtml(data.error || "Could not reach api.weather.gov.")}</div>`;
        return;
      }
      $("nwsMetaLine").textContent = `${data.count || 0} active alert(s) • Updated ${data.fetched_at || ""}`;
      if (!data.alerts || !data.alerts.length) {
        listEl.innerHTML = `<div class="nws-all-clear">✔ ALL CLEAR — No active NWS watches, warnings, or advisories for ${escHtml(states.join(", ") || "this area")}.</div>`;
        return;
      }
      listEl.innerHTML = data.alerts
        .map((a) => {
          const sevCls = `nws-sev-${String(a.severity || "unknown").toLowerCase()}`;
          return `
            <article class="nws-alert-card ${escHtml(sevCls)}">
              <div class="plan-header-row">
                <span class="nws-alert-title">${escHtml(a.event)}</span>
                <span class="pill mono">${escHtml(a.severity)}</span>
              </div>
              ${a.headline ? `<div class="nws-alert-meta">${escHtml(a.headline)}</div>` : ""}
              ${a.area ? `<div class="nws-alert-meta"><strong>Areas:</strong> ${escHtml(a.area)}</div>` : ""}
              ${a.expires ? `<div class="nws-alert-meta mono">Expires: ${escHtml(a.expires)}</div>` : ""}
              ${a.description ? `<div class="nws-alert-body">${escHtml(a.description)}</div>` : ""}
            </article>`;
        })
        .join("");
    } catch (err) {
      $("nwsMetaLine").textContent = `Error: ${err.message}`;
      listEl.innerHTML = `<div class="notice-banner warning">${escHtml(err.message)}</div>`;
    }
  }

  function openNwsWeatherModal() {
    $("nwsAlertsBackdrop").classList.remove("hidden");
    fetchNwsPlanAlerts();
  }

  async function testQrzCredentials() {
    const banner = $("qrzTestBanner");
    banner.className = "qrz-test-banner";
    banner.textContent = "Testing QRZ XML login...";
    banner.classList.remove("hidden");
    try {
      const res = await api("/api/preferences/test-qrz", {
        method: "POST",
        body: JSON.stringify({
          qrzUsername: $("prefQrzUser").value.trim() || null,
          qrzPassword: $("prefQrzPass").value.trim() || null,
        }),
      });
      banner.className = `qrz-test-banner ${res.ok ? "ok" : "err"}`;
      banner.textContent = res.message || (res.ok ? "QRZ login OK" : "QRZ login failed");
    } catch (err) {
      banner.className = "qrz-test-banner err";
      banner.textContent = `QRZ test failed: ${err.message}`;
    }
  }

  async function downloadConfigBackup() {
    const includeTokens = $("chkBackupIncludeTokens").checked;
    try {
      const resp = await fetch(`/api/backup/export?include_tokens=${includeTokens ? "true" : "false"}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const cd = resp.headers.get("content-disposition") || "";
      const match = cd.match(/filename="([^"]+)"/);
      const fname = match ? match[1] : "radioplanner_backup.zip";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast(`Downloaded backup archive ${fname}`, "success");
    } catch (err) {
      toast(`Backup export failed: ${err.message}`, "error");
    }
  }

  async function restoreConfigBackup(file) {
    if (!file) return;
    if (!window.confirm(`Restore RadioPlanner configuration from "${file.name}"? A pre-restore snapshot will be saved automatically.`)) {
      return;
    }
    try {
      const buf = await file.arrayBuffer();
      const resp = await fetch("/api/backup/restore", {
        method: "POST",
        headers: { "Content-Type": "application/zip" },
        body: buf,
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.detail || `HTTP ${resp.status}`);
      if (body.preferences) applySavedPrefs(body.preferences);
      if (body.radios) state.radios = body.radios;
      if (body.templates) state.templates = body.templates;
      if (body.recipes) state.recipes = body.recipes;
      renderTemplatesPanel();
      renderRadiosPanel();
      renderRecipesList();
      toast(body.message || "Configuration restored", "success");
    } catch (err) {
      toast(`Backup restore failed: ${err.message}`, "error");
    }
  }

  function renderUpdateState(info) {
    state.updateInfo = info;
    if (!info) return;
    $("updateVersionPill").textContent = `v${info.current_version || state.appVersion}`;
    $("updateModePill").textContent = info.install_mode || state.installMode;
    $("updateStatusText").textContent = info.message || "Update status checked.";

    const link = $("updateReleaseLink");
    if (info.release_url) {
      link.href = info.release_url;
      link.classList.remove("hidden");
    } else {
      link.classList.add("hidden");
    }

    const notes = $("updateReleaseNotes");
    if (info.release_notes) {
      notes.textContent = info.release_notes;
      notes.classList.remove("hidden");
    } else {
      notes.classList.add("hidden");
    }

    const canInstall = Boolean(info.update_available && info.can_self_update);
    $("btnApplyUpdate").classList.toggle("hidden", !canInstall);
    const banner = $("btnUpdateBanner");
    if (info.update_available) {
      banner.textContent = `↑ v${info.latest_version} Available`;
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  }

  async function checkAppUpdates(quiet = false) {
    if (!quiet) $("updateStatusText").textContent = "Checking GitHub Releases...";
    try {
      const info = await api("/api/update/check");
      renderUpdateState(info);
      if (!quiet) toast(info.message || "Update check complete", info.update_available ? "success" : "info");
    } catch (err) {
      if (!quiet) {
        $("updateStatusText").textContent = `Update check failed: ${err.message}`;
        toast(`Update check failed: ${err.message}`, "error");
      }
    }
  }

  async function applyAppUpdate() {
    if (!window.confirm("Install the latest W5CDN RadioPlanner update now? A pre-update configuration backup will be saved first.")) {
      return;
    }
    $("btnApplyUpdate").disabled = true;
    $("updateStatusText").textContent = "Applying update & verifying integrity...";
    try {
      const res = await api("/api/update/apply", { method: "POST" });
      $("updateStatusText").textContent = res.message || "Update applied. Restarting...";
      toast(res.message || "Update applied", "success");
    } catch (err) {
      $("updateStatusText").textContent = `Update failed: ${err.message}`;
      toast(`Update failed: ${err.message}`, "error");
    } finally {
      $("btnApplyUpdate").disabled = false;
    }
  }

  // -------------------------------------------------------------------------
  // Modal Management & Keyboard Navigation Helpers
  // -------------------------------------------------------------------------
  const ALL_OVERLAY_IDS = [
    "panelsModalBackdrop",
    "prefsModalBackdrop",
    "editChannelBackdrop",
    "planReportBackdrop",
    "templateEditorBackdrop",
    "templateImportBackdrop",
    "radioEditorBackdrop",
    "saveRecipeBackdrop",
    "nwsAlertsBackdrop",
    "shortcutsBackdrop",
    "recipesDrawerBackdrop",
  ];

  function anyOverlayOpen() {
    return ALL_OVERLAY_IDS.some((id) => !$(id).classList.contains("hidden"));
  }

  function closeAllOverlays() {
    if (!$("prefsModalBackdrop").classList.contains("hidden")) {
      cancelPreferencesModal();
    }
    ALL_OVERLAY_IDS.forEach((id) => $(id).classList.add("hidden"));
    $("btnToggleRecipes").classList.remove("active");
  }

  function isTypingElement(el) {
    if (!el) return false;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
  }

  function moveRowSelection(delta) {
    const rows = getFilteredChannels();
    if (!rows.length) return;
    const idx = rows.findIndex((c) => c.number === state.selectedSlot);
    const nextIdx = idx === -1 ? (delta > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, idx + delta));
    state.selectedSlot = rows[nextIdx].number;
    renderChannelsTable();
    const tr = document.querySelector(`tr[data-slot="${state.selectedSlot}"]`);
    if (tr) tr.scrollIntoView({ block: "nearest" });
  }

  // -------------------------------------------------------------------------
  // Dock Resizers (Drag-to-Resize 5-Zone Stage)
  // -------------------------------------------------------------------------
  function initDockResizers() {
    const stage = $("cockpitStage");
    document.querySelectorAll("[data-resize-zone]").forEach((handle) => {
      const zone = handle.dataset.resizeZone;
      let dragging = false;

      handle.addEventListener("pointerdown", (e) => {
        dragging = true;
        handle.classList.add("dragging");
        handle.setPointerCapture(e.pointerId);
      });

      handle.addEventListener("pointermove", (e) => {
        if (!dragging) return;
        const rect = stage.getBoundingClientRect();
        const root = document.documentElement;
        if (zone === "left") {
          const w = Math.max(220, Math.min(rect.width - 320, e.clientX - rect.left - 8));
          root.style.setProperty("--dock-left-w", `${Math.round(w)}px`);
        } else if (zone === "right") {
          const w = Math.max(220, Math.min(rect.width - 320, rect.right - e.clientX - 8));
          root.style.setProperty("--dock-right-w", `${Math.round(w)}px`);
        } else if (zone === "top") {
          const h = Math.max(120, Math.min(rect.height - 200, e.clientY - rect.top - 8));
          root.style.setProperty("--dock-top-h", `${Math.round(h)}px`);
        } else if (zone === "bottom") {
          const h = Math.max(120, Math.min(rect.height - 200, rect.bottom - e.clientY - 8));
          root.style.setProperty("--dock-bottom-h", `${Math.round(h)}px`);
        }
      });

      const stop = () => {
        if (!dragging) return;
        dragging = false;
        handle.classList.remove("dragging");
        invalidateMapSoon();
      };
      handle.addEventListener("pointerup", stop);
      handle.addEventListener("pointercancel", stop);
    });
  }

  // -------------------------------------------------------------------------
  // Event Wiring
  // -------------------------------------------------------------------------
  function bindEvents() {
    // Topbar
    $("operatorCallBadge").addEventListener("click", () => openPreferencesModal("operator"));
    $("apiStatusPill").addEventListener("click", () => openPreferencesModal("api"));
    $("btnUpdateBanner").addEventListener("click", () => openPreferencesModal("system"));
    $("vfoCluster").addEventListener("click", () => $("targetRadioSelect").focus());
    $("btnTopAssemble").addEventListener("click", assemblePlan);
    $("btnOpenPanels").addEventListener("click", () => $("panelsModalBackdrop").classList.remove("hidden"));

    // Left Navigation Rail
    $("btnToggleRecipes").addEventListener("click", () => toggleRecipesDrawer());
    $("btnCloseRecipesDrawer").addEventListener("click", () => toggleRecipesDrawer(false));
    $("recipesDrawerBackdrop").addEventListener("click", (e) => {
      if (e.target === $("recipesDrawerBackdrop")) toggleRecipesDrawer(false);
    });
    $("btnNewPlan").addEventListener("click", () => {
      state.loadedRecipeFile = null;
      $("loadedRecipeBanner").classList.add("hidden");
      $("inPlanName").value = "";
      $("inPlanDesc").value = "";
      if (!state.prefs.panel_layout?.builder?.visible) togglePanel("builder", true);
      toast("Plan Builder reset for new plan");
    });
    $("btnToggleBuilder").addEventListener("click", () => togglePanel("builder"));
    $("btnToggleMap").addEventListener("click", () => togglePanel("map"));
    $("btnToggleSummary").addEventListener("click", () => togglePanel("summary"));
    $("btnToggleTemplates").addEventListener("click", () => togglePanel("templates"));
    $("btnToggleRadios").addEventListener("click", () => togglePanel("radios"));
    $("btnRailPanels").addEventListener("click", () => $("panelsModalBackdrop").classList.remove("hidden"));
    $("btnShortcuts").addEventListener("click", () => $("shortcutsBackdrop").classList.remove("hidden"));
    $("btnOpenPrefs").addEventListener("click", () => openPreferencesModal("appearance"));

    // Empty Workspace Quick-Start Presets
    document.querySelectorAll("[data-quick-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        setBuilderMode(btn.dataset.quickMode, false);
        if (!state.prefs.panel_layout?.builder?.visible) togglePanel("builder", true);
        assemblePlan();
      });
    });
    $("btnEmptyOpenRecipes").addEventListener("click", () => toggleRecipesDrawer(true));

    // Dock Panel 4-Way Move & Hide Buttons
    document.querySelectorAll("[data-panel-dock]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [key, pos] = btn.dataset.panelDock.split(":");
        movePanel(key, pos, true);
      });
    });
    document.querySelectorAll("[data-panel-hide]").forEach((btn) => {
      btn.addEventListener("click", () => togglePanel(btn.dataset.panelHide, false));
    });

    // Panels & Layout Modal
    document.querySelectorAll("[data-layout-preset]").forEach((btn) => {
      btn.addEventListener("click", () => applyLayoutPreset(btn.dataset.layoutPreset));
    });
    document.querySelectorAll("[data-panel-vis]").forEach((chk) => {
      chk.addEventListener("change", () => togglePanel(chk.dataset.panelVis, chk.checked));
    });
    document.querySelectorAll("[data-set-panel-pos]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [key, pos] = btn.dataset.setPanelPos.split(":");
        movePanel(key, pos, false);
      });
    });

    // Close Modal Buttons
    document.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", () => $(btn.dataset.closeModal).classList.add("hidden"));
    });

    // Builder Controls
    document.querySelectorAll("[data-builder-mode]").forEach((btn) => {
      btn.addEventListener("click", () => setBuilderMode(btn.dataset.builderMode, false));
    });
    $("btnResetBuilderDefaults").addEventListener("click", () => {
      state.loadedRecipeFile = null;
      $("loadedRecipeBanner").classList.add("hidden");
      state.waypoints = ["Tyler, TX", "Shreveport, LA", "Jackson, MS"];
      $("inCorridorWidth").value = "25";
      $("inCenterLocation").value = "Dallas, TX";
      $("inRadiusMiles").value = "50";
      $("inPlanName").value = "";
      $("inPlanDesc").value = "";
      state.sequenceOrder = defaultSequenceForMode(state.builderMode);
      renderWaypointsList();
      renderSequenceList();
    });
    $("btnAddWaypoint").addEventListener("click", () => {
      syncWaypointsFromDom();
      state.waypoints.push("");
      renderWaypointsList();
      const inputs = $("waypointsList").querySelectorAll("[data-wp-input]");
      if (inputs.length) inputs[inputs.length - 1].focus();
    });
    $("btnReverseWaypoints").addEventListener("click", () => {
      syncWaypointsFromDom();
      state.waypoints.reverse();
      renderWaypointsList();
    });
    $("waypointsList").addEventListener("click", (e) => {
      const rem = e.target.closest("[data-wp-remove]");
      if (!rem) return;
      syncWaypointsFromDom();
      if (state.waypoints.length <= 2) {
        toast("At least 2 waypoints are required for a route corridor", "error");
        return;
      }
      state.waypoints.splice(Number(rem.dataset.wpRemove), 1);
      renderWaypointsList();
    });
    bindDragSort($("waypointsList"), () => {
      syncWaypointsFromDom();
      renderWaypointsList();
    });

    $("btnInsertTemplateBlock").addEventListener("click", () => {
      const val = $("addTemplateSelect").value;
      if (!val || state.sequenceOrder.includes(val)) return;
      state.sequenceOrder.push(val);
      renderSequenceList();
    });
    $("sequenceList").addEventListener("click", (e) => {
      const rem = e.target.closest("[data-seq-remove]");
      if (!rem) return;
      state.sequenceOrder.splice(Number(rem.dataset.seqRemove), 1);
      renderSequenceList();
    });
    bindDragSort($("sequenceList"), () => {
      syncSequenceFromDom();
      renderSequenceList();
    });

    $("btnUseCurrentLocation").addEventListener("click", detectCurrentLocation);
    $("plannerForm").addEventListener("submit", (e) => {
      e.preventDefault();
      assemblePlan();
    });

    // Live Target Radio / Naming / Bands Controls
    $("targetRadioSelect").addEventListener("change", () => updateCodeplugTarget(true));
    $("targetNamingSelect").addEventListener("change", () => updateCodeplugTarget(false));
    $("targetBandsRow").addEventListener("change", () => updateCodeplugTarget(false));

    // Active Plan Actions
    $("btnPlanWeather").addEventListener("click", openNwsWeatherModal);
    $("btnPlanExpandDmr").addEventListener("click", expandDmrTalkgroups);
    $("btnPlanReport").addEventListener("click", openPlanReportModal);
    $("btnPlanExportCsv").addEventListener("click", exportActiveCsv);
    const openSaveRecipeModal = () => {
      if (!state.activePlan) {
        toast("Assemble a plan before saving a recipe", "error");
        return;
      }
      $("saveRecName").value = state.activePlan.recipe.name || "Saved_Plan";
      $("saveRecDesc").value = state.activePlan.recipe.description || "";
      $("saveRecipeBackdrop").classList.remove("hidden");
      $("saveRecName").focus();
    };
    $("btnPlanSaveRecipe").addEventListener("click", openSaveRecipeModal);
    $("btnDrawerSaveRecipe").addEventListener("click", openSaveRecipeModal);
    $("saveRecipeForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api("/api/recipes/save", {
          method: "POST",
          body: JSON.stringify({
            name: $("saveRecName").value.trim(),
            description: $("saveRecDesc").value.trim(),
          }),
        });
        state.recipes = res.recipes || state.recipes;
        renderRecipesList();
        $("saveRecipeBackdrop").classList.add("hidden");
        toast(res.message || "Recipe saved", "success");
      } catch (err) {
        toast(`Recipe save failed: ${err.message}`, "error");
      }
    });

    // Filter Toolbar, Band KPIs, Multi-Select Delete & Undo
    $("bandKpiStrip").addEventListener("click", (e) => {
      const chip = e.target.closest("[data-kpi-band]");
      if (!chip) return;
      state.bandFilter = chip.dataset.kpiBand;
      renderBandKpiStrip();
      renderChannelsTable();
    });
    document.querySelectorAll("[data-ch-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.channelFilter = btn.dataset.chFilter;
        renderChannelsTable();
      });
    });
    $("searchChannels").addEventListener("input", () => {
      state.searchQuery = $("searchChannels").value;
      renderChannelsTable();
    });
    $("selectAllChannels").addEventListener("change", (e) => {
      const rows = getFilteredChannels();
      if (e.target.checked) rows.forEach((ch) => state.checkedSlots.add(ch.number));
      else rows.forEach((ch) => state.checkedSlots.delete(ch.number));
      renderChannelsTable();
    });
    $("btnDeleteSelected").addEventListener("click", () => deleteSlots(Array.from(state.checkedSlots)));
    $("btnUndoDelete").addEventListener("click", undoLastChannelChange);

    // Channel Table Interactions (Shift+Click Multi-Select, Row Selection, Edit, Locate, Delete)
    $("channelsTbody").addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-slot]");
      if (!tr) return;
      const slot = Number(tr.dataset.slot);

      const chk = e.target.closest("[data-chk-slot]");
      if (chk) {
        const rows = getFilteredChannels();
        if (e.shiftKey && state.lastCheckedSlot !== null && state.lastCheckedSlot !== slot) {
          const i1 = rows.findIndex((c) => c.number === state.lastCheckedSlot);
          const i2 = rows.findIndex((c) => c.number === slot);
          if (i1 !== -1 && i2 !== -1) {
            const [lo, hi] = [Math.min(i1, i2), Math.max(i1, i2)];
            for (let i = lo; i <= hi; i += 1) {
              if (chk.checked) state.checkedSlots.add(rows[i].number);
              else state.checkedSlots.delete(rows[i].number);
            }
          }
        } else {
          if (chk.checked) state.checkedSlots.add(slot);
          else state.checkedSlots.delete(slot);
        }
        state.lastCheckedSlot = slot;
        renderChannelsTable();
        return;
      }

      const act = e.target.closest("[data-row-action]");
      state.selectedSlot = slot;
      if (act) {
        const action = act.dataset.rowAction;
        if (action === "edit") openEditChannelModal(slot);
        else if (action === "net-logger") copyChannelNetLoggerPreset(slot);
        else if (action === "locate") locateSlotOnMap(slot);
        else if (action === "delete") deleteSlots([slot]);
        return;
      }
      renderChannelsTable();
    });

    $("channelsTbody").addEventListener("dblclick", (e) => {
      const tr = e.target.closest("tr[data-slot]");
      if (tr && !e.target.closest("button, input")) {
        openEditChannelModal(Number(tr.dataset.slot));
      }
    });

    // Inline Channel Editor Form
    $("editChName").addEventListener("input", updateEditChannelNameCounter);
    $("editChOffsetDir").addEventListener("change", syncEditChannelControls);
    $("editChToneMode").addEventListener("change", syncEditChannelControls);
    $("btnEditLookupCall").addEventListener("click", async () => {
      const res = await lookupCallsign($("editChCallsign").value);
      if (res && res.found) {
        if (res.city && !$("editChCity").value.trim()) $("editChCity").value = res.city;
        if (res.state && !$("editChState").value.trim()) $("editChState").value = res.state;
        const note = `${res.name}${res.grid ? ` [${res.grid}]` : ""}`.trim();
        if (note && !$("editChComment").value.trim()) $("editChComment").value = note;
        toast(`Found ${res.callsign}: ${res.name} (${res.qth || res.source})`, "success");
      } else if (res) {
        toast(res.error || `Callsign ${res.callsign || ""} not found`, "error");
      }
    });
    $("editChannelForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const slot = Number($("editChSlot").value);
      const toneMode = $("editChToneMode").value;
      const toneVal = $("editChToneVal").value.trim();
      try {
        const updated = await api(`/api/codeplug/channels/${slot}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: $("editChName").value.trim(),
            callsign: $("editChCallsign").value.trim().toUpperCase(),
            rxFreq: Number($("editChRx").value),
            offsetDir: $("editChOffsetDir").value,
            offset: Number($("editChOffset").value || 0),
            mode: $("editChMode").value,
            power: $("editChPower").value,
            toneMode,
            ctcss: toneMode === "Tone" || toneMode === "TSQL" ? toneVal : "None",
            dcs: toneMode === "DCS" ? toneVal : "None",
            city: $("editChCity").value.trim(),
            state: $("editChState").value.trim().toUpperCase(),
            comment: $("editChComment").value.trim(),
          }),
        });
        $("editChannelBackdrop").classList.add("hidden");
        renderActivePlan(updated);
        toast(updated.message || `Updated slot #${slot}`, "success");
      } catch (err) {
        toast(`Channel update failed: ${err.message}`, "error");
      }
    });

    // Pocket Reference Card / Plan Report Modal Actions
    $("btnReportRefresh").addEventListener("click", openPlanReportModal);
    $("btnReportCopy").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText($("planReportText").value);
        toast("Pocket reference card copied to clipboard", "success");
      } catch {
        toast("Could not access clipboard", "error");
      }
    });
    $("btnReportSaveTxt").addEventListener("click", () => {
      const fname = state.activeReport?.filename || "codeplug_pocket_card.txt";
      downloadTextFile(fname, $("planReportText").value, "text/plain;charset=utf-8");
      toast(`Saved ${fname}`, "success");
    });
    $("btnReportPrint").addEventListener("click", () => window.print());

    // Saved Recipes Drawer Actions
    $("recipesSearch").addEventListener("input", renderRecipesList);
    $("btnUploadRecipe").addEventListener("click", () => $("recipeUploadFile").click());
    $("recipeUploadFile").addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      try {
        const yamlText = await file.text();
        const res = await api("/api/recipes/upload", {
          method: "POST",
          body: JSON.stringify({ filename: file.name, yaml_text: yamlText }),
        });
        state.recipes = res.recipes || state.recipes;
        renderRecipesList();
        applyRecipeToBuilder(res.filename, res.recipe);
      } catch (err) {
        toast(`Recipe upload failed: ${err.message}`, "error");
      }
    });
    $("recipesList").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-recipe-action]");
      if (!btn) return;
      const card = btn.closest("[data-recipe-file]");
      const filename = card.dataset.recipeFile;
      if (btn.dataset.recipeAction === "load") {
        try {
          const res = await api(`/api/recipes/${encodeURIComponent(filename)}`);
          applyRecipeToBuilder(res.filename, res.recipe);
        } catch (err) {
          toast(`Load failed: ${err.message}`, "error");
        }
      } else if (btn.dataset.recipeAction === "export") {
        try {
          const resp = await fetch(`/api/recipes/${encodeURIComponent(filename)}/export`);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const yamlText = await resp.text();
          const ok = await downloadTextFile(filename, yamlText, "application/x-yaml;charset=utf-8");
          if (ok) toast(`Exported recipe YAML: ${filename}`, "success");
        } catch (err) {
          toast(`Recipe YAML export failed: ${err.message}`, "error");
        }
      } else if (btn.dataset.recipeAction === "delete") {
        if (!window.confirm(`Delete saved recipe ${filename}?`)) return;
        try {
          const res = await api(`/api/recipes/${encodeURIComponent(filename)}`, { method: "DELETE" });
          state.recipes = res.recipes || [];
          renderRecipesList();
          toast(`Deleted ${filename}`, "success");
        } catch (err) {
          toast(`Delete failed: ${err.message}`, "error");
        }
      }
    });

    // Templates Panel & Spreadsheet Editor
    $("templatesSearch").addEventListener("input", renderTemplatesPanel);
    $("btnNewTemplate").addEventListener("click", () => openTemplateEditorModal(null));
    $("btnImportTemplate").addEventListener("click", () => {
      $("tplImpId").value = "";
      $("tplImpName").value = "";
      $("tplImpTag").value = "CUSTOM";
      $("tplImpFile").value = "";
      $("templateImportBackdrop").classList.remove("hidden");
    });
    $("templatesList").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-tpl-action]");
      if (!btn) return;
      const card = btn.closest("[data-tpl-id]");
      const tplId = card.dataset.tplId;
      const tpl = state.templates.find((t) => t.id === tplId);
      if (!tpl) return;
      const action = btn.dataset.tplAction;
      if (action === "edit") openTemplateEditorModal(tpl);
      else if (action === "export") {
        try {
          const resp = await fetch(`/api/templates/${encodeURIComponent(tpl.id)}/export`);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const yamlText = await resp.text();
          const ok = await downloadTextFile(`${tpl.id}.yaml`, yamlText, "application/x-yaml;charset=utf-8");
          if (ok) toast(`Exported template YAML: ${tpl.id}.yaml`, "success");
        } catch (err) {
          toast(`Template YAML export failed: ${err.message}`, "error");
        }
      } else if (action === "insert") {
        const key = `TEMPLATE:${tpl.id}`;
        if (!state.sequenceOrder.includes(key)) {
          state.sequenceOrder.push(key);
          renderSequenceList();
          toast(`Inserted '${tpl.name}' into Plan Sequence`, "success");
        }
      } else if (action === "delete") {
        if (!window.confirm(`Delete custom template '${tpl.name}'?`)) return;
        try {
          const res = await api(`/api/templates/${encodeURIComponent(tpl.id)}`, { method: "DELETE" });
          state.templates = res.templates || [];
          renderTemplatesPanel();
          toast(`Deleted template ${tpl.id}`, "success");
        } catch (err) {
          toast(`Delete failed: ${err.message}`, "error");
        }
      }
    });

    $("btnTplAddRow").addEventListener("click", () => {
      const idx = $("tplEditorTbody").querySelectorAll("tr.tpl-sheet-row").length + 1;
      $("tplEditorTbody").insertAdjacentHTML("beforeend", createTplSheetRowHtml({ name: `CH ${idx}` }));
    });
    $("tplEditorTbody").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-tpl-row]");
      if (!btn) return;
      const tr = btn.closest("tr.tpl-sheet-row");
      const tbody = $("tplEditorTbody");
      const act = btn.dataset.tplRow;
      if (act === "del") tr.remove();
      else if (act === "up" && tr.previousElementSibling) tbody.insertBefore(tr, tr.previousElementSibling);
      else if (act === "down" && tr.nextElementSibling) tbody.insertBefore(tr.nextElementSibling, tr);
    });
    $("tplEditorTbody").addEventListener("change", (e) => {
      const el = e.target;
      const tr = el.closest("tr.tpl-sheet-row");
      if (!tr) return;
      if (el.dataset.f === "offsetDir") {
        const off = tr.querySelector('[data-f="offset"]');
        if (el.value === "off") {
          off.value = "0.000";
          off.readOnly = true;
        } else {
          off.readOnly = false;
          if (Number(off.value || 0) === 0) {
            const rx = Number(tr.querySelector('[data-f="rxFreq"]').value || 146.52);
            off.value = rx >= 420 && rx <= 470 ? "5.000" : "0.600";
          }
        }
      } else if (el.dataset.f === "toneMode") {
        const tv = tr.querySelector('[data-f="toneVal"]');
        if (el.value === "None") {
          tv.value = "None";
          tv.readOnly = true;
        } else {
          tv.readOnly = false;
          if (!tv.value || tv.value === "None") tv.value = el.value === "DCS" ? "023" : "100.0";
        }
      }
    });
    $("templateEditorForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const rows = Array.from($("tplEditorTbody").querySelectorAll("tr.tpl-sheet-row")).map((tr) => ({
        name: tr.querySelector('[data-f="name"]').value.trim(),
        rxFreq: Number(tr.querySelector('[data-f="rxFreq"]').value),
        offsetDir: tr.querySelector('[data-f="offsetDir"]').value,
        offset: Number(tr.querySelector('[data-f="offset"]').value || 0),
        mode: tr.querySelector('[data-f="mode"]').value,
        power: tr.querySelector('[data-f="power"]').value,
        toneMode: tr.querySelector('[data-f="toneMode"]').value,
        toneVal: tr.querySelector('[data-f="toneVal"]').value.trim() || "None",
        comment: tr.querySelector('[data-f="comment"]').value.trim(),
      }));
      try {
        const res = await api("/api/templates", {
          method: "POST",
          body: JSON.stringify({
            id: $("tplEditId").value.trim(),
            name: $("tplEditName").value.trim(),
            tagText: $("tplEditTag").value.trim().toUpperCase(),
            tagColorHex: $("tplEditColor").value,
            description: $("tplEditDesc").value.trim(),
            channels: rows,
          }),
        });
        state.templates = res.templates || [];
        renderTemplatesPanel();
        renderSequenceList();
        $("templateEditorBackdrop").classList.add("hidden");
        toast(res.message || "Template saved", "success");
      } catch (err) {
        toast(`Template save failed: ${err.message}`, "error");
      }
    });

    $("templateImportForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const file = $("tplImpFile").files?.[0];
      if (!file) return;
      try {
        const content = await file.text();
        const res = await api("/api/templates/import", {
          method: "POST",
          body: JSON.stringify({
            id: $("tplImpId").value.trim(),
            name: $("tplImpName").value.trim(),
            tagText: $("tplImpTag").value.trim().toUpperCase(),
            filename: file.name,
            content,
          }),
        });
        state.templates = res.templates || [];
        renderTemplatesPanel();
        $("templateImportBackdrop").classList.add("hidden");
        toast(res.message || "Template imported", "success");
      } catch (err) {
        toast(`Import failed: ${err.message}`, "error");
      }
    });

    // Radios Panel & Editor Modal
    $("radiosSearch").addEventListener("input", renderRadiosPanel);
    $("btnNewRadio").addEventListener("click", () => openRadioEditorModal(null));
    $("btnImportRadioYaml")?.addEventListener("click", () => $("radioImportYamlFile")?.click());
    $("radioImportYamlFile")?.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      try {
        const yamlText = await file.text();
        const res = await api("/api/radios/import", {
          method: "POST",
          body: JSON.stringify({ filename: file.name, yaml_text: yamlText }),
        });
        state.radios = res.radios || [];
        renderRadiosPanel();
        toast(res.message || `Imported radio profile from ${file.name}`, "success");
      } catch (err) {
        toast(`Radio YAML validation failed: ${err.message}`, "error");
      }
    });
    $("radiosList").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-radio-action]");
      if (!btn) return;
      const card = btn.closest("[data-radio-id]");
      const spec = state.radios.find((r) => r.id === card.dataset.radioId);
      if (!spec) return;
      const action = btn.dataset.radioAction;
      if (action === "edit") openRadioEditorModal(spec);
      else if (action === "export") {
        try {
          const resp = await fetch(`/api/radios/${encodeURIComponent(spec.id)}/export`);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const yamlText = await resp.text();
          const ok = await downloadTextFile(`${spec.id}.yaml`, yamlText, "application/x-yaml;charset=utf-8");
          if (ok) toast(`Exported radio profile YAML: ${spec.id}.yaml`, "success");
        } catch (err) {
          toast(`Radio YAML export failed: ${err.message}`, "error");
        }
      } else if (action === "target" && state.activePlan) {
        $("targetRadioSelect").value = spec.id;
        updateCodeplugTarget(true);
      } else if (action === "delete") {
        if (!window.confirm(`Delete custom radio '${spec.brand} ${spec.model}'?`)) return;
        try {
          const res = await api(`/api/radios/${encodeURIComponent(spec.id)}`, { method: "DELETE" });
          state.radios = res.radios || [];
          renderRadiosPanel();
          toast(`Deleted radio ${spec.id}`, "success");
        } catch (err) {
          toast(`Delete failed: ${err.message}`, "error");
        }
      }
    });
    $("radioEditorForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api("/api/radios", {
          method: "POST",
          body: JSON.stringify({
            id: $("radId").value.trim(),
            brand: $("radBrand").value.trim(),
            model: $("radModel").value.trim(),
            description: $("radDesc").value.trim(),
            startChannel: Number($("radStart").value),
            maxChannels: Number($("radMaxCh").value),
            maxNameLength: Number($("radMaxName").value),
            programmerType: $("radProg").value,
            supportedBands: $("radBands").value.split(",").map((s) => s.trim()).filter(Boolean),
            supportedModes: $("radModes").value.split(",").map((s) => s.trim()).filter(Boolean),
            allowDots: $("radAllowDots").checked,
            allowSpaces: $("radAllowSpaces").checked,
          }),
        });
        state.radios = res.radios || [];
        renderRadiosPanel();
        $("radioEditorBackdrop").classList.add("hidden");
        toast(res.message || "Radio saved", "success");
      } catch (err) {
        toast(`Radio save failed: ${err.message}`, "error");
      }
    });

    // Preferences Modal
    document.querySelectorAll("[data-pref-tab]").forEach((btn) => {
      btn.addEventListener("click", () => setPrefTab(btn.dataset.prefTab));
    });
    document.querySelectorAll("[data-theme-pick]").forEach((card) => {
      card.addEventListener("click", () => {
        state.draftTheme = card.dataset.themePick;
        document.querySelectorAll("[data-theme-pick]").forEach((c) => {
          c.classList.toggle("active", c.dataset.themePick === state.draftTheme);
        });
        previewDraftVisuals();
      });
    });
    $("prefUiFont").addEventListener("change", previewDraftVisuals);
    $("prefMonoFont").addEventListener("change", previewDraftVisuals);
    $("prefFontSize").addEventListener("input", () => {
      updateSliderTip($("prefFontSize"), $("prefFontSizeTip"), $("prefFontSizeVal"));
      previewDraftVisuals();
    });
    $("prefLcdSize").addEventListener("input", () => {
      updateSliderTip($("prefLcdSize"), $("prefLcdSizeTip"), $("prefLcdSizeVal"));
      previewDraftVisuals();
    });
    document.querySelectorAll("[data-toggle-secret]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = $(btn.dataset.toggleSecret);
        if (!input) return;
        const showing = input.type === "text";
        input.type = showing ? "password" : "text";
        btn.textContent = showing ? "Show" : "Hide";
        btn.setAttribute("aria-pressed", showing ? "false" : "true");
      });
    });
    $("btnCancelPrefs").addEventListener("click", cancelPreferencesModal);
    $("btnCancelPrefsTop").addEventListener("click", cancelPreferencesModal);
    $("prefsForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api("/api/preferences", {
          method: "PUT",
          body: JSON.stringify({
            colorTheme: state.draftTheme,
            fontFamily: $("prefUiFont").value,
            monoFont: $("prefMonoFont").value,
            uiFontSize: Number($("prefFontSize").value),
            lcdFontSize: Number($("prefLcdSize").value),
            callsign: $("prefCallsign").value.trim(),
            operatorName: $("prefOperatorName").value.trim(),
            primaryDmrId: $("prefDmrId").value.trim(),
            defaultRadioId: $("prefDefaultRadio").value,
            channelNamingFormat: $("prefNamingFormat").value,
            distanceUnit: $("prefDistanceUnit").value,
            repeaterMaxAgeDays: Number($("prefCacheAge").value) || 30,
            webPort: Number($("prefWebPort").value) || 8000,
            repeaterBookApiKey: $("prefRbKey").value.trim() || null,
            clearRepeaterBookApiKey: $("prefClearRbKey").checked,
            radioIdUsername: $("prefRadioIdUser").value.trim(),
            radioIdApiKey: $("prefRadioIdKey").value.trim() || null,
            clearRadioIdApiKey: $("prefClearRadioIdKey").checked,
            qrzUsername: $("prefQrzUser").value.trim(),
            qrzPassword: $("prefQrzPass").value.trim() || null,
            clearQrzPassword: $("prefClearQrzPass").checked,
          }),
        });
        applySavedPrefs(res.preferences);
        state.cachedStates = res.cached_states || [];
        $("prefsModalBackdrop").classList.add("hidden");
        toast("Preferences saved", "success");
      } catch (err) {
        toast(`Failed to save preferences: ${err.message}`, "error");
      }
    });

    // Callsign Lookup, QRZ Test, NWS Weather, Backup & Updates Buttons
    $("btnPrefLookupCall").addEventListener("click", async () => {
      const res = await lookupCallsign($("prefCallsign").value);
      if (res && res.found) {
        if (res.callsign) $("prefCallsign").value = res.callsign;
        if (res.name) $("prefOperatorName").value = res.name;
        toast(`Found ${res.callsign}: ${res.name} (${res.source.toUpperCase()})`, "success");
      } else if (res) {
        toast(res.error || `Callsign not found`, "error");
      }
    });
    $("btnTestQrz").addEventListener("click", testQrzCredentials);
    $("btnDownloadBackup").addEventListener("click", downloadConfigBackup);
    $("btnOpenConfigFolder")?.addEventListener("click", async () => {
      if (window.desktopApi && typeof window.desktopApi.openDataFolder === "function") {
        const res = await window.desktopApi.openDataFolder();
        if (res && res.ok) toast(`Opened config folder: ${res.path || ""}`, "info");
        else toast(`Could not open config folder: ${res?.error || "unknown error"}`, "error");
      }
    });
    $("btnReloadConfigs")?.addEventListener("click", async () => {
      try {
        const res = await api("/api/workspace/reload", { method: "POST" });
        if (res.preferences) applySavedPrefs(res.preferences);
        if (res.radios) state.radios = res.radios;
        if (res.templates) state.templates = res.templates;
        if (res.recipes) state.recipes = res.recipes;
        renderTemplatesPanel();
        renderRadiosPanel();
        renderRecipesList();
        toast("Reloaded radios, templates, recipes & preferences from disk", "success");
      } catch (err) {
        toast(`Reload failed: ${err.message}`, "error");
      }
    });
    $("btnRestoreBackup").addEventListener("click", () => $("restoreBackupFile").click());
    $("restoreBackupFile").addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (file) await restoreConfigBackup(file);
    });
    $("btnCheckUpdate").addEventListener("click", () => checkAppUpdates(false));
    $("btnApplyUpdate").addEventListener("click", applyAppUpdate);
    $("btnNwsRefresh").addEventListener("click", fetchNwsPlanAlerts);
    $("btnNwsCopy").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(state.nwsBriefingText || "");
        toast("NWS weather briefing copied to clipboard", "success");
      } catch {
        toast("Could not access clipboard", "error");
      }
    });

    // Notify local desktop/browser server when tab closes
    window.addEventListener("pagehide", () => {
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/api/client/unload");
      }
    });

    // Backdrop click-to-close on non-form info modals
    ["panelsModalBackdrop", "planReportBackdrop", "nwsAlertsBackdrop", "shortcutsBackdrop"].forEach((id) => {
      $(id).addEventListener("click", (e) => {
        if (e.target === $(id)) $(id).classList.add("hidden");
      });
    });

    // Global Keyboard Shortcuts
    document.addEventListener("keydown", (e) => {
      const key = e.key;
      const lower = key.toLowerCase();

      if (key === "Escape") {
        if (anyOverlayOpen()) {
          closeAllOverlays();
        }
        return;
      }

      if ((e.ctrlKey || e.metaKey) && key === "Enter" && !anyOverlayOpen()) {
        e.preventDefault();
        assemblePlan();
        return;
      }

      if ((e.ctrlKey || e.metaKey) && lower === "z" && !isTypingElement(document.activeElement) && !anyOverlayOpen()) {
        if (state.activePlan?.can_undo) {
          e.preventDefault();
          undoLastChannelChange();
        }
        return;
      }

      if (key === "F1") {
        e.preventDefault();
        $("shortcutsBackdrop").classList.toggle("hidden");
        return;
      }

      if (e.altKey) {
        if (lower === "s") { e.preventDefault(); toggleRecipesDrawer(); return; }
        if (lower === "b") { e.preventDefault(); togglePanel("builder"); return; }
        if (lower === "m") { e.preventDefault(); togglePanel("map"); return; }
        if (lower === "u") { e.preventDefault(); togglePanel("summary"); return; }
        if (lower === "t") { e.preventDefault(); togglePanel("templates"); return; }
        if (lower === "r") { e.preventDefault(); togglePanel("radios"); return; }
        if (lower === "l") { e.preventDefault(); $("panelsModalBackdrop").classList.toggle("hidden"); return; }
        if (lower === "n") { e.preventDefault(); $("btnNewPlan").click(); return; }
        if (key === ",") {
          e.preventDefault();
          if ($("prefsModalBackdrop").classList.contains("hidden")) openPreferencesModal("appearance");
          else cancelPreferencesModal();
          return;
        }
        if (lower === "f") {
          e.preventDefault();
          $("searchChannels").focus();
          $("searchChannels").select();
          return;
        }
      }

      if (anyOverlayOpen() || isTypingElement(document.activeElement)) return;

      if (key === "?") {
        e.preventDefault();
        $("shortcutsBackdrop").classList.remove("hidden");
        return;
      }
      if (key === "ArrowDown") { e.preventDefault(); moveRowSelection(1); return; }
      if (key === "ArrowUp") { e.preventDefault(); moveRowSelection(-1); return; }
      if (state.selectedSlot !== null && state.activePlan) {
        if (lower === "e") { e.preventDefault(); openEditChannelModal(state.selectedSlot); }
        else if (lower === "l") { e.preventDefault(); locateSlotOnMap(state.selectedSlot); }
        else if (key === "Delete") { e.preventDefault(); deleteSlots([state.selectedSlot]); }
      }
    });
  }

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------
  async function boot() {
    bindEvents();
    initDockResizers();
    updateClocks();
    setInterval(updateClocks, 1000);
    renderWaypointsList();

    try {
      const cfg = await api("/api/config");
      state.appVersion = cfg.version || "0.2.0";
      state.installMode = cfg.install_mode || "source";
      state.configDir = cfg.config_dir || "";
      if ($("rpVersionPill")) $("rpVersionPill").textContent = `v${state.appVersion}`;
      state.radios = cfg.radios || [];
      state.templates = cfg.templates || [];
      state.cachedStates = cfg.cached_states || [];
      $("railRecipeBadge").textContent = String(cfg.recipes_count || 0);
      if (cfg.preferences) applySavedPrefs(cfg.preferences);
      renderTemplatesPanel();
      renderRadiosPanel();
      setBuilderMode("ROUTE_CORRIDOR", true);
      if (cfg.active_plan && cfg.active_plan.active) {
        renderActivePlan(cfg.active_plan);
      } else {
        ensureLeafletMap();
      }
      checkAppUpdates(true);
    } catch (err) {
      toast(`Startup error: ${err.message}`, "error");
    }
  }

  boot();
})();
