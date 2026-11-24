/**
 * Shared Common Internal Representation (CIR) types, constants, and API contracts
 * for W5CDN RadioPlanner (Electron + TypeScript).
 */

export const VALID_COCKPIT_THEMES = [
  "shack-dark",
  "night-red",
  "amber-crt",
  "forest-eoc",
  "daylight",
  "paper-warm",
  "eoc-light",
  "sky-breeze",
  "high-contrast",
] as const;

export type CockpitTheme = (typeof VALID_COCKPIT_THEMES)[number];

export const LEGACY_THEME_TO_COCKPIT: Record<string, CockpitTheme> = {
  DARK: "shack-dark",
  LIGHT: "daylight",
  HIGH_CONTRAST: "high-contrast",
};

export const VALID_UI_FONTS = ["system", "humanist", "geometric", "serif", "mono"] as const;
export const VALID_MONO_FONTS = ["cascadia", "consolas", "courier"] as const;
export const VALID_DOCK_POSITIONS = ["left", "right", "top", "bottom"] as const;

export interface PanelLayoutItem {
  visible: boolean;
  position?: string;
}

export type PanelLayout = Record<string, PanelLayoutItem>;

export const DEFAULT_PANEL_LAYOUT: PanelLayout = {
  builder: { visible: true, position: "left" },
  map: { visible: true, position: "right" },
  summary: { visible: true, position: "right" },
  templates: { visible: false, position: "right" },
  radios: { visible: false, position: "right" },
  vfo: { visible: true },
  footer: { visible: true },
};

export const NAMING_FORMAT_OPTIONS: Array<[string, string, string]> = [
  ["CITY_FREQ", "City + Freq", "Compact city + last digits of freq (e.g. 'Tyler 7.20')"],
  ["CALLSIGN_FREQ", "Callsign + Freq", "Repeater callsign + freq shorthand (e.g. 'W5ETX 7.20')"],
  ["CALLSIGN", "Callsign Only", "Repeater callsign only — ideal for 6-char LCDs (e.g. 'W5ETX')"],
  ["CITY", "City Only", "Municipality name only (e.g. 'Tyler')"],
  ["STANDARD", "Standard Full", "Full city + frequency condensed to LCD width (e.g. 'Tyler 147.20')"],
];

export const AVIATION_NAMING_FORMAT_OPTIONS: Array<[string, string, string]> = [
  ["IDENT_TYPE", "ICAO + Service", "Airport ICAO + service type (e.g. 'KTYR ATIS')"],
  ["CITY_TYPE", "City + Service", "City name + service type (e.g. 'Tyler ATIS')"],
  ["IDENT_FREQ", "ICAO + Freq", "Airport ICAO + frequency shorthand (e.g. 'KTYR 6.25')"],
  ["IDENT_ONLY", "ICAO Only", "Airport identifier only (e.g. 'KTYR')"],
];

export const BAND_COLORS: Record<string, string> = {
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

export const RING_COLORS = [
  "#10b981",
  "#06b6d4",
  "#3b82f6",
  "#a855f7",
  "#f59e0b",
  "#f43f5e",
  "#ec4899",
  "#84cc16",
] as const;

export interface RadioChannel {
  number: number;
  name: string;
  callsign: string | null;
  rxFreq: number;
  txFreq: number;
  offset: number;
  offsetDir: string;
  mode: string;
  power: string;
  toneMode: string;
  ctcss: string;
  rxCtcss: string;
  dcs: string;
  rxDcs: string;
  dcsPolarity: string;
  bandwidth: string;
  city: string | null;
  state: string | null;
  lat: number | null;
  lon: number | null;
  specialType: string;
  colorCode: number | null;
  timeSlot: number | null;
  dmrId: string | null;
  contact: string | null;
  comment: string;
}

export interface TargetRadioSpec {
  id: string;
  brand: string;
  model: string;
  description: string;
  startChannel: number;
  maxChannels: number;
  maxNameLength: number;
  allowDots: boolean;
  allowSpaces: boolean;
  allowedSpecialChars: string;
  supportedBands: string[];
  supportedModes: string[];
  programmerType: string;
  columns: string[];
}

export interface TemplateChannelItem {
  name: string;
  rxFreq: number;
  txFreq: number | null;
  offset: number | null;
  offsetDir: string;
  mode: string;
  power: string;
  toneMode: string;
  ctcss: string;
  rxCtcss: string;
  dcs: string;
  rxDcs: string;
  dcsPolarity: string;
  bandwidth: string;
  specialType: string | null;
  comment: string;
}

export interface PresetTemplateFile {
  id: string;
  name: string;
  description: string;
  tagText: string;
  tagColorHex: string;
  channels: TemplateChannelItem[];
  fileName: string | null;
  rawCsvContent: string | null;
}

export interface AviationFrequency {
  type: string;
  description: string;
  frequencyMhz: number;
}

export interface AirfieldRecord {
  ident: string;
  name: string;
  latitude: number;
  longitude: number;
  municipality: string;
  state: string;
  frequencies: AviationFrequency[];
}

export interface CorridorConfig {
  waypoints: string[];
  corridor_width_miles: number;
}

export interface ProximityConfig {
  center_location: string;
  radius_miles: number;
}

export interface AviationConfig {
  center_location: string;
  radius_miles: number;
}

export interface RadioTargetConfig {
  radio_id: string | null;
  programmer_format: string | null;
  include_simplex: boolean;
  bands: string[];
  modes: string[];
  repeater_access: string[];
  naming_format: string;
}

export interface ExportConfig {
  output_dir: string;
  filename_pattern: string | null;
}

export type RecipeMode =
  | "ROUTE_CORRIDOR"
  | "PROXIMITY_SEARCH"
  | "AVIATION_PLANNER"
  | "PRESET_TEMPLATES";

export interface RadioPlannerRecipe {
  version: string;
  mode: RecipeMode;
  name: string;
  description: string;
  corridor: CorridorConfig | null;
  proximity: ProximityConfig | null;
  aviation: AviationConfig | null;
  radio_target: RadioTargetConfig;
  sequence_order: string[];
  export: ExportConfig;
}

export interface UserPreferences {
  callsign: string;
  operatorName: string;
  primaryDmrId: string | null;
  distanceUnit: string;
  language: string;
  defaultRadioId: string | null;
  colorTheme: string;
  fontFamily: string;
  monoFont: string;
  fontSize: string;
  uiFontSize: number;
  lcdFontSize: number;
  panelLayout: PanelLayout;
  channelNamingFormat: string;
  repeaterAccess: string[];
  repeaterMaxAgeDays: number;
  webPort: number;
}

export interface ApiTokens {
  repeaterBookApiKey: string | null;
  radioIdUsername: string | null;
  radioIdApiKey: string | null;
  qrzUsername: string | null;
  qrzPassword: string | null;
}

export interface WaypointCoord {
  name: string;
  lat: number;
  lon: number;
}

export interface ActivePlanSession {
  mode: string;
  name: string;
  radio_id: string;
  naming_format: string;
  waypoints: WaypointCoord[];
  center_location: string;
  center_lat: number | null;
  center_lon: number | null;
  corridor_width_miles: number;
  radius_miles: number;
  channels: RadioChannel[];
  route_coords: Array<[number, number]>;
  sequence_order: string[];
  bands: string[];
  modes: string[];
  repeater_access: string[];
  include_simplex: boolean;
  stats: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function createRadioChannel(partial: Partial<RadioChannel> & { name: string; rxFreq: number }): RadioChannel {
  const rxFreq = Number(partial.rxFreq);
  const txFreq = partial.txFreq !== undefined && partial.txFreq !== null ? Number(partial.txFreq) : rxFreq;
  let offset = partial.offset !== undefined && partial.offset !== null ? Number(partial.offset) : Math.abs(rxFreq - txFreq);
  if (!Number.isFinite(offset)) offset = 0.0;
  let offsetDir = partial.offsetDir ?? "off";
  if (offsetDir === "off" && offset > 1e-5) {
    offsetDir = txFreq > rxFreq ? "+" : "-";
  }
  return {
    number: partial.number ?? 1,
    name: String(partial.name),
    callsign: partial.callsign ?? null,
    rxFreq,
    txFreq,
    offset,
    offsetDir,
    mode: partial.mode ?? "FM",
    power: partial.power ?? "High",
    toneMode: partial.toneMode ?? "None",
    ctcss: partial.ctcss ?? "None",
    rxCtcss: partial.rxCtcss ?? "None",
    dcs: partial.dcs ?? "None",
    rxDcs: partial.rxDcs ?? "None",
    dcsPolarity: partial.dcsPolarity ?? "NN",
    bandwidth: partial.bandwidth ?? "25KHz",
    city: partial.city ?? null,
    state: partial.state ?? null,
    lat: partial.lat !== undefined && partial.lat !== null ? Number(partial.lat) : null,
    lon: partial.lon !== undefined && partial.lon !== null ? Number(partial.lon) : null,
    specialType: partial.specialType ?? "REPEATERS",
    colorCode: partial.colorCode !== undefined && partial.colorCode !== null ? Number(partial.colorCode) : null,
    timeSlot: partial.timeSlot !== undefined && partial.timeSlot !== null ? Number(partial.timeSlot) : null,
    dmrId: partial.dmrId ?? null,
    contact: partial.contact ?? null,
    comment: partial.comment ?? "",
  };
}

export function templateItemToRadioChannel(
  item: TemplateChannelItem,
  number: number,
  defaultSpecialType = "CUSTOM",
  tag = "",
): RadioChannel {
  const txFreq = item.txFreq !== null && item.txFreq !== undefined ? item.txFreq : item.rxFreq;
  const offset = item.offset !== null && item.offset !== undefined ? item.offset : Math.abs(item.rxFreq - txFreq);
  let offsetDir = item.offsetDir || "off";
  if (offsetDir === "off" && offset > 1e-5) {
    offsetDir = txFreq > item.rxFreq ? "+" : "-";
  }
  const specType = item.specialType || defaultSpecialType;
  let commentStr = item.comment || "";
  if (tag && !commentStr.includes(`[${tag}]`)) {
    commentStr = `[${tag}] ${commentStr}`.trim();
  }
  return createRadioChannel({
    number,
    name: item.name,
    rxFreq: item.rxFreq,
    txFreq,
    offset,
    offsetDir,
    mode: item.mode || "FM",
    power: item.power || "High",
    toneMode: item.toneMode || "None",
    ctcss: item.ctcss || "None",
    rxCtcss: item.rxCtcss || "None",
    dcs: item.dcs || "None",
    rxDcs: item.rxDcs || "None",
    dcsPolarity: item.dcsPolarity || "NN",
    bandwidth: item.bandwidth || "25KHz",
    specialType: specType,
    comment: commentStr,
  });
}

export function templateFileToRadioChannels(tpl: PresetTemplateFile): RadioChannel[] {
  let specType = "CUSTOM";
  const idLow = (tpl.id || "").toLowerCase();
  const tagUp = (tpl.tagText || "").toUpperCase();
  if (idLow.includes("calling") || tagUp === "CALLING") {
    specType = "CALLING";
  } else if (idLow.includes("wx") || tagUp === "WX") {
    specType = "WX";
  } else if (idLow.includes("gmrs")) {
    specType = "GMRS";
  }
  return tpl.channels.map((item, idx) => templateItemToRadioChannel(item, idx + 1, specType, tpl.tagText));
}

export function sanitizePanelLayout(raw: unknown): PanelLayout {
  const src = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const out: PanelLayout = {};
  for (const [key, defaults] of Object.entries(DEFAULT_PANEL_LAYOUT)) {
    const rawItem = src[key];
    const item = rawItem && typeof rawItem === "object" && !Array.isArray(rawItem) ? (rawItem as Record<string, unknown>) : {};
    const entry: PanelLayoutItem = {
      visible: typeof item.visible === "boolean" ? item.visible : defaults.visible,
    };
    if (defaults.position !== undefined) {
      const pos = String(item.position ?? defaults.position).trim().toLowerCase();
      entry.position = (VALID_DOCK_POSITIONS as readonly string[]).includes(pos) ? pos : defaults.position;
    }
    out[key] = entry;
  }
  return out;
}

export function resolveCockpitTheme(colorTheme: string): CockpitTheme {
  const upper = (colorTheme || "").trim().toUpperCase();
  if (upper in LEGACY_THEME_TO_COCKPIT) {
    return LEGACY_THEME_TO_COCKPIT[upper];
  }
  const low = (colorTheme || "").trim().toLowerCase();
  return (VALID_COCKPIT_THEMES as readonly string[]).includes(low) ? (low as CockpitTheme) : "shack-dark";
}

export function resolveUiFont(fontFamily: string): string {
  const low = (fontFamily || "").trim().toLowerCase();
  if ((VALID_UI_FONTS as readonly string[]).includes(low)) {
    return low;
  }
  const legacy: Record<string, string> = { sans: "system", system: "system", mono: "mono", serif: "serif" };
  return legacy[low] ?? "system";
}
