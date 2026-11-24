/**
 * Strict YAML loader, clean YAML serializer, and human-friendly schema validators
 * for hand-edited Radio Profiles, Channel Templates, Recipes, Preferences, and Tokens.
 */

import fs from "node:fs";
import YAML from "yaml";
import {
  ApiTokens,
  DEFAULT_PANEL_LAYOUT,
  PresetTemplateFile,
  RadioPlannerRecipe,
  RecipeMode,
  TargetRadioSpec,
  TemplateChannelItem,
  UserPreferences,
  VALID_COCKPIT_THEMES,
  VALID_MONO_FONTS,
  VALID_UI_FONTS,
  sanitizePanelLayout,
} from "./types";

export class YamlDiagnosticError extends Error {
  filePath?: string;
  line?: number;
  column?: number;
  snippet?: string;
  suggestion?: string;
  issues: string[];

  constructor(opts: {
    message: string;
    filePath?: string;
    line?: number;
    column?: number;
    snippet?: string;
    suggestion?: string;
    issues?: string[];
  }) {
    super(opts.message);
    this.name = "YamlDiagnosticError";
    this.filePath = opts.filePath;
    this.line = opts.line;
    this.column = opts.column;
    this.snippet = opts.snippet;
    this.suggestion = opts.suggestion;
    this.issues = opts.issues ?? [];
  }

  formatReport(): string {
    const lines: string[] = [];
    if (this.filePath) lines.push(`File: ${this.filePath}`);
    if (this.line !== undefined) {
      lines.push(`Location: Line ${this.line}${this.column !== undefined ? `, Column ${this.column}` : ""}`);
    }
    lines.push(`Error: ${this.message}`);
    if (this.issues.length > 0) {
      lines.push("Validation issues:");
      for (const issue of this.issues) {
        lines.push(`  - ${issue}`);
      }
    }
    if (this.snippet) {
      lines.push("Context:");
      lines.push(this.snippet);
    }
    if (this.suggestion) {
      lines.push(`Tip: ${this.suggestion}`);
    }
    return lines.join("\n");
  }

  toPayload(): Record<string, unknown> {
    return {
      error: this.message,
      file: this.filePath ?? null,
      line: this.line ?? null,
      column: this.column ?? null,
      snippet: this.snippet ?? null,
      suggestion: this.suggestion ?? null,
      issues: this.issues,
      formatted: this.formatReport(),
    };
  }
}

export function buildLineSnippet(text: string, lineNumber: number, radius = 2): string {
  const rows = text.replace(/\r\n/g, "\n").split("\n");
  const start = Math.max(0, lineNumber - 1 - radius);
  const end = Math.min(rows.length, lineNumber + radius);
  const out: string[] = [];
  for (let i = start; i < end; i++) {
    const marker = i + 1 === lineNumber ? ">> " : "   ";
    out.push(`${marker}${String(i + 1).padStart(3, " ")} | ${rows[i]}`);
  }
  return out.join("\n");
}

export function parseYamlText(text: string, filePath?: string): Record<string, unknown> {
  if (!text || !text.trim()) {
    throw new YamlDiagnosticError({
      message: "YAML content is empty.",
      filePath,
      suggestion: "Provide a valid YAML mapping (key: value pairs).",
    });
  }

  const doc = YAML.parseDocument(text, { prettyErrors: true });
  if (doc.errors.length > 0) {
    const first = doc.errors[0];
    const linePos = first.linePos?.[0];
    const line = linePos?.line;
    const column = linePos?.col;
    const rawMsg = first.message || "Invalid YAML syntax";
    let suggestion = "Check indentation (use spaces, never tabs) and make sure quotes/colons are balanced.";
    if (text.includes("\t")) {
      suggestion = "YAML does not allow tab characters for indentation. Replace tabs with 2 spaces.";
    }
    throw new YamlDiagnosticError({
      message: `YAML syntax error: ${rawMsg.split("\n")[0]}`,
      filePath,
      line,
      column,
      snippet: line ? buildLineSnippet(text, line) : undefined,
      suggestion,
    });
  }

  const parsed: unknown = doc.toJS();
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new YamlDiagnosticError({
      message: "Top-level YAML document must be a key-value mapping (object).",
      filePath,
      suggestion: "Start the file with named keys such as 'id:', 'name:', or 'mode:'.",
    });
  }
  return parsed as Record<string, unknown>;
}

export function loadYamlFile(filePath: string): Record<string, unknown> {
  if (!fs.existsSync(filePath)) {
    throw new YamlDiagnosticError({
      message: `YAML file not found: ${filePath}`,
      filePath,
    });
  }
  const text = fs.readFileSync(filePath, "utf-8");
  return parseYamlText(text, filePath);
}

export function dumpYamlText(data: unknown, headerComment?: string): string {
  const body = YAML.stringify(data, {
    indent: 2,
    lineWidth: 120,
  });
  if (headerComment && headerComment.trim()) {
    const commented = headerComment
      .trim()
      .split("\n")
      .map((line) => (line.startsWith("#") ? line : `# ${line}`))
      .join("\n");
    return `${commented}\n\n${body}`;
  }
  return body;
}

function asString(v: unknown, fallback = ""): string {
  if (v === null || v === undefined) return fallback;
  return String(v).trim();
}

function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v.trim());
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function asStringArray(v: unknown): string[] {
  if (Array.isArray(v)) {
    return v.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof v === "string") {
    return v
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

/**
 * Strictly validate a TargetRadioSpec object (used when loading or hand-importing radio YAML).
 */
export function validateRadioSpec(raw: Record<string, unknown>, sourceLabel?: string): TargetRadioSpec {
  const issues: string[] = [];

  const id = asString(raw.id);
  const brand = asString(raw.brand);
  const model = asString(raw.model);
  const description = asString(raw.description || `${brand} ${model}`.trim());

  if (!id) issues.push("Field 'id' is required (e.g. 'my_custom_radio').");
  else if (!/^[a-zA-Z0-9_-]+$/.test(id)) {
    issues.push("Field 'id' may only contain letters, numbers, underscores, and hyphens.");
  }
  if (!brand) issues.push("Field 'brand' is required (e.g. 'Baofeng', 'Yaesu', 'Icom').");
  if (!model) issues.push("Field 'model' is required (e.g. '5RM', 'FT-60R').");

  const startChannel = raw.startChannel !== undefined ? asNumber(raw.startChannel) : 1;
  if (startChannel === null || !Number.isInteger(startChannel) || startChannel < 0 || startChannel > 1000) {
    issues.push("Field 'startChannel' must be an integer between 0 and 1000.");
  }

  const maxChannels = raw.maxChannels !== undefined ? asNumber(raw.maxChannels) : 128;
  if (maxChannels === null || !Number.isInteger(maxChannels) || maxChannels < 1 || maxChannels > 100000) {
    issues.push("Field 'maxChannels' must be an integer between 1 and 100000.");
  }

  const maxNameLength = raw.maxNameLength !== undefined ? asNumber(raw.maxNameLength) : 10;
  if (maxNameLength === null || !Number.isInteger(maxNameLength) || maxNameLength < 1 || maxNameLength > 64) {
    issues.push("Field 'maxNameLength' must be an integer between 1 and 64.");
  }

  const allowDots = raw.allowDots !== undefined ? Boolean(raw.allowDots) : true;
  const allowSpaces = raw.allowSpaces !== undefined ? Boolean(raw.allowSpaces) : true;
  const allowedSpecialChars =
    typeof raw.allowedSpecialChars === "string" ? raw.allowedSpecialChars : " -_./#";

  const supportedBands = raw.supportedBands !== undefined ? asStringArray(raw.supportedBands) : ["2m", "70cm"];
  if (supportedBands.length === 0) {
    issues.push("Field 'supportedBands' must contain at least one band (e.g. ['2m', '70cm']).");
  }

  const supportedModes = raw.supportedModes !== undefined ? asStringArray(raw.supportedModes) : ["FM", "AM"];
  if (supportedModes.length === 0) {
    issues.push("Field 'supportedModes' must contain at least one mode (e.g. ['FM', 'AM']).");
  }

  const programmerType = asString(raw.programmerType || "RT_SYSTEMS").toUpperCase();
  const validProgrammers = new Set(["CHIRP", "RT_SYSTEMS", "VENDOR_CPS", "GENERIC_CSV"]);
  if (!validProgrammers.has(programmerType)) {
    issues.push(`Field 'programmerType' must be one of: CHIRP, RT_SYSTEMS, VENDOR_CPS, GENERIC_CSV (got '${programmerType}').`);
  }

  const columns = raw.columns !== undefined ? asStringArray(raw.columns) : [];

  if (issues.length > 0) {
    throw new YamlDiagnosticError({
      message: "Radio profile YAML failed schema validation.",
      filePath: sourceLabel,
      issues,
      suggestion: "Export an existing radio profile YAML to see a valid template, then re-import.",
    });
  }

  return {
    id,
    brand,
    model,
    description: description || `${brand} ${model}`.trim(),
    startChannel: startChannel ?? 1,
    maxChannels: maxChannels ?? 128,
    maxNameLength: maxNameLength ?? 10,
    allowDots,
    allowSpaces,
    allowedSpecialChars,
    supportedBands,
    supportedModes,
    programmerType,
    columns,
  };
}

function parseLegacyRawCsv(rawCsv: string): TemplateChannelItem[] {
  const lines = rawCsv.trim().split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
  const out: TemplateChannelItem[] = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = lines[i].split(",").map((v) => v.trim().replace(/^"|"$/g, ""));
    const row: Record<string, string> = {};
    headers.forEach((h, idx) => {
      row[h] = vals[idx] ?? "";
    });
    const name = row["Name"] || row["Channel Name"] || "CH";
    const rxStr = row["RX Frequency"] || row["Frequency"] || row["Receive Frequency"] || "146.520";
    const txStr = row["TX Frequency"] || row["Transmit Frequency"] || rxStr;
    const rx = Number(rxStr);
    const tx = Number(txStr);
    if (!Number.isFinite(rx) || !Number.isFinite(tx)) continue;
    out.push({
      name,
      rxFreq: rx,
      txFreq: tx,
      offset: Math.abs(rx - tx),
      offsetDir: Math.abs(rx - tx) > 1e-5 ? (tx > rx ? "+" : "-") : "off",
      mode: row["Mode"] || row["Operating Mode"] || "FM",
      power: row["Power"] || row["Tx Power"] || "High",
      toneMode: "None",
      ctcss: "None",
      rxCtcss: "None",
      dcs: "None",
      rxDcs: "None",
      dcsPolarity: "NN",
      bandwidth: "25KHz",
      specialType: null,
      comment: row["Comment"] || "",
    });
  }
  return out;
}

/**
 * Strictly validate a PresetTemplateFile object (used for built-in, user, and hand-edited YAML import).
 */
export function validateTemplateFile(raw: Record<string, unknown>, sourceLabel?: string): PresetTemplateFile {
  const issues: string[] = [];

  const id = asString(raw.id);
  const name = asString(raw.name);
  const description = asString(raw.description);
  const tagText = asString(raw.tagText || "PRESET") || "PRESET";
  const tagColorHex = asString(raw.tagColorHex || "#00BCD4") || "#00BCD4";
  const fileName = raw.fileName ? asString(raw.fileName) : null;
  const rawCsvContent = typeof raw.rawCsvContent === "string" ? raw.rawCsvContent : null;

  if (!id) issues.push("Field 'id' is required (e.g. 'local_ares_nets').");
  if (!name) issues.push("Field 'name' is required (e.g. 'Local ARES Nets').");
  if (tagColorHex && !/^#[0-9a-fA-F]{3,8}$/.test(tagColorHex)) {
    issues.push(`Field 'tagColorHex' must be a hex color like '#00BCD4' (got '${tagColorHex}').`);
  }

  const channels: TemplateChannelItem[] = [];
  if (Array.isArray(raw.channels)) {
    raw.channels.forEach((entry, idx) => {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        issues.push(`channels[${idx}] must be an object with 'name' and 'rxFreq'.`);
        return;
      }
      const ch = entry as Record<string, unknown>;
      const chName = asString(ch.name);
      const rxFreq = asNumber(ch.rxFreq);
      if (!chName) issues.push(`channels[${idx}].name is required.`);
      if (rxFreq === null || rxFreq <= 0 || rxFreq > 3000) {
        issues.push(`channels[${idx}].rxFreq must be a positive frequency in MHz (got '${String(ch.rxFreq)}').`);
        return;
      }
      const txFreq = ch.txFreq !== undefined && ch.txFreq !== null ? asNumber(ch.txFreq) : null;
      if (ch.txFreq !== undefined && ch.txFreq !== null && (txFreq === null || txFreq <= 0 || txFreq > 3000)) {
        issues.push(`channels[${idx}].txFreq must be a valid frequency in MHz.`);
      }
      const offset = ch.offset !== undefined && ch.offset !== null ? asNumber(ch.offset) : null;
      const offsetDir = asString(ch.offsetDir || "off") || "off";
      if (!["+", "-", "off", ""].includes(offsetDir)) {
        issues.push(`channels[${idx}].offsetDir must be '+', '-', or 'off' (got '${offsetDir}').`);
      }

      channels.push({
        name: chName || `CH ${idx + 1}`,
        rxFreq,
        txFreq,
        offset,
        offsetDir: offsetDir || "off",
        mode: asString(ch.mode || "FM") || "FM",
        power: asString(ch.power || "High") || "High",
        toneMode: asString(ch.toneMode || "None") || "None",
        ctcss: asString(ch.ctcss || "None") || "None",
        rxCtcss: asString(ch.rxCtcss || "None") || "None",
        dcs: asString(ch.dcs || "None") || "None",
        rxDcs: asString(ch.rxDcs || "None") || "None",
        dcsPolarity: asString(ch.dcsPolarity || "NN") || "NN",
        bandwidth: asString(ch.bandwidth || "25KHz") || "25KHz",
        specialType: ch.specialType ? asString(ch.specialType) : null,
        comment: asString(ch.comment),
      });
    });
  } else if (rawCsvContent) {
    channels.push(...parseLegacyRawCsv(rawCsvContent));
  } else if (raw.channels !== undefined) {
    issues.push("Field 'channels' must be a YAML list of channel entries.");
  }

  if (issues.length > 0) {
    throw new YamlDiagnosticError({
      message: "Template YAML failed schema validation.",
      filePath: sourceLabel,
      issues,
      suggestion: "Export an existing template YAML to see the exact schema, then re-import.",
    });
  }

  return {
    id,
    name,
    description,
    tagText,
    tagColorHex,
    channels,
    fileName,
    rawCsvContent,
  };
}

const VALID_RECIPE_MODES = new Set<RecipeMode>([
  "ROUTE_CORRIDOR",
  "PROXIMITY_SEARCH",
  "AVIATION_PLANNER",
  "PRESET_TEMPLATES",
]);

/**
 * Strictly validate a RadioPlannerRecipe object (for saved recipes & hand-edited YAML import).
 */
export function validateRecipe(raw: Record<string, unknown>, sourceLabel?: string): RadioPlannerRecipe {
  const issues: string[] = [];

  const modeRaw = asString(raw.mode).toUpperCase() as RecipeMode;
  if (!VALID_RECIPE_MODES.has(modeRaw)) {
    issues.push(
      `Field 'mode' must be one of ROUTE_CORRIDOR, PROXIMITY_SEARCH, AVIATION_PLANNER, PRESET_TEMPLATES (got '${asString(raw.mode)}').`,
    );
  }

  const version = asString(raw.version || "1.0") || "1.0";
  const name = asString(raw.name || "RadioPlanner-Run") || "RadioPlanner-Run";
  const description = asString(raw.description);

  let corridor = null;
  if (raw.corridor && typeof raw.corridor === "object" && !Array.isArray(raw.corridor)) {
    const c = raw.corridor as Record<string, unknown>;
    const waypoints = asStringArray(c.waypoints);
    const width = c.corridor_width_miles !== undefined ? asNumber(c.corridor_width_miles) : 25.0;
    if (width === null || width <= 0) {
      issues.push("Field 'corridor.corridor_width_miles' must be > 0.");
    }
    if (waypoints.length < 2) {
      issues.push("Field 'corridor.waypoints' must contain at least 2 waypoints.");
    }
    corridor = { waypoints, corridor_width_miles: width ?? 25.0 };
  }

  let proximity = null;
  if (raw.proximity && typeof raw.proximity === "object" && !Array.isArray(raw.proximity)) {
    const p = raw.proximity as Record<string, unknown>;
    const center = asString(p.center_location);
    const radius = p.radius_miles !== undefined ? asNumber(p.radius_miles) : 50.0;
    if (!center) issues.push("Field 'proximity.center_location' is required.");
    if (radius === null || radius <= 0) issues.push("Field 'proximity.radius_miles' must be > 0.");
    proximity = { center_location: center, radius_miles: radius ?? 50.0 };
  }

  let aviation = null;
  if (raw.aviation && typeof raw.aviation === "object" && !Array.isArray(raw.aviation)) {
    const a = raw.aviation as Record<string, unknown>;
    const center = asString(a.center_location);
    const radius = a.radius_miles !== undefined ? asNumber(a.radius_miles) : 35.0;
    if (!center) issues.push("Field 'aviation.center_location' is required.");
    if (radius === null || radius <= 0) issues.push("Field 'aviation.radius_miles' must be > 0.");
    aviation = { center_location: center, radius_miles: radius ?? 35.0 };
  }

  if (modeRaw === "ROUTE_CORRIDOR" && (!corridor || corridor.waypoints.length < 2)) {
    issues.push("ROUTE_CORRIDOR requires a 'corridor' section with at least 2 waypoints.");
  } else if (modeRaw === "PROXIMITY_SEARCH" && (!proximity || !proximity.center_location)) {
    issues.push("PROXIMITY_SEARCH requires a 'proximity' section with 'center_location'.");
  } else if (modeRaw === "AVIATION_PLANNER" && (!aviation || !aviation.center_location)) {
    issues.push("AVIATION_PLANNER requires an 'aviation' section with 'center_location'.");
  }

  const rtRaw =
    raw.radio_target && typeof raw.radio_target === "object" && !Array.isArray(raw.radio_target)
      ? (raw.radio_target as Record<string, unknown>)
      : {};
  const radio_target = {
    radio_id: rtRaw.radio_id ? asString(rtRaw.radio_id) : null,
    programmer_format: rtRaw.programmer_format ? asString(rtRaw.programmer_format) : null,
    include_simplex: rtRaw.include_simplex !== undefined ? Boolean(rtRaw.include_simplex) : true,
    bands: rtRaw.bands !== undefined ? asStringArray(rtRaw.bands) : ["2m", "70cm", "WX"],
    modes: rtRaw.modes !== undefined ? asStringArray(rtRaw.modes) : ["FM", "AM"],
    repeater_access: rtRaw.repeater_access !== undefined ? asStringArray(rtRaw.repeater_access) : ["OPEN"],
    naming_format: asString(rtRaw.naming_format || "CITY_FREQ") || "CITY_FREQ",
  };

  const sequence_order =
    raw.sequence_order !== undefined
      ? asStringArray(raw.sequence_order)
      : ["TEMPLATE:builtin_calling_channels", "ROUTE_PLAN", "TEMPLATE:builtin_noaa_wx_channels"];

  const expRaw =
    raw.export && typeof raw.export === "object" && !Array.isArray(raw.export)
      ? (raw.export as Record<string, unknown>)
      : {};
  const expCfg = {
    output_dir: asString(expRaw.output_dir || "./exports") || "./exports",
    filename_pattern: expRaw.filename_pattern ? asString(expRaw.filename_pattern) : null,
  };

  if (issues.length > 0) {
    throw new YamlDiagnosticError({
      message: "Recipe YAML failed schema validation.",
      filePath: sourceLabel,
      issues,
      suggestion: "Verify that 'mode' and its matching section (corridor / proximity / aviation) are valid.",
    });
  }

  return {
    version,
    mode: modeRaw,
    name,
    description,
    corridor,
    proximity,
    aviation,
    radio_target,
    sequence_order,
    export: expCfg,
  };
}

export function defaultUserPreferences(): UserPreferences {
  return {
    callsign: "N0CALL",
    operatorName: "Radio Operator",
    primaryDmrId: null,
    distanceUnit: "MILES",
    language: "ENGLISH",
    defaultRadioId: null,
    colorTheme: "shack-dark",
    fontFamily: "system",
    monoFont: "cascadia",
    fontSize: "MEDIUM",
    uiFontSize: 14,
    lcdFontSize: 15,
    panelLayout: sanitizePanelLayout(DEFAULT_PANEL_LAYOUT),
    channelNamingFormat: "CITY_FREQ",
    repeaterAccess: ["OPEN"],
    repeaterMaxAgeDays: 30,
    webPort: 8000,
  };
}

export function normalizeUserPreferences(raw: Record<string, unknown>): UserPreferences {
  const base = defaultUserPreferences();

  const callsignRaw = asString(raw.callsign ?? base.callsign).toUpperCase();
  const callsign = callsignRaw || "N0CALL";

  const operatorName = asString(raw.operatorName ?? base.operatorName) || "Radio Operator";
  const primaryDmrId = raw.primaryDmrId ? asString(raw.primaryDmrId) : null;

  const distLow = asString(raw.distanceUnit ?? base.distanceUnit).toLowerCase();
  const distanceUnit = ["k", "km", "kilometers", "kilometer"].includes(distLow) ? "KILOMETERS" : "MILES";

  const langMap: Record<string, string> = {
    "1": "ENGLISH",
    "2": "SPANISH",
    "3": "FRENCH",
    "4": "GERMAN",
    ENGLISH: "ENGLISH",
    SPANISH: "SPANISH",
    FRENCH: "FRENCH",
    GERMAN: "GERMAN",
  };
  const language = langMap[asString(raw.language ?? base.language).toUpperCase()] ?? "ENGLISH";

  const defaultRadioId = raw.defaultRadioId ? asString(raw.defaultRadioId) : null;

  const themeRaw = asString(raw.colorTheme ?? base.colorTheme);
  const themeNumMap: Record<string, string> = { "1": "DARK", "2": "LIGHT", "3": "HIGH_CONTRAST" };
  let colorTheme = "shack-dark";
  if (themeRaw in themeNumMap) {
    colorTheme = themeNumMap[themeRaw];
  } else if ((VALID_COCKPIT_THEMES as readonly string[]).includes(themeRaw.toLowerCase())) {
    colorTheme = themeRaw.toLowerCase();
  } else if (["DARK", "LIGHT", "HIGH_CONTRAST"].includes(themeRaw.toUpperCase())) {
    colorTheme = themeRaw.toUpperCase();
  }

  const fontRaw = asString(raw.fontFamily ?? base.fontFamily);
  let fontFamily = "system";
  if ((VALID_UI_FONTS as readonly string[]).includes(fontRaw.toLowerCase())) {
    fontFamily = fontRaw.toLowerCase();
  } else if (["SANS", "MONO", "SERIF", "SYSTEM"].includes(fontRaw.toUpperCase())) {
    fontFamily = fontRaw.toUpperCase();
  }

  const monoLow = asString(raw.monoFont ?? base.monoFont).toLowerCase();
  const monoFont = (VALID_MONO_FONTS as readonly string[]).includes(monoLow) ? monoLow : "cascadia";

  const fontSizeUp = asString(raw.fontSize ?? base.fontSize).toUpperCase();
  const fontSize = ["SMALL", "MEDIUM", "LARGE", "XLARGE"].includes(fontSizeUp) ? fontSizeUp : "MEDIUM";

  const legacyUiSize: Record<string, number> = { SMALL: 12, MEDIUM: 14, LARGE: 17, XLARGE: 20 };
  let uiFontSize = base.uiFontSize;
  const rawUi = raw.uiFontSize;
  if (typeof rawUi === "string" && rawUi.trim().toUpperCase() in legacyUiSize) {
    uiFontSize = legacyUiSize[rawUi.trim().toUpperCase()];
  } else if (rawUi !== undefined) {
    const n = asNumber(rawUi);
    if (n !== null) uiFontSize = Math.max(11, Math.min(22, Math.round(n)));
  }

  let lcdFontSize = base.lcdFontSize;
  if (raw.lcdFontSize !== undefined) {
    const n = asNumber(raw.lcdFontSize);
    if (n !== null) lcdFontSize = Math.max(12, Math.min(26, Math.round(n)));
  }

  const panelLayout = sanitizePanelLayout(raw.panelLayout ?? base.panelLayout);

  const namingMap: Record<string, string> = {
    "1": "CITY_FREQ",
    "2": "CALLSIGN_FREQ",
    "3": "CALLSIGN",
    "4": "CITY",
    "5": "STANDARD",
    CITY_FREQ: "CITY_FREQ",
    CALLSIGN_FREQ: "CALLSIGN_FREQ",
    CALLSIGN: "CALLSIGN",
    CITY: "CITY",
    STANDARD: "STANDARD",
  };
  const channelNamingFormat =
    namingMap[asString(raw.channelNamingFormat ?? base.channelNamingFormat).toUpperCase()] ?? "CITY_FREQ";

  const validAccess = new Set(["OPEN", "CLOSED", "PRIVATE"]);
  let rawAccessItems: string[] = [];
  if (typeof raw.repeaterAccess === "string") {
    const up = raw.repeaterAccess.trim().toUpperCase();
    rawAccessItems = up === "ALL" ? ["OPEN", "CLOSED", "PRIVATE"] : up.split(",").map((s) => s.trim());
  } else if (Array.isArray(raw.repeaterAccess)) {
    rawAccessItems = raw.repeaterAccess.map((s) => String(s).trim().toUpperCase());
  }
  const filteredAccess = ["OPEN", "CLOSED", "PRIVATE"].filter(
    (k) => validAccess.has(k) && rawAccessItems.includes(k),
  );
  const repeaterAccess = filteredAccess.length > 0 ? filteredAccess : ["OPEN"];

  const maxAgeNum = asNumber(raw.repeaterMaxAgeDays);
  const repeaterMaxAgeDays = maxAgeNum !== null && maxAgeNum >= 1 ? Math.round(maxAgeNum) : 30;

  const portNum = asNumber(raw.webPort);
  const webPort = portNum !== null && portNum >= 1 && portNum <= 65535 ? Math.round(portNum) : 8000;

  return {
    callsign,
    operatorName,
    primaryDmrId,
    distanceUnit,
    language,
    defaultRadioId,
    colorTheme,
    fontFamily,
    monoFont,
    fontSize,
    uiFontSize,
    lcdFontSize,
    panelLayout,
    channelNamingFormat,
    repeaterAccess,
    repeaterMaxAgeDays,
    webPort,
  };
}

export function defaultApiTokens(): ApiTokens {
  return {
    repeaterBookApiKey: null,
    radioIdUsername: null,
    radioIdApiKey: null,
    qrzUsername: null,
    qrzPassword: null,
  };
}

export function normalizeApiTokens(raw: Record<string, unknown>): ApiTokens {
  const norm = (v: unknown): string | null => {
    const s = asString(v);
    return s ? s : null;
  };
  return {
    repeaterBookApiKey: norm(raw.repeaterBookApiKey),
    radioIdUsername: norm(raw.radioIdUsername),
    radioIdApiKey: norm(raw.radioIdApiKey),
    qrzUsername: norm(raw.qrzUsername),
    qrzPassword: norm(raw.qrzPassword),
  };
}
