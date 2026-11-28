/**
 * In-Process API Router for W5CDN RadioPlanner.
 * Implements 100% parity with all 33 original REST endpoints PLUS hand-editable YAML export/import
 * endpoints with strict line/column & field-level schema validation.
 */

import fs from "node:fs";
import path from "node:path";
import {
  channelBand,
  channelIsSimplex,
  cleanSingleLine,
  safeChildPath,
  sanitizeFilename,
  sanitizeHttpUrl,
  sanitizeSlug,
  utcNowIso,
} from "../shared/sanitize";
import {
  AVIATION_NAMING_FORMAT_OPTIONS,
  ApiError,
  BAND_COLORS,
  NAMING_FORMAT_OPTIONS,
  PresetTemplateFile,
  RING_COLORS,
  RadioChannel,
  RadioPlannerRecipe,
  TargetRadioSpec,
  TemplateChannelItem,
  resolveCockpitTheme,
  resolveUiFont,
  sanitizePanelLayout,
} from "../shared/types";
import { YamlDiagnosticError, parseYamlText, validateTemplateFile } from "../shared/yamlDiagnostics";
import { createConfigBackupZipBytes, restoreConfigBackupZipBytes } from "./backup";
import { NameCondenser } from "./condenser";
import { AviationEngine } from "./engines/aviation";
import { ProximityEngine } from "./engines/proximity";
import { RouteCorridorEngine } from "./engines/routeCorridor";
import { SequenceOrganizer } from "./engines/sequence";
import { exportCodeplugCsv } from "./exporters";
import { getExportsDir } from "./paths";
import { CallsignLookupService } from "./providers/callsignLookup";
import { haversineMiles } from "./providers/geocoding";
import { RadioIdProvider } from "./providers/radioId";
import {
  getOfflineWxStations,
  identifyStatesForProximity,
  identifyStatesForRoute,
} from "./providers/repeaterbook";
import { CodeplugState, WebWorkspace, channelDeleteKey } from "./workspace";

export interface RouterRequest {
  method: string;
  pathname: string;
  query: URLSearchParams;
  bodyText?: string;
  bodyBuffer?: Buffer;
}

export interface RouterResponse {
  status: number;
  headers: Record<string, string>;
  body: string | Buffer;
}

const APP_TITLE = "W5CDN RadioPlanner";

function readAppVersion(): string {
  try {
    const pkgCandidates = [
      path.resolve(__dirname, "..", "..", "package.json"),
      path.resolve(__dirname, "..", "..", "..", "package.json"),
      path.resolve(process.cwd(), "package.json"),
    ];
    for (const p of pkgCandidates) {
      if (fs.existsSync(p)) {
        const parsed = JSON.parse(fs.readFileSync(p, "utf-8")) as { version?: string };
        if (parsed.version) return parsed.version;
      }
    }
  } catch {
    // fallback
  }
  return "0.2.0";
}

function jsonResponse(data: unknown, status = 200): RouterResponse {
  return {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(data),
  };
}

function textDownloadResponse(content: string, contentType: string, filename: string): RouterResponse {
  const safeName = sanitizeFilename(filename, "export.txt");
  return {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": `attachment; filename="${safeName}"`,
    },
    body: content,
  };
}

function parseJsonBody(bodyText?: string): Record<string, unknown> {
  if (!bodyText || !bodyText.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(bodyText);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return {};
  } catch {
    throw new ApiError(400, "Invalid JSON request body.");
  }
}

function computeBandCountsAndMapChannels(
  channels: RadioChannel[],
  activeBands: string[],
  extraWxStations: RadioChannel[] = [],
): { bandCounts: Record<string, number>; mapChannels: Array<Record<string, unknown>> } {
  const counts: Record<string, number> = {};
  for (const b of activeBands) counts[b] = 0;

  const mapChannels: Array<Record<string, unknown>> = [];
  const mappedCoordKeys = new Set<string>();
  const wxChannelByFreq = new Map<string, RadioChannel>();

  for (const ch of channels) {
    const band = channelBand(ch.rxFreq);
    counts[band] = (counts[band] ?? 0) + 1;
    if (band === "WX" && !wxChannelByFreq.has(ch.rxFreq.toFixed(3))) {
      wxChannelByFreq.set(ch.rxFreq.toFixed(3), ch);
    }
    if (ch.lat !== null && ch.lon !== null) {
      const toneLbl =
        ch.toneMode === "Tone" || ch.toneMode === "TSQL"
          ? ch.ctcss
          : ch.toneMode === "DCS" || ch.toneMode === "DTCS"
            ? `D${ch.dcs}`
            : "CSQ";
      const coordKey = `${ch.rxFreq.toFixed(3)}|${ch.lat.toFixed(3)}|${ch.lon.toFixed(3)}`;
      mappedCoordKeys.add(coordKey);
      mapChannels.push({
        number: ch.number,
        name: ch.name,
        callsign: ch.callsign || "",
        rxFreq: ch.rxFreq,
        mode: ch.mode,
        band,
        color: BAND_COLORS[band] ?? "#10b981",
        tone: toneLbl,
        location: [ch.city, ch.state].filter(Boolean).join(", "),
        lat: ch.lat,
        lon: ch.lon,
      });
    }
  }

  // Also include nearby/corridor NOAA WX transmitter sites on the map when WX band/channels are active
  const wxActive =
    (counts.WX ?? 0) > 0 || activeBands.some((b) => b.toUpperCase() === "WX");
  if (wxActive && extraWxStations.length > 0) {
    for (const wx of extraWxStations) {
      if (wx.lat === null || wx.lon === null) continue;
      const coordKey = `${wx.rxFreq.toFixed(3)}|${wx.lat.toFixed(3)}|${wx.lon.toFixed(3)}`;
      if (mappedCoordKeys.has(coordKey)) continue;
      mappedCoordKeys.add(coordKey);
      const matchedSlot = wxChannelByFreq.get(wx.rxFreq.toFixed(3));
      mapChannels.push({
        number: matchedSlot ? matchedSlot.number : wx.number,
        name: matchedSlot ? `${matchedSlot.name} (${wx.city || wx.callsign || "NWR"})` : wx.name,
        callsign: wx.callsign || matchedSlot?.callsign || "NWR",
        rxFreq: wx.rxFreq,
        mode: wx.mode || "FM",
        band: "WX",
        color: BAND_COLORS.WX ?? "#38bdf8",
        tone: "CSQ",
        location: [wx.city, wx.state].filter(Boolean).join(", "),
        lat: wx.lat,
        lon: wx.lon,
      });
    }
  }

  return { bandCounts: counts, mapChannels };
}

function buildNamingPreviews(spec: TargetRadioSpec, mode = "ROUTE_CORRIDOR"): Array<Record<string, string>> {
  if (mode.toUpperCase() === "AVIATION_PLANNER") {
    const sampleAir: RadioChannel = {
      number: 1,
      name: "KTYR ATIS",
      callsign: "KTYR",
      rxFreq: 126.25,
      txFreq: 126.25,
      offset: 0,
      offsetDir: "off",
      mode: "AM",
      power: "Low",
      toneMode: "None",
      ctcss: "None",
      rxCtcss: "None",
      dcs: "None",
      rxDcs: "None",
      dcsPolarity: "NN",
      bandwidth: "25KHz",
      city: "Tyler",
      state: "TX",
      lat: null,
      lon: null,
      specialType: "AVIATION",
      colorCode: null,
      timeSlot: null,
      dmrId: null,
      contact: null,
      comment: "",
    };
    return AVIATION_NAMING_FORMAT_OPTIONS.map(([code, label, desc]) => ({
      code,
      label,
      desc,
      sample: NameCondenser.condenseChannel(sampleAir, spec, code),
    }));
  }

  const sampleCh: RadioChannel = {
    number: 1,
    name: "Tyler 147.20",
    callsign: "W5ETX",
    rxFreq: 147.2,
    txFreq: 147.8,
    offset: 0.6,
    offsetDir: "+",
    mode: "FM",
    power: "High",
    toneMode: "Tone",
    ctcss: "136.5",
    rxCtcss: "None",
    dcs: "None",
    rxDcs: "None",
    dcsPolarity: "NN",
    bandwidth: "25KHz",
    city: "Tyler",
    state: "TX",
    lat: null,
    lon: null,
    specialType: "REPEATERS",
    colorCode: null,
    timeSlot: null,
    dmrId: null,
    contact: null,
    comment: "",
  };
  return NAMING_FORMAT_OPTIONS.map(([code, label, desc]) => ({
    code,
    label,
    desc,
    sample: NameCondenser.condenseChannel(sampleCh, spec, code),
  }));
}

function serializeChannel(ch: RadioChannel): Record<string, unknown> {
  return {
    ...ch,
    band: channelBand(ch.rxFreq),
    is_simplex: channelIsSimplex(ch),
  };
}

function defaultExportFilename(recipe: RadioPlannerRecipe, spec: TargetRadioSpec): string {
  const now = new Date();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const yy = String(now.getFullYear()).slice(-2);
  const prog = (recipe.radio_target.programmer_format || spec.programmerType || "RT_SYSTEMS").toLowerCase();
  return `${sanitizeFilename(recipe.name, "codeplug")}-${spec.id}-${prog}-${mm}${dd}${yy}.csv`;
}

function defaultBandsForRadio(spec: TargetRadioSpec, mode: string, sequenceOrder: string[] = []): string[] {
  if (mode.toUpperCase() === "AVIATION_PLANNER") {
    const hasTemplates = sequenceOrder.some((k) => k.startsWith("TEMPLATE:"));
    return hasTemplates ? Array.from(new Set([...spec.supportedBands, "Airband"])) : ["Airband"];
  }
  const isGmrsOnly =
    spec.supportedBands.some((b) => b.toLowerCase() === "gmrs") &&
    !spec.supportedBands.some((b) => b.toLowerCase() === "2m");
  const hasGmrsTemplate = sequenceOrder.includes("TEMPLATE:gmrs_channels");
  const defaultAmateur = spec.supportedBands.filter((b) => {
    const low = b.toLowerCase();
    if (low === "airband") return false;
    if (low === "gmrs" && !isGmrsOnly && !hasGmrsTemplate) return false;
    return true;
  });
  return defaultAmateur.length > 0 ? defaultAmateur : [...spec.supportedBands];
}

function renumberChannels(channels: RadioChannel[], startSlot: number): RadioChannel[] {
  return channels.map((ch, idx) => ({ ...ch, number: startSlot + idx }));
}

function parseNetLoggerJsonToTemplate(opts: {
  cleanId: string;
  name: string;
  description: string;
  tagText: string;
  rawJson: string;
}): PresetTemplateFile {
  let parsed: unknown;
  try {
    parsed = JSON.parse(opts.rawJson);
  } catch {
    throw new Error("Invalid JSON syntax.");
  }

  const records: Array<[string, Record<string, unknown>]> = [];
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const obj = parsed as Record<string, unknown>;
    if (obj.net_type_defaults && typeof obj.net_type_defaults === "object" && !Array.isArray(obj.net_type_defaults)) {
      for (const [label, cfg] of Object.entries(obj.net_type_defaults as Record<string, unknown>)) {
        if (cfg && typeof cfg === "object" && !Array.isArray(cfg)) {
          records.push([label, cfg as Record<string, unknown>]);
        }
      }
    } else if ("frequency" in obj) {
      records.push([String(obj.name || obj.callsign || "Net Preset"), obj]);
    } else {
      for (const [label, cfg] of Object.entries(obj)) {
        if (cfg && typeof cfg === "object" && !Array.isArray(cfg)) {
          const rec = cfg as Record<string, unknown>;
          if ("frequency" in rec || "rxFreq" in rec) {
            records.push([String(rec.name || label), rec]);
          }
        }
      }
    }
  } else if (Array.isArray(parsed)) {
    parsed.forEach((cfg, idx) => {
      if (cfg && typeof cfg === "object" && !Array.isArray(cfg)) {
        const rec = cfg as Record<string, unknown>;
        records.push([String(rec.name || rec.callsign || `Net ${idx + 1}`), rec]);
      }
    });
  }

  const channels: TemplateChannelItem[] = [];
  const freqRe = /(\d{1,4}(?:\.\d{1,6})?)/;
  const offRe = /([+-])[ \t]{0,4}(\d{1,4}(?:\.\d{1,5})?)/;
  const plRe = /\b(?:PL|CTCSS|TONE)[ \t:=]{0,6}(\d{2,3}\.\d)\b/i;
  const dcsRe = /\b(?:DCS|DTCS|D)[ \t:=]{0,6}(\d{3})\b/i;

  for (const [label, cfg] of records) {
    const freqRaw = String(cfg.frequency ?? cfg.rxFreq ?? "").trim().slice(0, 40);
    const fm = freqRaw.match(freqRe);
    if (!fm) continue;
    const rx = Number(Number(fm[1]).toFixed(5));
    if (!Number.isFinite(rx) || rx <= 0 || rx >= 3000) continue;

    const toneOff = String(cfg.tone_offset ?? "").trim().slice(0, 120);
    let offDir = "off";
    let offVal = 0.0;
    const om = toneOff.match(offRe);
    if (om) {
      offDir = om[1];
      const rawOff = Number(om[2]);
      offVal = Number((rawOff > 50 ? rawOff / 1000 : rawOff).toFixed(5));
    }

    const tx =
      offDir === "+"
        ? Number((rx + offVal).toFixed(5))
        : offDir === "-"
          ? Number((rx - offVal).toFixed(5))
          : rx;

    let toneMode = "None";
    let ctcss = "None";
    let dcs = "None";
    const pm = toneOff.match(plRe);
    const dm = toneOff.match(dcsRe);
    if (pm) {
      toneMode = "Tone";
      ctcss = pm[1];
    } else if (dm) {
      toneMode = "DCS";
      dcs = dm[1];
    }

    const modeVal = cleanSingleLine(cfg.mode ?? "FM", 12).toUpperCase() || "FM";
    const commentBits = [
      cleanSingleLine(cfg.callsign ?? "", 16),
      cleanSingleLine(cfg.location ?? "", 80),
      cleanSingleLine(toneOff, 60),
    ].filter(Boolean);

    channels.push({
      name: cleanSingleLine(label, 64) || `Net ${channels.length + 1}`,
      rxFreq: rx,
      txFreq: tx,
      offset: offDir !== "off" ? offVal : null,
      offsetDir: offDir,
      mode: modeVal,
      power: "High",
      toneMode,
      ctcss,
      rxCtcss: "None",
      dcs,
      rxDcs: toneMode === "DCS" ? dcs : "None",
      dcsPolarity: "NN",
      bandwidth: "25KHz",
      specialType: null,
      comment: commentBits.join(" | ").slice(0, 240),
    });
  }

  if (channels.length === 0) {
    throw new Error("No valid frequency entries found in Net Logger JSON.");
  }

  return {
    id: opts.cleanId,
    name: cleanSingleLine(opts.name, 100) || opts.cleanId,
    description: cleanSingleLine(opts.description, 240),
    tagText: cleanSingleLine(opts.tagText, 24).toUpperCase() || "NETLOG",
    tagColorHex: "#38bdf8",
    channels,
    fileName: null,
    rawCsvContent: null,
  };
}

function buildPocketReportText(
  recipe: RadioPlannerRecipe,
  codeplug: CodeplugState,
  spec: TargetRadioSpec,
  summary: Record<string, unknown>,
  operatorCallsign: string,
): string {
  const total = codeplug.channels.length;
  const endSlot = spec.startChannel + Math.max(total - 1, 0);
  const lines: string[] = [
    `RADIOPLANNER CODEPLUG REFERENCE CARD — ${codeplug.name}`,
    "=".repeat(78),
    `Mode:         ${recipe.mode}`,
    `Target Radio: ${spec.brand} ${spec.model} (${spec.id}) | Slots ${spec.startChannel}..${endSlot} (${total}/${spec.maxChannels})`,
    `LCD Limit:    ${spec.maxNameLength} chars | Naming: ${recipe.radio_target.naming_format} | Format: ${recipe.radio_target.programmer_format || spec.programmerType}`,
    `Generated:    ${utcNowIso()} | Operator: ${operatorCallsign}`,
  ];
  if (summary.subtitle) lines.push(`Coverage:     ${String(summary.subtitle)}`);
  if (Array.isArray(summary.states) && summary.states.length > 0) {
    lines.push(`States:       ${summary.states.join(", ")}`);
  }
  if (recipe.description) lines.push(`Notes:        ${recipe.description}`);

  lines.push(
    "-".repeat(78),
    `${"CH".padStart(4)}  ${"LCD NAME".padEnd(16)} ${"CALL".padEnd(8)} ${"RX (MHz)".padStart(10)} ${"DUP".padStart(7)} ${"TONE".padEnd(11)} ${"MODE".padEnd(5)} LOCATION`,
    "-".repeat(78),
  );

  for (const ch of codeplug.channels) {
    const dup = channelIsSimplex(ch) ? "SIMPLEX" : `${ch.offsetDir}${ch.offset.toFixed(3)}`;
    let tone = "CSQ";
    if ((ch.toneMode === "Tone" || ch.toneMode === "TSQL") && ch.ctcss !== "None") {
      tone = `${ch.toneMode.slice(0, 4)} ${ch.ctcss}`;
    } else if ((ch.toneMode === "DCS" || ch.toneMode === "DTCS") && ch.dcs !== "None") {
      tone = `DCS ${ch.dcs}`;
    }
    const loc = ch.city && ch.state ? `${ch.city}, ${ch.state}` : ch.city || ch.comment.slice(0, 24) || "-";
    lines.push(
      `${String(ch.number).padStart(4)}  ${ch.name.slice(0, 16).padEnd(16)} ${(ch.callsign || "-").padEnd(8)} ${ch.rxFreq.toFixed(4).padStart(10)} ${dup.padStart(7)} ${tone.padEnd(11)} ${ch.mode.padEnd(5)} ${loc}`,
    );
  }
  lines.push("-".repeat(78), `Total Channels: ${total}`);
  return `${lines.join("\n")}\n`;
}

function compareSemver(a: string, b: string): number {
  const pa = a.replace(/^v/i, "").split(".").map((x) => parseInt(x, 10) || 0);
  const pb = b.replace(/^v/i, "").split(".").map((x) => parseInt(x, 10) || 0);
  for (let i = 0; i < 3; i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

export class ApiRouter {
  readonly workspace: WebWorkspace;
  readonly appVersion: string;

  constructor(workspace: WebWorkspace, appVersion = readAppVersion()) {
    this.workspace = workspace;
    this.appVersion = appVersion;
  }

  private smartDefaultNaming(spec: TargetRadioSpec, mode: string): string {
    if (mode.toUpperCase() === "AVIATION_PLANNER") return "IDENT_TYPE";
    if (spec.maxNameLength <= 6) return "CALLSIGN";
    return this.workspace.prefsMgr.preferences.channelNamingFormat || "CITY_FREQ";
  }

  private serializePreferences(): Record<string, unknown> {
    const prefs = this.workspace.prefsMgr.preferences;
    const tokens = this.workspace.prefsMgr.tokens;
    return {
      callsign: prefs.callsign,
      operatorName: prefs.operatorName,
      primaryDmrId: prefs.primaryDmrId || "",
      distanceUnit: prefs.distanceUnit,
      defaultRadioId: prefs.defaultRadioId || "",
      channelNamingFormat: prefs.channelNamingFormat,
      repeaterAccess: [...prefs.repeaterAccess],
      repeaterMaxAgeDays: prefs.repeaterMaxAgeDays,
      webPort: prefs.webPort,
      theme: resolveCockpitTheme(prefs.colorTheme),
      ui_font: resolveUiFont(prefs.fontFamily),
      mono_font: prefs.monoFont,
      font_size: prefs.uiFontSize,
      lcd_font_size: prefs.lcdFontSize,
      panel_layout: sanitizePanelLayout(prefs.panelLayout),
      repeaterBookApiKeySet: Boolean(tokens.repeaterBookApiKey),
      radioIdUsername: tokens.radioIdUsername || "",
      radioIdApiKeySet: Boolean(tokens.radioIdApiKey),
      qrzUsername: tokens.qrzUsername || "",
      qrzConfigured: Boolean(tokens.qrzUsername && tokens.qrzPassword),
      has_api_key: this.workspace.repeaterProvider.hasApiKey(),
      config_dir: this.workspace.baseDir,
    };
  }

  private serializeRadios(): Array<Record<string, unknown>> {
    return this.workspace.radioMgr.listRadios().map((spec) => ({
      ...spec,
      is_user: this.workspace.radioMgr.isUserRadio(spec.id),
    }));
  }

  private serializeTemplates(): Array<Record<string, unknown>> {
    this.workspace.templateMgr.reload();
    return this.workspace.templateMgr.listTemplates().map((tpl) => {
      const channelsOut = tpl.channels.map((ch) => {
        const txF = ch.txFreq !== null && ch.txFreq !== undefined ? ch.txFreq : ch.rxFreq;
        const calcOff = ch.offset !== null && ch.offset !== undefined ? ch.offset : Math.abs(txF - ch.rxFreq);
        let effDir = "off";
        if (ch.offsetDir === "+" || ch.offsetDir === "-") effDir = ch.offsetDir;
        else if (txF - ch.rxFreq > 0.0001) effDir = "+";
        else if (ch.rxFreq - txF > 0.0001) effDir = "-";
        const effTone =
          ch.toneMode === "DCS" ? ch.dcs : ch.toneMode === "Tone" || ch.toneMode === "TSQL" ? ch.ctcss : "None";
        return {
          name: ch.name,
          rxFreq: ch.rxFreq,
          txFreq: txF,
          offsetDir: effDir,
          offset: Number((effDir !== "off" ? calcOff : 0.0).toFixed(5)),
          mode: ch.mode,
          power: ch.power,
          toneMode: ch.toneMode,
          toneVal: effTone,
          comment: ch.comment,
        };
      });
      return {
        id: tpl.id,
        name: tpl.name,
        description: tpl.description,
        tagText: tpl.tagText,
        tagColorHex: tpl.tagColorHex,
        channelCount: channelsOut.length,
        channels: channelsOut,
        is_user: this.workspace.templateMgr.isUserTemplate(tpl.id),
        is_builtin: tpl.id === "calling_channels" || tpl.id === "noaa_wx_channels" || tpl.id === "gmrs_channels",
      };
    });
  }

  private serializeRecipes(): Array<Record<string, unknown>> {
    return this.workspace.recipeMgr.listRecipes().map(({ filename, recipe }) => ({
      filename,
      name: recipe.name,
      description: recipe.description,
      mode: recipe.mode,
      corridor: recipe.corridor,
      proximity: recipe.proximity,
      aviation: recipe.aviation,
      radio_target: recipe.radio_target,
      sequence_order: [...recipe.sequence_order],
    }));
  }

  private serializeActivePlan(message = ""): Record<string, unknown> {
    const sess = this.workspace.session;
    if (!sess.recipe || !sess.codeplug || !sess.radio_spec) {
      return { active: false };
    }
    return {
      active: true,
      message,
      recipe: sess.recipe,
      radio_spec: sess.radio_spec,
      naming_previews: buildNamingPreviews(sess.radio_spec, sess.recipe.mode),
      codeplug: {
        name: sess.codeplug.name,
        total_channels: sess.codeplug.channels.length,
        channels: sess.codeplug.channels.map(serializeChannel),
      },
      summary: sess.summary_data,
      map_data: sess.map_data,
      notices: sess.notices,
      band_colors: BAND_COLORS,
      default_export_filename: defaultExportFilename(sess.recipe, sess.radio_spec),
      can_undo: sess.undo_stack.length > 0,
      undo_count: sess.undo_stack.length,
      undo_label: sess.undo_stack.length > 0 ? sess.undo_stack[sess.undo_stack.length - 1].label : "",
    };
  }

  async handle(req: RouterRequest): Promise<RouterResponse> {
    const method = req.method.toUpperCase();
    const p = req.pathname.replace(/\/+$/, "") || "/";

    try {
      // ─── Client unload (no-op in Electron) ────────────────────────────────
      if (method === "POST" && p === "/api/client/unload") {
        return jsonResponse({ ok: true, shutdown_scheduled: false });
      }

      // ─── Workspace reload (hand-edited files on disk) ─────────────────────
      if (method === "POST" && p === "/api/workspace/reload") {
        this.workspace.reloadAll();
        return jsonResponse({
          reloaded: true,
          preferences: this.serializePreferences(),
          radios: this.serializeRadios(),
          templates: this.serializeTemplates(),
          recipes: this.serializeRecipes(),
        });
      }

      // ─── Bootstrap Config ─────────────────────────────────────────────────
      if (method === "GET" && p === "/api/config") {
        const recipes = this.serializeRecipes();
        return jsonResponse({
          app_title: APP_TITLE,
          version: this.appVersion,
          install_mode: "electron",
          utc_now: utcNowIso(),
          preferences: this.serializePreferences(),
          radios: this.serializeRadios(),
          templates: this.serializeTemplates(),
          recipes_count: recipes.length,
          recipes_dir: this.workspace.recipeMgr.recipesDir,
          config_dir: this.workspace.baseDir,
          cached_states: this.workspace.repeaterProvider.listCachedStateFiles(),
          band_colors: BAND_COLORS,
          active_plan: this.serializeActivePlan(),
        });
      }

      // ─── Preferences ──────────────────────────────────────────────────────
      if (method === "GET" && p === "/api/preferences") {
        return jsonResponse({
          preferences: this.serializePreferences(),
          cached_states: this.workspace.repeaterProvider.listCachedStateFiles(),
        });
      }

      if (method === "PUT" && p === "/api/preferences") {
        const body = parseJsonBody(req.bodyText);
        const cur = this.workspace.prefsMgr.preferences;
        const nextPrefs = { ...cur };

        if (body.callsign !== undefined && body.callsign !== null) {
          nextPrefs.callsign = cleanSingleLine(body.callsign, 24).toUpperCase() || "N0CALL";
        }
        if (body.operatorName !== undefined && body.operatorName !== null) {
          nextPrefs.operatorName = cleanSingleLine(body.operatorName, 80) || "Radio Operator";
        }
        if (body.primaryDmrId !== undefined) {
          nextPrefs.primaryDmrId = cleanSingleLine(body.primaryDmrId, 16) || null;
        }
        if (body.defaultRadioId !== undefined) {
          nextPrefs.defaultRadioId = cleanSingleLine(body.defaultRadioId, 64) || null;
        }
        if (body.channelNamingFormat !== undefined && body.channelNamingFormat !== null) {
          nextPrefs.channelNamingFormat = cleanSingleLine(body.channelNamingFormat, 32);
        }
        if (body.distanceUnit !== undefined && body.distanceUnit !== null) {
          nextPrefs.distanceUnit = cleanSingleLine(body.distanceUnit, 16);
        }
        if (body.repeaterMaxAgeDays !== undefined && body.repeaterMaxAgeDays !== null) {
          const n = Number(body.repeaterMaxAgeDays);
          if (Number.isFinite(n) && n >= 1 && n <= 365) nextPrefs.repeaterMaxAgeDays = Math.round(n);
        }
        if (body.webPort !== undefined && body.webPort !== null) {
          const n = Number(body.webPort);
          if (Number.isFinite(n) && n >= 1 && n <= 65535) nextPrefs.webPort = Math.round(n);
        }
        if (body.colorTheme !== undefined && body.colorTheme !== null) {
          nextPrefs.colorTheme = cleanSingleLine(body.colorTheme, 32);
        }
        if (body.fontFamily !== undefined && body.fontFamily !== null) {
          nextPrefs.fontFamily = cleanSingleLine(body.fontFamily, 32);
        }
        if (body.monoFont !== undefined && body.monoFont !== null) {
          nextPrefs.monoFont = cleanSingleLine(body.monoFont, 32);
        }
        if (body.uiFontSize !== undefined && body.uiFontSize !== null) {
          const n = Number(body.uiFontSize);
          if (Number.isFinite(n)) nextPrefs.uiFontSize = Math.max(11, Math.min(22, Math.round(n)));
        }
        if (body.lcdFontSize !== undefined && body.lcdFontSize !== null) {
          const n = Number(body.lcdFontSize);
          if (Number.isFinite(n)) nextPrefs.lcdFontSize = Math.max(12, Math.min(26, Math.round(n)));
        }
        if (body.panelLayout && typeof body.panelLayout === "object" && !Array.isArray(body.panelLayout)) {
          const currentLayout = sanitizePanelLayout(cur.panelLayout);
          const merged = { ...currentLayout };
          for (const [k, v] of Object.entries(body.panelLayout as Record<string, unknown>)) {
            if (k in currentLayout && v && typeof v === "object" && !Array.isArray(v)) {
              merged[k] = { ...currentLayout[k], ...(v as Record<string, unknown>) };
            }
          }
          nextPrefs.panelLayout = sanitizePanelLayout(merged);
        }

        this.workspace.prefsMgr.savePreferences(nextPrefs);

        const curTokens = this.workspace.prefsMgr.tokens;
        const nextTokens = { ...curTokens };
        let tokensChanged = false;

        if (body.clearRepeaterBookApiKey === true) {
          nextTokens.repeaterBookApiKey = null;
          tokensChanged = true;
        } else if (typeof body.repeaterBookApiKey === "string" && body.repeaterBookApiKey.trim()) {
          nextTokens.repeaterBookApiKey = cleanSingleLine(body.repeaterBookApiKey, 256);
          tokensChanged = true;
        }

        if (body.radioIdUsername !== undefined) {
          nextTokens.radioIdUsername = cleanSingleLine(body.radioIdUsername, 32).toUpperCase() || null;
          tokensChanged = true;
        }

        if (body.clearRadioIdApiKey === true) {
          nextTokens.radioIdApiKey = null;
          tokensChanged = true;
        } else if (typeof body.radioIdApiKey === "string" && body.radioIdApiKey.trim()) {
          nextTokens.radioIdApiKey = cleanSingleLine(body.radioIdApiKey, 256);
          tokensChanged = true;
        }

        if (body.qrzUsername !== undefined) {
          nextTokens.qrzUsername = cleanSingleLine(body.qrzUsername, 120) || null;
          tokensChanged = true;
        }

        if (body.clearQrzPassword === true) {
          nextTokens.qrzPassword = null;
          tokensChanged = true;
        } else if (typeof body.qrzPassword === "string" && body.qrzPassword.trim()) {
          if (/[\x00\r\n]/.test(body.qrzPassword)) {
            throw new ApiError(400, "Password cannot contain newline or NUL characters.");
          }
          nextTokens.qrzPassword = body.qrzPassword.trim().slice(0, 200);
          tokensChanged = true;
        }

        if (tokensChanged) {
          this.workspace.prefsMgr.saveTokens(nextTokens);
          this.workspace.repeaterProvider.apiKey = nextTokens.repeaterBookApiKey;
          this.workspace.repeaterProvider.lastStatus = nextTokens.repeaterBookApiKey ? "CONFIGURED" : "NO_KEY";
          this.workspace.lookupService = new CallsignLookupService(
            nextTokens.qrzUsername,
            nextTokens.qrzPassword,
          );
        }

        return jsonResponse({
          preferences: this.serializePreferences(),
          cached_states: this.workspace.repeaterProvider.listCachedStateFiles(),
        });
      }

      // ─── Callsign Lookup & QRZ Test ───────────────────────────────────────
      if (method === "GET" && p.startsWith("/api/lookup/")) {
        const callsign = decodeURIComponent(p.slice("/api/lookup/".length));
        const cleaned = cleanSingleLine(callsign, 24).toUpperCase();
        const res = await this.workspace.lookupService.lookup(cleaned);
        if (!res) {
          return jsonResponse({ found: false, callsign: cleaned, error: "Callsign not found or offline." });
        }
        return jsonResponse({ found: true, ...res });
      }

      if (method === "POST" && p === "/api/preferences/test-qrz") {
        const body = parseJsonBody(req.bodyText);
        const tokens = this.workspace.prefsMgr.tokens;
        const user =
          typeof body.qrzUsername === "string" && body.qrzUsername.trim()
            ? cleanSingleLine(body.qrzUsername, 120)
            : tokens.qrzUsername || "";
        const pwd =
          typeof body.qrzPassword === "string" && body.qrzPassword.trim()
            ? body.qrzPassword.trim()
            : tokens.qrzPassword || "";
        const tester = new CallsignLookupService(user, pwd);
        return jsonResponse(await tester.testQrzLogin());
      }

      if (method === "POST" && p === "/api/preferences/test-repeaterbook") {
        const body = parseJsonBody(req.bodyText);
        const tokens = this.workspace.prefsMgr.tokens;
        const key =
          typeof body.repeaterBookApiKey === "string" && body.repeaterBookApiKey.trim()
            ? cleanSingleLine(body.repeaterBookApiKey, 256)
            : tokens.repeaterBookApiKey || "";
        return jsonResponse(await this.workspace.repeaterProvider.testApiKey(key));
      }

      // ─── NWS Alerts ───────────────────────────────────────────────────────
      if (method === "GET" && p === "/api/nws/plan-alerts") {
        const rawStates = (req.query.get("states") || "").trim();
        const targetStates = rawStates
          ? rawStates.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean)
          : Array.isArray(this.workspace.session.summary_data.states)
            ? (this.workspace.session.summary_data.states as string[])
            : [];
        return jsonResponse(await this.workspace.nwsService.getAlertsForStates(targetStates));
      }

      // ─── Geolocation ──────────────────────────────────────────────────────
      if (method === "GET" && p === "/api/geolocate") {
        const latStr = req.query.get("lat");
        const lonStr = req.query.get("lon");
        if (latStr !== null && lonStr !== null) {
          const lat = Number(latStr);
          const lon = Number(lonStr);
          if (Number.isFinite(lat) && Number.isFinite(lon)) {
            const loc = await this.workspace.geocoder.reverseGeocode(lat, lon);
            return jsonResponse({ ok: true, location: loc || `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon });
          }
        }
        const detected = await this.workspace.geocoder.geolocateByIp();
        if (detected) {
          return jsonResponse({ ok: true, location: detected.label, ...detected });
        }
        return jsonResponse({ ok: false, error: "Unable to detect current location." });
      }

      // ─── Plan Current & Generate ──────────────────────────────────────────
      if (method === "GET" && p === "/api/plan/current") {
        return jsonResponse(this.serializeActivePlan());
      }

      if (method === "POST" && p === "/api/plan/generate") {
        return jsonResponse(await this.handlePlanGenerate(parseJsonBody(req.bodyText)));
      }

      // ─── Codeplug Operations ──────────────────────────────────────────────
      if (method === "POST" && p === "/api/codeplug/update") {
        return jsonResponse(this.handleCodeplugUpdate(parseJsonBody(req.bodyText)));
      }

      if (method === "POST" && p === "/api/codeplug/delete-channels") {
        return jsonResponse(this.handleDeleteChannels(parseJsonBody(req.bodyText)));
      }

      if (method === "POST" && p === "/api/codeplug/undo-delete") {
        return jsonResponse(this.handleUndoDelete());
      }

      const netLoggerPresetMatch = p.match(/^\/api\/codeplug\/channels\/(\d+)\/net-logger-preset$/);
      if (method === "GET" && netLoggerPresetMatch) {
        return jsonResponse(this.handleChannelNetLoggerPreset(parseInt(netLoggerPresetMatch[1], 10)));
      }

      const editChannelMatch = p.match(/^\/api\/codeplug\/channels\/(\d+)$/);
      if (method === "PATCH" && editChannelMatch) {
        return jsonResponse(this.handleEditChannel(parseInt(editChannelMatch[1], 10), parseJsonBody(req.bodyText)));
      }

      if (method === "POST" && p === "/api/codeplug/expand-dmr") {
        return jsonResponse(this.handleExpandDmr());
      }

      if (method === "GET" && p === "/api/codeplug/report") {
        return jsonResponse(this.handleCodeplugReport());
      }

      if (method === "POST" && p === "/api/codeplug/export") {
        return this.handleCodeplugExport(parseJsonBody(req.bodyText));
      }

      // ─── Recipes API (+ Export YAML) ──────────────────────────────────────
      if (method === "GET" && p === "/api/recipes") {
        return jsonResponse({
          recipes_dir: this.workspace.recipeMgr.recipesDir,
          recipes: this.serializeRecipes(),
        });
      }

      if (method === "POST" && p === "/api/recipes/save") {
        const body = parseJsonBody(req.bodyText);
        const sess = this.workspace.session;
        if (!sess.recipe || !sess.codeplug || !sess.radio_spec) {
          throw new ApiError(400, "No active recipe to save.");
        }
        const nextName = cleanSingleLine(body.name ?? sess.recipe.name, 100) || sess.recipe.name;
        const nextDesc = cleanSingleLine(body.description ?? sess.recipe.description, 300);
        sess.recipe = {
          ...sess.recipe,
          name: nextName,
          description: nextDesc,
        };
        sess.codeplug = {
          ...sess.codeplug,
          name: nextName,
        };
        this.workspace.saveSession();
        const saved = this.workspace.recipeMgr.saveRecipe(sess.recipe);
        return jsonResponse({
          saved: true,
          filename: saved.filename,
          path: saved.fullPath,
          message: `Saved radio-agnostic recipe '${sess.recipe.name}' to ${saved.filename}`,
          recipes: this.serializeRecipes(),
          active_plan: this.serializeActivePlan(),
        });
      }

      if (method === "POST" && p === "/api/recipes/upload") {
        const body = parseJsonBody(req.bodyText);
        const yamlText = typeof body.yaml_text === "string" ? body.yaml_text : "";
        const filename = cleanSingleLine(body.filename ?? "uploaded_recipe.yaml", 120) || "uploaded_recipe.yaml";
        const imported = this.workspace.recipeMgr.importRecipeYaml(yamlText, filename);
        return jsonResponse({
          uploaded: true,
          filename: imported.filename,
          recipe: imported.recipe,
          recipes: this.serializeRecipes(),
        });
      }

      const recipeExportMatch = p.match(/^\/api\/recipes\/([^/]+)\/export$/);
      if (method === "GET" && recipeExportMatch) {
        const fname = decodeURIComponent(recipeExportMatch[1]);
        const item = this.workspace.recipeMgr.getRecipe(fname);
        return textDownloadResponse(item.rawYaml, "application/x-yaml; charset=utf-8", item.filename);
      }

      const recipeItemMatch = p.match(/^\/api\/recipes\/([^/]+)$/);
      if (recipeItemMatch) {
        const fname = decodeURIComponent(recipeItemMatch[1]);
        if (method === "GET") {
          const item = this.workspace.recipeMgr.getRecipe(fname);
          return jsonResponse({ filename: item.filename, recipe: item.recipe });
        }
        if (method === "DELETE") {
          const deleted = this.workspace.recipeMgr.deleteRecipe(fname);
          if (!deleted) throw new ApiError(404, "Recipe file not found.");
          return jsonResponse({ deleted: true, filename: fname, recipes: this.serializeRecipes() });
        }
      }

      // ─── Templates API (+ Export YAML) ────────────────────────────────────
      if (method === "GET" && p === "/api/templates") {
        return jsonResponse({
          core_templates_dir: this.workspace.templateMgr.appDir,
          user_templates_dir: this.workspace.templateMgr.userDir,
          templates: this.serializeTemplates(),
        });
      }

      if (method === "POST" && p === "/api/templates") {
        return jsonResponse(this.handleSaveTemplate(parseJsonBody(req.bodyText)));
      }

      if (method === "POST" && p === "/api/templates/import") {
        return jsonResponse(this.handleImportTemplate(parseJsonBody(req.bodyText)));
      }

      if (method === "POST" && p === "/api/templates/import-net-logger") {
        const body = parseJsonBody(req.bodyText);
        const cleanId = sanitizeSlug(String(body.id ?? "net_logger_presets"), "net_logger_presets");
        const tpl = parseNetLoggerJsonToTemplate({
          cleanId,
          name: String(body.name ?? "W5CDN Net Logger Presets"),
          description: String(body.description ?? "Imported from W5CDN Net Logger net_type_defaults JSON"),
          tagText: String(body.tagText ?? "NETLOG"),
          rawJson: String(body.json_text ?? ""),
        });
        this.workspace.templateMgr.saveTemplate(tpl);
        return jsonResponse({
          imported: true,
          id: tpl.id,
          message: `Imported ${tpl.channels.length} Net Logger preset(s) into template '${tpl.name}'.`,
          templates: this.serializeTemplates(),
        });
      }

      const tplExportMatch = p.match(/^\/api\/templates\/([^/]+)\/export$/);
      if (method === "GET" && tplExportMatch) {
        const tplId = decodeURIComponent(tplExportMatch[1]);
        const exported = this.workspace.templateMgr.exportTemplateYaml(tplId);
        return textDownloadResponse(exported.yaml, "application/x-yaml; charset=utf-8", exported.filename);
      }

      const tplDeleteMatch = p.match(/^\/api\/templates\/([^/]+)$/);
      if (method === "DELETE" && tplDeleteMatch) {
        const tplId = cleanSingleLine(decodeURIComponent(tplDeleteMatch[1]), 64);
        if (tplId === "calling_channels" || tplId === "noaa_wx_channels" || tplId === "gmrs_channels") {
          throw new ApiError(400, "Built-in system templates cannot be deleted.");
        }
        const deleted = this.workspace.templateMgr.deleteTemplate(tplId);
        if (!deleted) throw new ApiError(404, `Template '${tplId}' not found.`);
        return jsonResponse({ deleted: true, id: tplId, templates: this.serializeTemplates() });
      }

      // ─── Radios API (+ Export YAML & Validated Import YAML) ───────────────
      if (method === "GET" && p === "/api/radios") {
        return jsonResponse({ radios: this.serializeRadios() });
      }

      if (method === "POST" && p === "/api/radios/import") {
        const body = parseJsonBody(req.bodyText);
        const yamlText = typeof body.yaml_text === "string" ? body.yaml_text : String(body.content ?? "");
        const filename = cleanSingleLine(body.filename ?? "imported_radio.yaml", 120) || "imported_radio.yaml";
        const spec = this.workspace.radioMgr.importRadioYaml(yamlText, filename);
        return jsonResponse({
          imported: true,
          radio: spec,
          message: `Validated and imported radio profile '${spec.brand} ${spec.model}' (${spec.id}).`,
          radios: this.serializeRadios(),
        });
      }

      if (method === "POST" && p === "/api/radios") {
        return jsonResponse(this.handleSaveRadio(parseJsonBody(req.bodyText)));
      }

      const radioExportMatch = p.match(/^\/api\/radios\/([^/]+)\/export$/);
      if (method === "GET" && radioExportMatch) {
        const radioId = decodeURIComponent(radioExportMatch[1]);
        const exported = this.workspace.radioMgr.exportRadioYaml(radioId);
        return textDownloadResponse(exported.yaml, "application/x-yaml; charset=utf-8", exported.filename);
      }

      const radioPreviewsMatch = p.match(/^\/api\/radios\/([^/]+)\/naming-previews$/);
      if (method === "GET" && radioPreviewsMatch) {
        const radioId = decodeURIComponent(radioPreviewsMatch[1]);
        const mode = req.query.get("mode") || "ROUTE_CORRIDOR";
        const spec = this.workspace.radioMgr.getRadio(radioId);
        return jsonResponse({
          radio: spec,
          naming_previews: buildNamingPreviews(spec, mode),
        });
      }

      const radioDeleteMatch = p.match(/^\/api\/radios\/([^/]+)$/);
      if (method === "DELETE" && radioDeleteMatch) {
        const radioId = cleanSingleLine(decodeURIComponent(radioDeleteMatch[1]), 64);
        const deleted = this.workspace.radioMgr.deleteUserRadio(radioId);
        if (!deleted) throw new ApiError(404, `Custom user radio '${radioId}' not found.`);
        return jsonResponse({ deleted: true, id: radioId, radios: this.serializeRadios() });
      }

      // ─── Backup & Restore ─────────────────────────────────────────────────
      if (method === "GET" && p === "/api/backup/export") {
        const includeTokens = req.query.get("include_tokens") === "true" || req.query.get("include_tokens") === "1";
        const buf = await createConfigBackupZipBytes(this.workspace, {
          includeTokens,
          appVersion: this.appVersion,
        });
        const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z").replace("T", "_");
        return {
          status: 200,
          headers: {
            "Content-Type": "application/zip",
            "Content-Disposition": `attachment; filename="radioplanner_backup_${stamp}.zip"`,
          },
          body: buf,
        };
      }

      if (method === "POST" && p === "/api/backup/restore") {
        const rawBuf = req.bodyBuffer ?? Buffer.from(req.bodyText ?? "", "utf-8");
        const res = await restoreConfigBackupZipBytes(this.workspace, rawBuf);
        return jsonResponse({
          ...res,
          preferences: this.serializePreferences(),
          radios: this.serializeRadios(),
          templates: this.serializeTemplates(),
          recipes: this.serializeRecipes(),
        });
      }

      // ─── Update Check (GitHub Releases) ───────────────────────────────────
      if (method === "GET" && p === "/api/update/check") {
        return jsonResponse(await this.handleUpdateCheck());
      }

      if (method === "POST" && p === "/api/update/apply") {
        return jsonResponse(
          {
            ok: false,
            detail: "Download the latest W5CDN RadioPlanner installer from GitHub Releases to upgrade.",
          },
          400,
        );
      }

      return jsonResponse({ detail: "API endpoint not found." }, 404);
    } catch (err) {
      if (err instanceof ApiError) {
        return jsonResponse({ detail: err.message, ...(err.detail ? { info: err.detail } : {}) }, err.status);
      }
      if (err instanceof YamlDiagnosticError) {
        return jsonResponse({ detail: err.formatReport(), diagnostic: err.toPayload() }, 400);
      }
      const msg = err instanceof Error ? err.message : "Internal server error";
      if (/not found/i.test(msg)) {
        return jsonResponse({ detail: msg }, 404);
      }
      if (/unsafe filename|escapes base directory|invalid|required/i.test(msg)) {
        return jsonResponse({ detail: msg }, 400);
      }
      return jsonResponse({ detail: msg }, 500);
    }
  }

  private async handlePlanGenerate(body: Record<string, unknown>): Promise<Record<string, unknown>> {
    const mode = String(body.mode ?? "ROUTE_CORRIDOR").trim().toUpperCase();
    if (mode !== "ROUTE_CORRIDOR" && mode !== "PROXIMITY_SEARCH" && mode !== "AVIATION_PLANNER") {
      throw new ApiError(400, `Unsupported planner mode: ${mode}`);
    }

    const includeSimplex = body.include_simplex !== undefined ? Boolean(body.include_simplex) : true;
    const repeaterAccess = Array.isArray(body.repeater_access)
      ? body.repeater_access.map((a) => String(a).trim().toUpperCase()).filter(Boolean)
      : ["OPEN"];
    if (repeaterAccess.length === 0) repeaterAccess.push("OPEN");

    let sequenceOrder = Array.isArray(body.sequence_order)
      ? body.sequence_order.map((s) => String(s).trim()).filter(Boolean)
      : [];

    const allRadios = this.workspace.radioMgr.listRadios();
    if (allRadios.length === 0) {
      throw new ApiError(500, "No target radio hardware specs configured.");
    }

    let radioId: string;
    const reqRadioId = typeof body.radio_id === "string" ? body.radio_id.trim() : "";
    if (reqRadioId && this.workspace.radioMgr.hasRadio(reqRadioId)) {
      radioId = reqRadioId;
    } else if (this.workspace.session.radio_spec && this.workspace.radioMgr.hasRadio(this.workspace.session.radio_spec.id)) {
      radioId = this.workspace.session.radio_spec.id;
    } else {
      const defPref = this.workspace.prefsMgr.preferences.defaultRadioId;
      radioId = defPref && this.workspace.radioMgr.hasRadio(defPref) ? defPref : allRadios[0].id;
      if (mode === "AVIATION_PLANNER" && !this.workspace.radioMgr.getRadio(radioId).supportedBands.includes("Airband")) {
        const airRadio = allRadios.find((r) => r.supportedBands.includes("Airband"));
        if (airRadio) radioId = airRadio.id;
      }
    }

    const radioSpec = this.workspace.radioMgr.getRadio(radioId);
    const submittedBands = Array.isArray(body.bands)
      ? body.bands.map((b) => String(b).trim()).filter(Boolean)
      : [];
    let bands = submittedBands.length > 0 ? submittedBands : defaultBandsForRadio(radioSpec, mode, sequenceOrder);
    const submittedNaming = typeof body.naming_format === "string" ? body.naming_format.trim().toUpperCase() : "";
    const namingFormat = submittedNaming || this.smartDefaultNaming(radioSpec, mode);

    this.workspace.session.deleted_keys = new Set();
    this.workspace.session.undo_stack = [];

    const planDescription = cleanSingleLine(body.plan_description ?? "", 300);
    const notices: Array<{ level: string; message: string }> = [];
    const mapData: Record<string, unknown> = { center: [32.35, -95.3], zoom: 6, channels: [] };
    const summary: Record<string, unknown> = {
      title: "Plan Summary",
      subtitle: "",
      metric_badge: "",
      rows: [],
      band_counts: {},
      states: [],
    };

    let primaryChannels: RadioChannel[] = [];
    let recipe: RadioPlannerRecipe;

    if (mode === "ROUTE_CORRIDOR") {
      const rawWaypoints = Array.isArray(body.waypoints)
        ? body.waypoints
        : ["Tyler, TX", "Shreveport, LA", "Jackson, MS"];
      const waypoints = rawWaypoints.map((w) => cleanSingleLine(w, 120)).filter(Boolean);
      if (waypoints.length < 2) {
        throw new ApiError(400, "At least 2 waypoints are required for a route corridor.");
      }
      const corridorWidth = Math.max(1, Math.min(200, Number(body.corridor_width ?? 25) || 25));
      if (sequenceOrder.length === 0) {
        sequenceOrder = ["TEMPLATE:calling_channels", "ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"];
      }
      if (radioSpec.supportedBands.includes("GMRS") && !radioSpec.supportedBands.includes("2m")) {
        if (!sequenceOrder.includes("TEMPLATE:gmrs_channels")) {
          sequenceOrder = ["TEMPLATE:gmrs_channels", ...sequenceOrder];
        }
      }

      const resolvedPts: Array<{ name: string; lat: number; lon: number }> = [];
      for (const wp of waypoints) {
        const coords = await this.workspace.geocoder.geocode(wp);
        if (coords) {
          resolvedPts.push({ name: wp, lat: coords[0], lon: coords[1] });
        }
      }
      if (resolvedPts.length < 2) {
        throw new ApiError(400, `Could not geocode at least 2 waypoints from: ${waypoints.join(", ")}`);
      }

      const routeCoords: Array<[number, number]> = resolvedPts.map((pt) => [pt.lat, pt.lon]);
      const routeStates = identifyStatesForRoute(routeCoords, corridorWidth, waypoints);
      const rbRes = await this.workspace.repeaterProvider.getRepeatersForStates(routeStates, {
        allowedUse: repeaterAccess,
        includeGmrs: true,
      });
      const candidateChannels = includeSimplex
        ? rbRes.channels
        : rbRes.channels.filter((ch) => !channelIsSimplex(ch));

      const matches = RouteCorridorEngine.filterAndOrder(candidateChannels, routeCoords, corridorWidth);
      const wxMatches = RouteCorridorEngine.filterAndOrder(
        getOfflineWxStations(),
        routeCoords,
        Math.max(corridorWidth, 45),
      );
      primaryChannels = [...matches.map((m) => m.channel), ...wxMatches.map((m) => m.channel)];

      const cumulativeMiles: number[] = [0];
      let totalMiles = 0;
      for (let i = 1; i < resolvedPts.length; i++) {
        totalMiles += haversineMiles(
          resolvedPts[i - 1].lat,
          resolvedPts[i - 1].lon,
          resolvedPts[i].lat,
          resolvedPts[i].lon,
        );
        cumulativeMiles.push(totalMiles);
      }

      const startCity = waypoints[0].split(",")[0].trim();
      const endCity = waypoints[waypoints.length - 1].split(",")[0].trim();
      const customName = cleanSingleLine(body.plan_name ?? "", 100);
      const planName = customName || `${startCity}_to_${endCity}_Corridor`;

      recipe = {
        version: "1.0",
        mode: "ROUTE_CORRIDOR",
        name: planName,
        description: planDescription,
        corridor: { waypoints, corridor_width_miles: corridorWidth },
        proximity: null,
        aviation: null,
        radio_target: {
          radio_id: radioId,
          programmer_format: radioSpec.programmerType,
          include_simplex: includeSimplex,
          bands,
          modes: [...radioSpec.supportedModes],
          repeater_access: repeaterAccess,
          naming_format: namingFormat,
        },
        sequence_order: sequenceOrder,
        export: { output_dir: "./exports", filename_pattern: null },
      };

      mapData.center = routeCoords[Math.floor(routeCoords.length / 2)];
      mapData.route_coords = routeCoords;
      mapData.waypoints = resolvedPts;
      summary.title = "Route Waypoints & Distance";
      summary.subtitle = `${resolvedPts.length} stops • ${totalMiles.toFixed(1)} miles`;
      summary.metric_badge = `${totalMiles.toFixed(1)} mi`;
      summary.rows = resolvedPts.map((pt, i) => ({
        label: pt.name || `Stop ${i + 1}`,
        value: `${cumulativeMiles[i].toFixed(1)} mi`,
      }));
      summary.states = routeStates;
    } else if (mode === "PROXIMITY_SEARCH") {
      const centerLoc = cleanSingleLine(body.center_location ?? "Dallas, TX", 120) || "Dallas, TX";
      const radiusMiles = Math.max(1, Math.min(300, Number(body.radius_miles ?? 50) || 50));
      if (sequenceOrder.length === 0) {
        sequenceOrder = ["TEMPLATE:calling_channels", "PROXIMITY_PLAN", "TEMPLATE:noaa_wx_channels"];
      }
      if (radioSpec.supportedBands.includes("GMRS") && !radioSpec.supportedBands.includes("2m")) {
        if (!sequenceOrder.includes("TEMPLATE:gmrs_channels")) {
          sequenceOrder = ["TEMPLATE:gmrs_channels", ...sequenceOrder];
        }
      }

      const centerCoords = await this.workspace.geocoder.geocode(centerLoc);
      if (!centerCoords) {
        throw new ApiError(400, `Could not geocode center location '${centerLoc}'.`);
      }

      const proxStates = identifyStatesForProximity(centerCoords[0], centerCoords[1], radiusMiles, centerLoc);
      const rbRes = await this.workspace.repeaterProvider.getRepeatersForStates(proxStates, {
        allowedUse: repeaterAccess,
        includeGmrs: true,
      });
      const candidateChannels = includeSimplex
        ? rbRes.channels
        : rbRes.channels.filter((ch) => !channelIsSimplex(ch));

      const matches = ProximityEngine.filterAndOrder(candidateChannels, centerCoords[0], centerCoords[1], radiusMiles);
      const wxMatches = ProximityEngine.filterAndOrder(
        getOfflineWxStations(),
        centerCoords[0],
        centerCoords[1],
        Math.max(radiusMiles, 50),
      );
      primaryChannels = [...matches.map((m) => m.channel), ...wxMatches.map((m) => m.channel)];

      // Build concentric distance rings (up to 4 rings)
      const ringCount = radiusMiles <= 20 ? 2 : radiusMiles <= 45 ? 3 : 4;
      const ringStep = radiusMiles / ringCount;
      const rings: Array<{ index: number; start_mi: number; end_mi: number; color: string; count: number }> = [];
      for (let r = 1; r <= ringCount; r++) {
        const startMi = (r - 1) * ringStep;
        const endMi = r * ringStep;
        const count = matches.filter((m) => (r === 1 ? m.distanceMiles <= endMi : m.distanceMiles > startMi && m.distanceMiles <= endMi)).length;
        rings.push({
          index: r,
          start_mi: Math.round(startMi),
          end_mi: Math.round(endMi),
          color: RING_COLORS[(r - 1) % RING_COLORS.length],
          count,
        });
      }

      const cityClean = centerLoc.split(",")[0].trim();
      const customName = cleanSingleLine(body.plan_name ?? "", 100);
      const planName = customName || `${cityClean}_Proximity_${Math.round(radiusMiles)}mi`;

      recipe = {
        version: "1.0",
        mode: "PROXIMITY_SEARCH",
        name: planName,
        description: planDescription,
        corridor: null,
        proximity: { center_location: centerLoc, radius_miles: radiusMiles },
        aviation: null,
        radio_target: {
          radio_id: radioId,
          programmer_format: radioSpec.programmerType,
          include_simplex: includeSimplex,
          bands,
          modes: [...radioSpec.supportedModes],
          repeater_access: repeaterAccess,
          naming_format: namingFormat,
        },
        sequence_order: sequenceOrder,
        export: { output_dir: "./exports", filename_pattern: null },
      };

      mapData.center = [centerCoords[0], centerCoords[1]];
      mapData.waypoints = [{ name: centerLoc, lat: centerCoords[0], lon: centerCoords[1] }];
      mapData.rings = rings;
      summary.title = "Concentric Proximity Rings";
      summary.subtitle = `${centerLoc} • ${Math.round(radiusMiles)} mi radius`;
      summary.metric_badge = `${Math.round(radiusMiles)} mi radius`;
      summary.rows = rings.map((rg) => ({
        label: `Ring ${rg.index} (${rg.start_mi}–${rg.end_mi} mi)`,
        value: `${rg.count} ch`,
        color: rg.color,
      }));
      summary.states = proxStates;
    } else {
      // AVIATION_PLANNER
      const centerLoc = cleanSingleLine(body.center_location ?? "Tyler, TX", 120) || "Tyler, TX";
      const radiusMiles = Math.max(1, Math.min(300, Number(body.radius_miles ?? 35) || 35));
      if (sequenceOrder.length === 0) {
        sequenceOrder = ["AVIATION_BLOCK"];
      }

      if (!radioSpec.supportedBands.includes("Airband")) {
        notices.push({
          level: "warning",
          message: `${radioSpec.brand} ${radioSpec.model} does not list 'Airband' (108–137 MHz AM) in its supported hardware bands. Airband channels are shown below for preview, or switch to an Airband-capable radio.`,
        });
      }

      const centerCoords = await this.workspace.geocoder.geocode(centerLoc);
      if (!centerCoords) {
        throw new ApiError(400, `Could not geocode center location '${centerLoc}'.`);
      }

      const hasTemplates = sequenceOrder.some((k) => k.startsWith("TEMPLATE:"));
      const activeBands = hasTemplates ? Array.from(new Set([...radioSpec.supportedBands, "Airband"])) : ["Airband"];
      const activeModes = hasTemplates ? Array.from(new Set([...radioSpec.supportedModes, "AM"])) : ["AM"];

      const engine = new AviationEngine(this.workspace.airportsProvider);
      const res = engine.discover(centerCoords[0], centerCoords[1], radiusMiles);
      primaryChannels = res.channels;

      if (res.airfields.length === 0) {
        notices.push({
          level: "warning",
          message: `No airfields found within ${Math.round(radiusMiles)} miles of '${centerLoc}'. Try increasing the search radius.`,
        });
      }

      const cityClean = centerLoc.split(",")[0].trim();
      const customName = cleanSingleLine(body.plan_name ?? "", 100);
      const planName = customName || `${cityClean}_Aviation_${Math.round(radiusMiles)}mi`;

      recipe = {
        version: "1.0",
        mode: "AVIATION_PLANNER",
        name: planName,
        description: planDescription,
        corridor: null,
        proximity: null,
        aviation: { center_location: centerLoc, radius_miles: radiusMiles },
        radio_target: {
          radio_id: radioId,
          programmer_format: radioSpec.programmerType,
          include_simplex: false,
          bands: activeBands,
          modes: activeModes,
          repeater_access: ["OPEN"],
          naming_format: namingFormat,
        },
        sequence_order: sequenceOrder,
        export: { output_dir: "./exports", filename_pattern: null },
      };

      bands = activeBands;
      mapData.center = [centerCoords[0], centerCoords[1]];
      mapData.waypoints = res.airfields.map(({ airfield }) => ({
        name: `${airfield.ident} (${airfield.name})`,
        lat: airfield.latitude,
        lon: airfield.longitude,
      }));
      summary.title = "Airfields Within Range";
      summary.subtitle = `${res.airfields.length} airfields within ${Math.round(radiusMiles)} mi`;
      summary.metric_badge = `${res.airfields.length} airfields`;
      summary.rows = res.airfields.map(({ airfield, distanceMiles }) => ({
        label: `${airfield.ident} — ${airfield.name}`,
        value: `${distanceMiles.toFixed(1)} mi`,
      }));
      summary.states = identifyStatesForProximity(centerCoords[0], centerCoords[1], radiusMiles, centerLoc);
    }

    const assemblySpec: TargetRadioSpec =
      mode === "AVIATION_PLANNER"
        ? {
            ...radioSpec,
            supportedBands: Array.from(new Set([...radioSpec.supportedBands, "Airband"])),
            supportedModes: Array.from(new Set([...radioSpec.supportedModes, "AM"])),
          }
        : radioSpec;

    const uncondensedSpec: TargetRadioSpec = {
      ...assemblySpec,
      maxNameLength: 64,
      allowDots: true,
      allowSpaces: true,
    };

    const rawAssembled = SequenceOrganizer.assemble({
      codeplugName: recipe.name,
      sequenceKeys: recipe.sequence_order,
      primaryChannels,
      targetSpec: uncondensedSpec,
      templateManager: this.workspace.templateMgr,
      allowedBands: bands,
      allowedModes: recipe.radio_target.modes,
      namingFormat: "STANDARD",
    });

    const codeplug = SequenceOrganizer.assemble({
      codeplugName: recipe.name,
      sequenceKeys: recipe.sequence_order,
      primaryChannels,
      targetSpec: assemblySpec,
      templateManager: this.workspace.templateMgr,
      allowedBands: bands,
      allowedModes: recipe.radio_target.modes,
      namingFormat,
    });

    if (codeplug.channels.length > radioSpec.maxChannels) {
      notices.push({
        level: "warning",
        message: `Plan contains ${codeplug.channels.length} channels, which exceeds ${radioSpec.brand} ${radioSpec.model}'s ${radioSpec.maxChannels}-channel memory limit.`,
      });
    }

    const primaryWxStations = primaryChannels.filter((ch) => channelBand(ch.rxFreq) === "WX");
    const { bandCounts, mapChannels } = computeBandCountsAndMapChannels(
      codeplug.channels,
      bands,
      primaryWxStations,
    );
    mapData.channels = mapChannels;
    summary.band_counts = bandCounts;

    this.workspace.session.recipe = recipe;
    this.workspace.session.codeplug = codeplug;
    this.workspace.session.radio_spec = radioSpec;
    this.workspace.session.primary_channels = primaryChannels;
    this.workspace.session.raw_channels = [...rawAssembled.channels];
    this.workspace.session.map_data = mapData;
    this.workspace.session.summary_data = summary;
    this.workspace.session.notices = notices;
    this.workspace.saveSession();

    return this.serializeActivePlan(
      `Assembled ${codeplug.channels.length} channels for ${radioSpec.brand} ${radioSpec.model}.`,
    );
  }

  private handleCodeplugUpdate(body: Record<string, unknown>): Record<string, unknown> {
    const sess = this.workspace.session;
    if (!sess.recipe || !sess.codeplug) {
      throw new ApiError(400, "No active codeplug session.");
    }

    const radioId = String(body.radio_id ?? "").trim();
    const spec = this.workspace.radioMgr.getRadio(radioId);
    const reqBands = Array.isArray(body.bands) ? body.bands.map((b) => String(b).trim()).filter(Boolean) : [];
    const reqNaming = typeof body.naming_format === "string" ? body.naming_format.trim().toUpperCase() : "";
    const radioChanged = Boolean(body.radio_changed);
    const includeGmrsStd = Boolean(body.include_gmrs_std);

    const isRadioSwitch =
      radioChanged || (sess.radio_spec !== null && sess.radio_spec.id !== spec.id && reqBands.length === 0);
    const isGmrsOnly = spec.supportedBands.includes("GMRS") && !spec.supportedBands.includes("2m");

    let activeNaming: string;
    let activeBands: string[];
    let seq = [...sess.recipe.sequence_order];

    if (isRadioSwitch) {
      activeNaming = !reqNaming || radioChanged ? this.smartDefaultNaming(spec, sess.recipe.mode) : reqNaming;
      activeBands = defaultBandsForRadio(spec, sess.recipe.mode, seq);
      if (isGmrsOnly && !seq.includes("TEMPLATE:gmrs_channels")) {
        seq = ["TEMPLATE:gmrs_channels", ...seq];
      }
    } else {
      activeNaming = reqNaming || sess.recipe.radio_target.naming_format || this.smartDefaultNaming(spec, sess.recipe.mode);
      activeBands =
        reqBands.length > 0
          ? reqBands.filter((b) => spec.supportedBands.includes(b))
          : sess.recipe.radio_target.bands.filter((b) => spec.supportedBands.includes(b));
      if (activeBands.length === 0) {
        activeBands = defaultBandsForRadio(spec, sess.recipe.mode, seq);
      }
      if (spec.supportedBands.includes("GMRS")) {
        if (includeGmrsStd) {
          if (!seq.includes("TEMPLATE:gmrs_channels")) seq = ["TEMPLATE:gmrs_channels", ...seq];
          if (!activeBands.includes("GMRS")) activeBands.push("GMRS");
        } else {
          seq = seq.filter((k) => k !== "TEMPLATE:gmrs_channels");
        }
      }
    }

    const updatedRecipe: RadioPlannerRecipe = {
      ...sess.recipe,
      sequence_order: seq,
      radio_target: {
        ...sess.recipe.radio_target,
        radio_id: spec.id,
        programmer_format: spec.programmerType,
        naming_format: activeNaming,
        bands: activeBands,
        modes: Array.from(
          new Set([...spec.supportedModes, ...(sess.recipe.mode === "AVIATION_PLANNER" ? ["AM"] : [])]),
        ),
      },
    };

    const assemblySpec: TargetRadioSpec =
      updatedRecipe.mode === "AVIATION_PLANNER"
        ? {
            ...spec,
            supportedBands: Array.from(new Set([...spec.supportedBands, "Airband"])),
            supportedModes: Array.from(new Set([...spec.supportedModes, "AM"])),
          }
        : spec;

    let assembled = SequenceOrganizer.assemble({
      codeplugName: updatedRecipe.name,
      sequenceKeys: updatedRecipe.sequence_order,
      primaryChannels: sess.primary_channels,
      targetSpec: assemblySpec,
      templateManager: this.workspace.templateMgr,
      allowedBands: activeBands,
      allowedModes: updatedRecipe.radio_target.modes,
      namingFormat: activeNaming,
    });

    if (sess.deleted_keys.size > 0) {
      const kept = assembled.channels.filter((ch) => !sess.deleted_keys.has(channelDeleteKey(ch)));
      assembled = { name: assembled.name, channels: renumberChannels(kept, spec.startChannel) };
    }

    const rawAssembled = SequenceOrganizer.assemble({
      codeplugName: updatedRecipe.name,
      sequenceKeys: updatedRecipe.sequence_order,
      primaryChannels: sess.primary_channels,
      targetSpec: { ...assemblySpec, maxNameLength: 64, allowDots: true, allowSpaces: true },
      templateManager: this.workspace.templateMgr,
      allowedBands: activeBands,
      allowedModes: updatedRecipe.radio_target.modes,
      namingFormat: "STANDARD",
    });

    const notices: Array<{ level: string; message: string }> = [];
    if (updatedRecipe.mode === "AVIATION_PLANNER" && !spec.supportedBands.includes("Airband")) {
      notices.push({
        level: "warning",
        message: `${spec.brand} ${spec.model} does not list 'Airband' in its supported hardware bands.`,
      });
    }
    if (assembled.channels.length > spec.maxChannels) {
      notices.push({
        level: "warning",
        message: `Plan contains ${assembled.channels.length} channels, exceeding ${spec.brand} ${spec.model}'s ${spec.maxChannels}-channel limit.`,
      });
    }

    sess.recipe = updatedRecipe;
    sess.codeplug = assembled;
    sess.raw_channels = [...rawAssembled.channels];
    sess.radio_spec = spec;
    sess.notices = notices;

    const primaryWxStations = sess.primary_channels.filter((ch) => channelBand(ch.rxFreq) === "WX");
    const { bandCounts, mapChannels } = computeBandCountsAndMapChannels(
      assembled.channels,
      activeBands,
      primaryWxStations,
    );
    sess.summary_data.band_counts = bandCounts;
    sess.map_data.channels = mapChannels;
    this.workspace.saveSession();

    const endSlot = assembled.channels.length > 0 ? spec.startChannel + assembled.channels.length - 1 : spec.startChannel;
    return this.serializeActivePlan(
      `Targeted ${spec.brand} ${spec.model} • Bands: ${activeBands.join(", ")} • Naming: ${activeNaming} (Slots ${spec.startChannel}..${endSlot})`,
    );
  }

  private handleDeleteChannels(body: Record<string, unknown>): Record<string, unknown> {
    const sess = this.workspace.session;
    if (!sess.codeplug || !sess.recipe || !sess.radio_spec) {
      throw new ApiError(400, "No active codeplug session.");
    }
    const slots = Array.isArray(body.slots) ? body.slots.map((s) => Number(s)).filter(Number.isFinite) : [];
    const selectedSet = new Set(slots);
    if (selectedSet.size === 0) {
      throw new ApiError(400, "No channel slots selected for deletion.");
    }

    const deletedChannels = sess.codeplug.channels.filter((ch) => selectedSet.has(ch.number));
    if (deletedChannels.length === 0) {
      throw new ApiError(404, "Selected channel slot(s) not found.");
    }

    sess.pushUndo(`Delete ${deletedChannels.length} channel(s)`);
    const remaining = sess.codeplug.channels.filter((ch) => !selectedSet.has(ch.number));

    if (sess.raw_channels.length === sess.codeplug.channels.length) {
      sess.raw_channels = sess.raw_channels.filter((_, idx) => !selectedSet.has(sess.codeplug!.channels[idx].number));
    }

    const delKeys = new Set(deletedChannels.map(channelDeleteKey));
    for (const k of delKeys) sess.deleted_keys.add(k);
    if (sess.primary_channels.length > 0) {
      sess.primary_channels = sess.primary_channels.filter((ch) => !delKeys.has(channelDeleteKey(ch)));
    }

    const renumbered = renumberChannels(remaining, sess.radio_spec.startChannel);
    sess.codeplug = { name: sess.codeplug.name, channels: renumbered };

    const primaryWxStations = sess.primary_channels.filter((ch) => channelBand(ch.rxFreq) === "WX");
    const { bandCounts, mapChannels } = computeBandCountsAndMapChannels(
      renumbered,
      sess.recipe.radio_target.bands,
      primaryWxStations,
    );
    sess.summary_data.band_counts = bandCounts;
    sess.map_data.channels = mapChannels;
    this.workspace.saveSession();

    return this.serializeActivePlan(
      `Deleted ${deletedChannels.length} channel(s). Renumbered ${renumbered.length} remaining channel(s).`,
    );
  }

  private handleUndoDelete(): Record<string, unknown> {
    const sess = this.workspace.session;
    if (!sess.codeplug || !sess.recipe || !sess.radio_spec) {
      throw new ApiError(400, "No active codeplug session.");
    }
    const snap = sess.popUndo();
    if (!snap) {
      throw new ApiError(400, "Nothing to undo.");
    }

    const restored = renumberChannels(snap.channels, sess.radio_spec.startChannel);
    sess.codeplug = { name: sess.codeplug.name, channels: restored };
    sess.raw_channels = [...snap.raw_channels];
    sess.primary_channels = [...snap.primary_channels];
    sess.deleted_keys = new Set(snap.deleted_keys);

    const primaryWxStations = sess.primary_channels.filter((ch) => channelBand(ch.rxFreq) === "WX");
    const { bandCounts, mapChannels } = computeBandCountsAndMapChannels(
      restored,
      sess.recipe.radio_target.bands,
      primaryWxStations,
    );
    sess.summary_data.band_counts = bandCounts;
    sess.map_data.channels = mapChannels;
    this.workspace.saveSession();

    return this.serializeActivePlan(`Undid: ${snap.label} (${restored.length} channels).`);
  }

  private handleEditChannel(slot: number, body: Record<string, unknown>): Record<string, unknown> {
    const sess = this.workspace.session;
    if (!sess.codeplug || !sess.recipe || !sess.radio_spec) {
      throw new ApiError(400, "No active codeplug session.");
    }
    const spec = sess.radio_spec;
    const idx = sess.codeplug.channels.findIndex((c) => c.number === slot);
    if (idx < 0) {
      throw new ApiError(404, `Channel slot ${slot} not found.`);
    }

    const cur = sess.codeplug.channels[idx];
    sess.pushUndo(`Edit slot #${slot} (${cur.name})`);

    const rx =
      body.rxFreq !== undefined && body.rxFreq !== null
        ? Number(Number(body.rxFreq).toFixed(5))
        : cur.rxFreq;
    if (!Number.isFinite(rx) || rx <= 0 || rx >= 3000) {
      throw new ApiError(400, "rxFreq must be between 0 and 3000 MHz.");
    }

    let offDir = cur.offsetDir;
    if (body.offsetDir !== undefined && body.offsetDir !== null) {
      const cand = String(body.offsetDir).trim();
      if (cand !== "off" && cand !== "+" && cand !== "-") {
        throw new ApiError(400, "offsetDir must be 'off', '+', or '-'.");
      }
      offDir = cand;
    }

    let offVal =
      body.offset !== undefined && body.offset !== null
        ? Number(Math.abs(Number(body.offset)).toFixed(5))
        : cur.offset;
    let tx = rx;
    if (offDir === "+") tx = Number((rx + offVal).toFixed(5));
    else if (offDir === "-") tx = Number((rx - offVal).toFixed(5));
    else offVal = 0.0;

    let newName = cur.name;
    if (body.name !== undefined && body.name !== null) {
      let cleaned = cleanSingleLine(body.name, 64);
      if (!cleaned) throw new ApiError(400, "Channel LCD name cannot be empty.");
      if (!spec.allowDots) cleaned = cleaned.replace(/\./g, "");
      if (!spec.allowSpaces) cleaned = cleaned.replace(/ /g, "");
      newName = cleaned.slice(0, spec.maxNameLength);
    }

    let toneMode = cur.toneMode;
    if (body.toneMode !== undefined && body.toneMode !== null) {
      const cand = String(body.toneMode).trim();
      if (!["None", "Tone", "TSQL", "DCS", "DTCS"].includes(cand)) {
        throw new ApiError(400, "Invalid toneMode.");
      }
      toneMode = cand;
    }

    let ctcss = cur.ctcss;
    let rxCtcss = cur.rxCtcss;
    let dcs = cur.dcs;
    let rxDcs = cur.rxDcs;
    if (toneMode === "None") {
      ctcss = "None";
      rxCtcss = "None";
      dcs = "None";
      rxDcs = "None";
    } else if (toneMode === "Tone" || toneMode === "TSQL") {
      if (body.ctcss !== undefined && body.ctcss !== null) {
        ctcss = cleanSingleLine(body.ctcss, 12) || "88.5";
      } else if (ctcss === "None") {
        ctcss = "88.5";
      }
      rxCtcss = toneMode === "TSQL" ? ctcss : "None";
      dcs = "None";
      rxDcs = "None";
    } else if (toneMode === "DCS" || toneMode === "DTCS") {
      if (body.dcs !== undefined && body.dcs !== null) {
        dcs = cleanSingleLine(body.dcs, 12).replace(/^[Dd]+/, "") || "023";
      } else if (dcs === "None") {
        dcs = "023";
      }
      rxDcs = dcs;
      ctcss = "None";
      rxCtcss = "None";
    }

    const modeVal = body.mode ? cleanSingleLine(body.mode, 12).toUpperCase() : cur.mode;
    let powerVal = cur.power;
    if (body.power !== undefined && body.power !== null) {
      const pRaw = cleanSingleLine(body.power, 12);
      const pCap = pRaw ? pRaw[0].toUpperCase() + pRaw.slice(1).toLowerCase() : "";
      if (pCap === "High" || pCap === "Mid" || pCap === "Low") powerVal = pCap;
    }

    const edited: RadioChannel = {
      ...cur,
      name: newName,
      callsign:
        body.callsign !== undefined ? cleanSingleLine(body.callsign, 16).toUpperCase() || null : cur.callsign,
      rxFreq: rx,
      txFreq: tx,
      offset: offVal,
      offsetDir: offDir,
      mode: modeVal,
      power: powerVal,
      toneMode,
      ctcss,
      rxCtcss,
      dcs,
      rxDcs,
      city: body.city !== undefined ? cleanSingleLine(body.city, 64) || null : cur.city,
      state: body.state !== undefined ? cleanSingleLine(body.state, 8).toUpperCase() || null : cur.state,
      comment: body.comment !== undefined ? cleanSingleLine(body.comment, 240) : cur.comment,
    };

    const updatedChannels = [...sess.codeplug.channels];
    updatedChannels[idx] = edited;
    sess.codeplug = { name: sess.codeplug.name, channels: updatedChannels };
    if (idx < sess.raw_channels.length) sess.raw_channels[idx] = edited;

    const { bandCounts, mapChannels } = computeBandCountsAndMapChannels(
      updatedChannels,
      sess.recipe.radio_target.bands,
    );
    sess.summary_data.band_counts = bandCounts;
    sess.map_data.channels = mapChannels;
    this.workspace.saveSession();

    return this.serializeActivePlan(`Updated channel slot #${slot} (${edited.name}).`);
  }

  private handleChannelNetLoggerPreset(slot: number): Record<string, unknown> {
    const cp = this.workspace.session.codeplug;
    if (!cp) throw new ApiError(400, "No active codeplug session.");
    const ch = cp.channels.find((c) => c.number === slot);
    if (!ch) throw new ApiError(404, `Channel slot ${slot} not found.`);

    const simplex = channelIsSimplex(ch);
    const toneParts: string[] = [];
    if (!simplex && (ch.offsetDir === "+" || ch.offsetDir === "-") && ch.offset > 0) {
      toneParts.push(`${ch.offsetDir}${ch.offset.toFixed(3)} MHz`);
    }
    if ((ch.toneMode === "Tone" || ch.toneMode === "TSQL") && ch.ctcss && ch.ctcss !== "None") {
      toneParts.push(`PL ${ch.ctcss}`);
    } else if ((ch.toneMode === "DCS" || ch.toneMode === "DTCS") && ch.dcs && ch.dcs !== "None") {
      toneParts.push(`DCS ${ch.dcs}`);
    } else if (simplex) {
      toneParts.push("Simplex");
    }

    return {
      slot,
      preset: {
        name: ch.name,
        frequency: `${ch.rxFreq.toFixed(4)} MHz`,
        band: channelBand(ch.rxFreq),
        mode: ch.mode,
        tone_offset: toneParts.join(" / ") || "CSQ",
        callsign: ch.callsign || "",
        location: [ch.city, ch.state].filter(Boolean).join(", "),
      },
    };
  }

  private handleExpandDmr(): Record<string, unknown> {
    const sess = this.workspace.session;
    if (!sess.codeplug || !sess.recipe || !sess.radio_spec) {
      throw new ApiError(400, "No active codeplug session.");
    }
    const expanded: RadioChannel[] = [];
    let dmrCount = 0;
    for (const ch of sess.codeplug.channels) {
      if (ch.mode.toUpperCase() === "DMR") {
        dmrCount++;
        expanded.push(...RadioIdProvider.duplicateChannelForTalkgroups(ch));
      } else {
        expanded.push(ch);
      }
    }

    let msg = "No DMR channels present in current codeplug.";
    if (dmrCount > 0) {
      sess.pushUndo(`Expand ${dmrCount} DMR channel(s)`);
      const renumbered = renumberChannels(expanded, sess.radio_spec.startChannel);
      sess.codeplug = { name: sess.codeplug.name, channels: renumbered };
      const { bandCounts, mapChannels } = computeBandCountsAndMapChannels(renumbered, sess.recipe.radio_target.bands);
      sess.summary_data.band_counts = bandCounts;
      sess.map_data.channels = mapChannels;
      this.workspace.saveSession();
      msg = `Expanded ${dmrCount} DMR channel(s) across standard Talkgroups (${renumbered.length} total).`;
    }
    return this.serializeActivePlan(msg);
  }

  private handleCodeplugReport(): Record<string, unknown> {
    const sess = this.workspace.session;
    if (!sess.codeplug || !sess.recipe || !sess.radio_spec) {
      throw new ApiError(400, "No active codeplug session.");
    }
    const summary = sess.summary_data || {};
    const bandCounts = (summary.band_counts as Record<string, number>) || {};
    const channels = sess.codeplug.channels;
    const repeaterCnt = channels.filter((c) => c.specialType === "REPEATERS").length;
    const simplexCnt = channels.filter((c) => channelIsSimplex(c)).length;
    const dmrCnt = channels.filter((c) => c.mode.toUpperCase() === "DMR").length;
    const opCall = this.workspace.prefsMgr.preferences.callsign;
    const reportText = buildPocketReportText(sess.recipe, sess.codeplug, sess.radio_spec, summary, opCall);

    return {
      name: sess.codeplug.name,
      mode: sess.recipe.mode,
      description: sess.recipe.description,
      generated_at: utcNowIso(),
      operator: opCall,
      radio: `${sess.radio_spec.brand} ${sess.radio_spec.model}`,
      radio_id: sess.radio_spec.id,
      max_channels: sess.radio_spec.maxChannels,
      lcd_limit: sess.radio_spec.maxNameLength,
      programmer: sess.recipe.radio_target.programmer_format || sess.radio_spec.programmerType,
      naming_format: sess.recipe.radio_target.naming_format,
      coverage: summary.subtitle || "",
      states: summary.states || [],
      kpis: {
        total_channels: channels.length,
        capacity_pct: Number(((channels.length / Math.max(sess.radio_spec.maxChannels, 1)) * 100).toFixed(1)),
        repeaters: repeaterCnt,
        simplex: simplexCnt,
        dmr: dmrCnt,
        bands_active: Object.values(bandCounts).filter((v) => v > 0).length,
      },
      channels: channels.map(serializeChannel),
      text: reportText,
      filename: `${sanitizeFilename(sess.codeplug.name, "codeplug")}_pocket_card.txt`,
    };
  }

  private handleCodeplugExport(body: Record<string, unknown>): RouterResponse {
    const sess = this.workspace.session;
    if (!sess.codeplug || !sess.radio_spec) {
      throw new ApiError(400, "No active codeplug to export.");
    }
    let rawName = cleanSingleLine(body.filename ?? "codeplug.csv", 140) || "codeplug.csv";
    if (!rawName.toLowerCase().endsWith(".csv")) rawName += ".csv";
    const safeName = sanitizeFilename(rawName, "codeplug.csv");

    const programmer = cleanSingleLine(body.programmer_type ?? "CHIRP", 32).toUpperCase() || "CHIRP";
    const csvContent = exportCodeplugCsv(sess.codeplug.channels, sess.radio_spec, programmer);

    // Best-effort archive copy into local exports/ dir
    try {
      const outDir = getExportsDir();
      fs.mkdirSync(outDir, { recursive: true });
      const dest = safeChildPath(outDir, safeName);
      fs.writeFileSync(dest, csvContent, "utf-8");
    } catch {
      // Best-effort only
    }

    return textDownloadResponse(csvContent, "text/csv; charset=utf-8", safeName);
  }

  private handleSaveTemplate(body: Record<string, unknown>): Record<string, unknown> {
    const cleanId = sanitizeSlug(String(body.id ?? ""), "");
    if (!cleanId) throw new ApiError(400, "Template ID slug is required.");

    const rawChannels = Array.isArray(body.channels) ? body.channels : [];
    const items: TemplateChannelItem[] = rawChannels.map((raw, idx) => {
      const item = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
      const rx = Number(Number(item.rxFreq).toFixed(5));
      if (!Number.isFinite(rx) || rx <= 0 || rx >= 3000) {
        throw new ApiError(400, `Channel #${idx + 1} has an invalid rxFreq.`);
      }
      const offDirRaw = String(item.offsetDir ?? "off").trim();
      const offDir = offDirRaw === "+" || offDirRaw === "-" ? offDirRaw : "off";
      let offVal = Number(Math.abs(Number(item.offset ?? 0)).toFixed(5)) || 0;
      let tx = rx;
      if (offDir === "+") tx = Number((rx + offVal).toFixed(5));
      else if (offDir === "-") tx = Number((rx - offVal).toFixed(5));
      else offVal = 0;

      const modeVal = cleanSingleLine(item.mode ?? "FM", 16).toUpperCase() || "FM";
      const pRaw = cleanSingleLine(item.power ?? "High", 16);
      const pCap = pRaw ? pRaw[0].toUpperCase() + pRaw.slice(1).toLowerCase() : "High";
      const powerVal = pCap === "High" || pCap === "Mid" || pCap === "Low" ? pCap : "High";

      const tModeRaw = String(item.toneMode ?? "None").trim();
      const tMode = ["None", "Tone", "TSQL", "DCS"].includes(tModeRaw) ? tModeRaw : "None";
      const tVal = cleanSingleLine(item.toneVal ?? "None", 16) || "None";

      let ctcss = "None";
      let rxCtcss = "None";
      let dcs = "None";
      let rxDcs = "None";
      if (tMode === "Tone" || tMode === "TSQL") {
        ctcss = tVal.toLowerCase() !== "none" ? tVal : "88.5";
        rxCtcss = tMode === "TSQL" ? ctcss : "None";
      } else if (tMode === "DCS") {
        dcs = tVal.toLowerCase() !== "none" ? tVal.replace(/^[Dd]+/, "") : "023";
        rxDcs = dcs;
      }

      return {
        name: cleanSingleLine(item.name ?? `CH ${idx + 1}`, 64) || `CH ${idx + 1}`,
        rxFreq: rx,
        txFreq: tx,
        offset: offDir !== "off" ? offVal : null,
        offsetDir: offDir,
        mode: modeVal,
        power: powerVal,
        toneMode: tMode,
        ctcss,
        rxCtcss,
        dcs,
        rxDcs,
        dcsPolarity: "NN",
        bandwidth: "25KHz",
        specialType: null,
        comment: cleanSingleLine(item.comment ?? "", 240),
      };
    });

    const tpl: PresetTemplateFile = {
      id: cleanId,
      name: cleanSingleLine(body.name ?? cleanId, 100) || cleanId,
      description: cleanSingleLine(body.description ?? "", 240),
      tagText: cleanSingleLine(body.tagText ?? "PRESET", 24).toUpperCase() || "PRESET",
      tagColorHex: cleanSingleLine(body.tagColorHex ?? "#00BCD4", 16) || "#00BCD4",
      channels: items,
      fileName: null,
      rawCsvContent: null,
    };

    const dest = this.workspace.templateMgr.saveTemplate(tpl);
    return {
      saved: true,
      id: cleanId,
      filename: path.basename(dest),
      message: `Saved ${items.length} channel(s) to template ${path.basename(dest)}`,
      templates: this.serializeTemplates(),
    };
  }

  private handleImportTemplate(body: Record<string, unknown>): Record<string, unknown> {
    const cleanId = sanitizeSlug(String(body.id ?? ""), "");
    if (!cleanId) throw new ApiError(400, "Template ID slug is required.");

    const filename = String(body.filename ?? "imported.csv").toLowerCase();
    const content = String(body.content ?? "");
    let tpl: PresetTemplateFile;

    if (filename.endsWith(".yaml") || filename.endsWith(".yml")) {
      const parsed = parseYamlText(content, filename);
      tpl = validateTemplateFile({ id: cleanId, name: body.name || cleanId, ...parsed }, filename);
    } else if (filename.endsWith(".json") || content.trimStart().startsWith("{") || content.trimStart().startsWith("[")) {
      tpl = parseNetLoggerJsonToTemplate({
        cleanId,
        name: String(body.name ?? cleanId),
        description: String(body.description ?? ""),
        tagText: String(body.tagText ?? "NETLOG"),
        rawJson: content,
      });
    } else {
      tpl = validateTemplateFile(
        {
          id: cleanId,
          name: cleanSingleLine(body.name ?? cleanId, 100) || cleanId,
          description: cleanSingleLine(body.description ?? "", 240),
          tagText: cleanSingleLine(body.tagText ?? "CUSTOM", 24).toUpperCase() || "CUSTOM",
          tagColorHex: "#4CAF50",
          rawCsvContent: content,
        },
        filename,
      );
    }

    this.workspace.templateMgr.saveTemplate(tpl);
    return {
      imported: true,
      id: tpl.id,
      message: `Imported template '${tpl.name}' (${tpl.channels.length} channels).`,
      templates: this.serializeTemplates(),
    };
  }

  private handleSaveRadio(body: Record<string, unknown>): Record<string, unknown> {
    const cleanId = sanitizeSlug(String(body.id ?? ""), "");
    if (!cleanId) throw new ApiError(400, "Unique radio ID slug is required.");

    const existingCols = this.workspace.radioMgr.hasRadio(cleanId)
      ? this.workspace.radioMgr.getRadio(cleanId).columns
      : [];

    const bands = Array.isArray(body.supportedBands)
      ? body.supportedBands.map((b) => cleanSingleLine(b, 24)).filter(Boolean)
      : ["2m", "70cm", "WX"];
    const modes = Array.isArray(body.supportedModes)
      ? body.supportedModes.map((m) => cleanSingleLine(m, 16).toUpperCase()).filter(Boolean)
      : ["FM"];

    const brand = cleanSingleLine(body.brand ?? "", 64);
    const model = cleanSingleLine(body.model ?? "", 64);
    if (!brand || !model) throw new ApiError(400, "Brand and model are required.");

    const spec: TargetRadioSpec = {
      id: cleanId,
      brand,
      model,
      description: cleanSingleLine(body.description ?? `${brand} ${model}`, 200) || `${brand} ${model}`,
      startChannel: Number(body.startChannel ?? 1) === 0 ? 0 : 1,
      maxChannels: Math.max(1, Math.min(10000, Math.round(Number(body.maxChannels ?? 128) || 128))),
      maxNameLength: Math.max(1, Math.min(32, Math.round(Number(body.maxNameLength ?? 8) || 8))),
      programmerType: cleanSingleLine(body.programmerType ?? "RT_SYSTEMS", 32).toUpperCase() || "RT_SYSTEMS",
      allowDots: body.allowDots !== undefined ? Boolean(body.allowDots) : true,
      allowSpaces: body.allowSpaces !== undefined ? Boolean(body.allowSpaces) : true,
      allowedSpecialChars: " -_./#",
      supportedBands: bands.length > 0 ? bands : ["2m", "70cm", "WX"],
      supportedModes: modes.length > 0 ? modes : ["FM"],
      columns: existingCols,
    };

    this.workspace.radioMgr.saveUserRadio(spec);
    return {
      saved: true,
      radio: spec,
      message: `Saved radio specification ${spec.brand} ${spec.model}`,
      radios: this.serializeRadios(),
    };
  }

  private async handleUpdateCheck(): Promise<Record<string, unknown>> {
    if (this.workspace.offlineOnly) {
      return {
        current_version: this.appVersion,
        latest_version: this.appVersion,
        update_available: false,
        install_mode: "electron",
        message: "Offline mode — update check skipped.",
      };
    }
    try {
      const res = await fetch("https://api.github.com/repos/edenhare/w5cdn-radio-planner/releases/latest", {
        headers: {
          "User-Agent": `W5CDN-RadioPlanner/${this.appVersion}`,
          Accept: "application/vnd.github+json",
        },
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) {
        return {
          current_version: this.appVersion,
          latest_version: this.appVersion,
          update_available: false,
          install_mode: "electron",
          message: `Release check returned HTTP ${res.status}.`,
        };
      }
      const data = (await res.json()) as { tag_name?: string; html_url?: string };
      const latest = String(data.tag_name || this.appVersion).replace(/^v/i, "");
      const updateAvailable = compareSemver(latest, this.appVersion) > 0;
      return {
        current_version: this.appVersion,
        latest_version: latest,
        update_available: updateAvailable,
        release_url: sanitizeHttpUrl(data.html_url) ?? null,
        install_mode: "electron",
        message: updateAvailable
          ? `Version v${latest} is available on GitHub Releases.`
          : `You are running the latest version (v${this.appVersion}).`,
      };
    } catch {
      return {
        current_version: this.appVersion,
        latest_version: this.appVersion,
        update_available: false,
        install_mode: "electron",
        message: "Could not reach GitHub Releases (offline).",
      };
    }
  }
}
