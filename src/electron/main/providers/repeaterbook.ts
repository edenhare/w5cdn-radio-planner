/**
 * RepeaterBook Local Cache + Live REST Provider + Offline Amateur/GMRS Fallback.
 */

import fs from "node:fs";
import path from "node:path";
import { RadioChannel, createRadioChannel } from "../../shared/types";
import { getCacheDir, resolveResourcesDir } from "../paths";

interface StateGeoData {
  US_STATE_ABBR: Record<string, string>;
  FIPS_STATE_ABBR: Record<string, string>;
  STATE_TO_FIPS: Record<string, string>;
  US_STATE_REGIONS: Record<string, [number, number, number, number]>;
}

interface RawRepeaterRecord {
  [key: string]: unknown;
}

let stateGeoCache: StateGeoData | null = null;
let offlineRepeatersCache: RawRepeaterRecord[] | null = null;
let gmrsRepeatersCache: RawRepeaterRecord[] | null = null;
let wxStationsCache: RawRepeaterRecord[] | null = null;

function loadStateGeo(): StateGeoData {
  if (stateGeoCache) return stateGeoCache;
  const filePath = path.join(resolveResourcesDir(), "state_geo.json");
  stateGeoCache = JSON.parse(fs.readFileSync(filePath, "utf-8")) as StateGeoData;
  return stateGeoCache;
}

export function getOfflineRepeaters(): RawRepeaterRecord[] {
  if (offlineRepeatersCache) return offlineRepeatersCache;
  try {
    const filePath = path.join(resolveResourcesDir(), "offline_repeaters.json");
    offlineRepeatersCache = JSON.parse(fs.readFileSync(filePath, "utf-8")) as RawRepeaterRecord[];
  } catch {
    offlineRepeatersCache = [];
  }
  return offlineRepeatersCache;
}

export function getGmrsRepeaters(): RawRepeaterRecord[] {
  if (gmrsRepeatersCache) return gmrsRepeatersCache;
  try {
    const filePath = path.join(resolveResourcesDir(), "gmrs_repeaters.json");
    gmrsRepeatersCache = JSON.parse(fs.readFileSync(filePath, "utf-8")) as RawRepeaterRecord[];
  } catch {
    gmrsRepeatersCache = [];
  }
  return gmrsRepeatersCache;
}

export function getOfflineWxStations(): RadioChannel[] {
  if (!wxStationsCache) {
    try {
      const filePath = path.join(resolveResourcesDir(), "offline_wx_stations.json");
      wxStationsCache = JSON.parse(fs.readFileSync(filePath, "utf-8")) as RawRepeaterRecord[];
    } catch {
      wxStationsCache = [];
    }
  }
  return wxStationsCache.map((rec, idx) => {
    const rxFreq = Number(rec.rxFreq ?? rec.Frequency ?? 162.55);
    const city = String(rec.city ?? "").trim() || null;
    const state = String(rec.state ?? "").trim() || null;
    const callsign = String(rec.callsign ?? "").trim() || null;
    const lat = rec.lat !== undefined ? Number(rec.lat) : null;
    const lon = rec.lon !== undefined ? Number(rec.lon) : null;
    const name = String(rec.name ?? (city ? `${city} WX` : `WX ${rxFreq.toFixed(3)}`)).trim();
    const comment =
      String(rec.comment ?? "").trim() ||
      [callsign ? `NOAA NWR ${callsign}` : "NOAA Weather Radio", city && state ? `${city}, ${state}` : city]
        .filter(Boolean)
        .join(" - ");
    return createRadioChannel({
      number: idx + 1,
      name,
      callsign,
      rxFreq,
      txFreq: rxFreq,
      offset: 0,
      offsetDir: "off",
      mode: "FM",
      power: "Low",
      toneMode: "None",
      ctcss: "None",
      rxCtcss: "None",
      dcs: "None",
      rxDcs: "None",
      city,
      state,
      lat: lat !== null && Number.isFinite(lat) ? lat : null,
      lon: lon !== null && Number.isFinite(lon) ? lon : null,
      specialType: "WX",
      comment,
    });
  });
}

export function resolveStateCode(stateInput: string): string | null {
  const geo = loadStateGeo();
  const s = (stateInput || "").trim().toUpperCase();
  if (!s) return null;
  if (s in geo.STATE_TO_FIPS) return s;
  const low = s.toLowerCase();
  for (const [name, abbr] of Object.entries(geo.US_STATE_ABBR)) {
    if (name.toLowerCase() === low) return abbr;
  }
  if (s in geo.FIPS_STATE_ABBR) return geo.FIPS_STATE_ABBR[s];
  return null;
}

export function extractStateFromText(text: string): string | null {
  if (!text) return null;
  const geo = loadStateGeo();
  const parts = text.split(",").map((p) => p.trim());
  for (let i = parts.length - 1; i >= 0; i--) {
    const tokens = parts[i].split(/\s+/);
    for (const tok of tokens) {
      const code = resolveStateCode(tok);
      if (code) return code;
    }
    const whole = resolveStateCode(parts[i]);
    if (whole) return whole;
  }
  const upper = text.toUpperCase();
  for (const [name, abbr] of Object.entries(geo.US_STATE_ABBR)) {
    if (upper.includes(name.toUpperCase())) return abbr;
  }
  return null;
}

export function identifyStatesForPointAndRadius(lat: number, lon: number, radiusMiles: number): string[] {
  const geo = loadStateGeo();
  const degLat = radiusMiles / 69.0;
  const degLon = radiusMiles / (69.0 * Math.max(0.2, Math.cos((lat * Math.PI) / 180)));

  const minLat = lat - degLat;
  const maxLat = lat + degLat;
  const minLon = lon - degLon;
  const maxLon = lon + degLon;

  const states: string[] = [];
  for (const [abbr, [sMinLat, sMaxLat, sMinLon, sMaxLon]] of Object.entries(geo.US_STATE_REGIONS)) {
    const latOverlap = maxLat >= sMinLat && minLat <= sMaxLat;
    const lonOverlap = maxLon >= sMinLon && minLon <= sMaxLon;
    if (latOverlap && lonOverlap) {
      states.push(abbr);
    }
  }
  return states.sort();
}

export function identifyStatesForRoute(
  routePoints: Array<[number, number]>,
  corridorMiles: number,
  waypointNames: string[] = [],
): string[] {
  const found = new Set<string>();
  for (const name of waypointNames) {
    const st = extractStateFromText(name);
    if (st) found.add(st);
  }
  for (const [lat, lon] of routePoints) {
    for (const st of identifyStatesForPointAndRadius(lat, lon, Math.max(15, corridorMiles))) {
      found.add(st);
    }
  }
  // Interpolate midpoints for long highway segments
  for (let i = 0; i < routePoints.length - 1; i++) {
    const [aLat, aLon] = routePoints[i];
    const [bLat, bLon] = routePoints[i + 1];
    const steps = 6;
    for (let s = 1; s < steps; s++) {
      const f = s / steps;
      const mLat = aLat + f * (bLat - aLat);
      const mLon = aLon + f * (bLon - aLon);
      for (const st of identifyStatesForPointAndRadius(mLat, mLon, Math.max(15, corridorMiles))) {
        found.add(st);
      }
    }
  }
  return Array.from(found).sort();
}

export function identifyStatesForProximity(
  lat: number,
  lon: number,
  radiusMiles: number,
  centerText = "",
): string[] {
  const found = new Set<string>(identifyStatesForPointAndRadius(lat, lon, radiusMiles));
  const st = extractStateFromText(centerText);
  if (st) found.add(st);
  return Array.from(found).sort();
}

function normalizeRepeaterRecord(raw: RawRepeaterRecord, index: number, allowedUseSet: Set<string>): RadioChannel | null {
  const useVal = String(raw.Use ?? raw.use ?? "OPEN").trim().toUpperCase();
  if (allowedUseSet.size > 0 && !allowedUseSet.has(useVal)) {
    return null;
  }

  const rxFreq = Number(raw.Frequency ?? raw.rxFreq ?? raw.frequency);
  if (!Number.isFinite(rxFreq) || rxFreq <= 0) return null;

  const inputRaw = raw["Input Freq"] ?? raw.txFreq ?? raw.input_freq;
  let txFreq = Number(inputRaw);
  if (!Number.isFinite(txFreq) || txFreq <= 0) {
    txFreq = rxFreq;
  }

  const diff = txFreq - rxFreq;
  const offset = Math.abs(diff);
  const offsetDir = offset > 1e-4 ? (diff > 0 ? "+" : "-") : "off";

  const callsign = String(raw.Callsign ?? raw.callsign ?? "").trim() || null;
  const city = String(raw["Nearest City"] ?? raw.city ?? "").trim() || null;
  const state = String(raw.State ?? raw.state ?? "").trim() || null;
  const lat = raw.Lat !== undefined ? Number(raw.Lat) : raw.lat !== undefined ? Number(raw.lat) : null;
  const lon = raw.Long !== undefined ? Number(raw.Long) : raw.lon !== undefined ? Number(raw.lon) : null;

  const pl = String(raw.PL ?? raw.ctcss ?? "").trim();
  const tsq = String(raw.TSQ ?? raw.rxCtcss ?? "").trim();
  let toneMode = "None";
  let ctcss = "None";
  let rxCtcss = "None";
  let dcs = "None";
  let rxDcs = "None";

  if (pl && pl.toUpperCase() !== "NONE" && pl !== "0") {
    if (pl.toUpperCase().startsWith("D")) {
      toneMode = "DCS";
      dcs = pl.slice(1).replace(/\D/g, "") || "023";
      rxDcs = dcs;
    } else if (!Number.isNaN(Number(pl))) {
      toneMode = "Tone";
      ctcss = Number(pl).toFixed(1);
    }
  }
  if (tsq && tsq.toUpperCase() !== "NONE" && tsq !== "0") {
    if (!Number.isNaN(Number(tsq))) {
      toneMode = "TSQL";
      rxCtcss = Number(tsq).toFixed(1);
      if (ctcss === "None") ctcss = rxCtcss;
    }
  }

  const isDmr =
    String(raw.DMR ?? "").toUpperCase() === "YES" ||
    String(raw.mode ?? "").toUpperCase() === "DMR" ||
    raw["DMR Color Code"] !== undefined;
  const mode = isDmr ? "DMR" : String(raw.mode ?? "FM").trim().toUpperCase() || "FM";
  const colorCodeRaw = raw["DMR Color Code"] ?? raw.colorCode;
  const colorCode = colorCodeRaw !== undefined && colorCodeRaw !== null && colorCodeRaw !== "" ? Number(colorCodeRaw) : null;

  const isGmrs = rxFreq >= 462.0 && rxFreq <= 468.0;
  const specialType = isGmrs ? "GMRS" : "REPEATERS";

  const landmark = String(raw.Landmark ?? raw.comment ?? "").trim();
  const displayName = city ? `${city} ${rxFreq.toFixed(2)}` : callsign || `RPT ${rxFreq.toFixed(2)}`;
  const commentParts = [callsign, city && state ? `${city}, ${state}` : city, landmark].filter(Boolean);

  return createRadioChannel({
    number: index + 1,
    name: displayName,
    callsign,
    rxFreq,
    txFreq,
    offset,
    offsetDir,
    mode,
    power: "High",
    toneMode,
    ctcss,
    rxCtcss,
    dcs,
    rxDcs,
    city,
    state,
    lat: lat !== null && Number.isFinite(lat) ? lat : null,
    lon: lon !== null && Number.isFinite(lon) ? lon : null,
    specialType,
    colorCode: colorCode !== null && Number.isFinite(colorCode) ? colorCode : null,
    timeSlot: isDmr ? 1 : null,
    comment: commentParts.join(" - "),
  });
}

export interface CachedStateFileInfo {
  state: string;
  filename: string;
  date: string;
  age_days: number;
  count: number;
}

export class RepeaterBookProvider {
  private cacheDir: string;
  apiKey: string | null;
  lastStatus: string;
  private maxAgeDays: number;
  private offlineOnly: boolean;

  constructor(opts?: {
    cacheDir?: string;
    apiKey?: string | null;
    maxAgeDays?: number;
    offlineOnly?: boolean;
  }) {
    this.cacheDir = opts?.cacheDir ?? getCacheDir();
    this.apiKey = opts?.apiKey ?? null;
    this.lastStatus = this.apiKey ? "CONFIGURED" : "NO_KEY";
    this.maxAgeDays = opts?.maxAgeDays ?? 30;
    this.offlineOnly = opts?.offlineOnly ?? false;
  }

  hasApiKey(): boolean {
    return Boolean(this.apiKey && this.apiKey.trim().length > 0);
  }

  listCachedStateFiles(): CachedStateFileInfo[] {
    if (!fs.existsSync(this.cacheDir)) return [];
    const results: CachedStateFileInfo[] = [];
    const files = fs
      .readdirSync(this.cacheDir)
      .filter((f) => /^rb_[A-Z]{2}_\d{4}-\d{2}-\d{2}\.json$/.test(f))
      .sort()
      .reverse();
    const seen = new Set<string>();
    for (const f of files) {
      const m = f.match(/^rb_([A-Z]{2})_(\d{4}-\d{2}-\d{2})\.json$/);
      if (!m || seen.has(m[1])) continue;
      seen.add(m[1]);
      const fullPath = path.join(this.cacheDir, f);
      try {
        const stat = fs.statSync(fullPath);
        const ageDays = Math.max(0, Math.round((Date.now() - stat.mtimeMs) / (1000 * 60 * 60 * 24)));
        const parsed = JSON.parse(fs.readFileSync(fullPath, "utf-8"));
        const count = Array.isArray(parsed) ? parsed.length : 0;
        results.push({
          state: m[1],
          filename: f,
          date: m[2],
          age_days: ageDays,
          count,
        });
      } catch {
        // Ignore corrupt cache entry
      }
    }
    return results.sort((a, b) => a.state.localeCompare(b.state));
  }

  private findFreshCacheFile(stateAbbr: string): string | null {
    if (!fs.existsSync(this.cacheDir)) return null;
    const prefix = `rb_${stateAbbr.toUpperCase()}_`;
    const files = fs
      .readdirSync(this.cacheDir)
      .filter((f) => f.startsWith(prefix) && f.endsWith(".json"))
      .sort()
      .reverse();

    if (files.length === 0) return null;
    const latest = path.join(this.cacheDir, files[0]);
    try {
      const stat = fs.statSync(latest);
      const ageDays = (Date.now() - stat.mtimeMs) / (1000 * 60 * 60 * 24);
      if (ageDays <= this.maxAgeDays) {
        return latest;
      }
    } catch {
      return null;
    }
    return null;
  }

  private async downloadStateRepeaters(stateAbbr: string): Promise<RawRepeaterRecord[] | null> {
    if (this.offlineOnly) return null;
    const geo = loadStateGeo();
    const fips = geo.STATE_TO_FIPS[stateAbbr.toUpperCase()];
    if (!fips) return null;

    const headers: Record<string, string> = {
      "User-Agent": "W5CDN-RadioPlanner/0.2.0 (Amateur Radio Codeplug Studio)",
      Accept: "application/json",
    };
    if (this.apiKey) {
      headers["X-RB-App-Token"] = this.apiKey;
    }

    try {
      const url = `https://www.repeaterbook.com/api/export.php?state_id=${encodeURIComponent(fips)}`;
      const res = await fetch(url, { headers, signal: AbortSignal.timeout(8000) });
      if (!res.ok) return null;
      const body = (await res.json()) as { results?: RawRepeaterRecord[] };
      if (!body || !Array.isArray(body.results)) return null;

      fs.mkdirSync(this.cacheDir, { recursive: true });
      const dateStr = new Date().toISOString().slice(0, 10);
      const outPath = path.join(this.cacheDir, `rb_${stateAbbr.toUpperCase()}_${dateStr}.json`);
      fs.writeFileSync(outPath, JSON.stringify(body.results), "utf-8");
      return body.results;
    } catch {
      return null;
    }
  }

  async getRepeatersForStates(
    states: string[],
    opts?: { allowedUse?: string[]; includeGmrs?: boolean },
  ): Promise<{ channels: RadioChannel[]; sources: string[]; warnings: string[] }> {
    const allowedUse = new Set((opts?.allowedUse ?? ["OPEN"]).map((u) => u.trim().toUpperCase()));
    const includeGmrs = opts?.includeGmrs ?? true;

    const rawRecords: RawRepeaterRecord[] = [];
    const sources: string[] = [];
    const warnings: string[] = [];

    const normalizedStates = Array.from(
      new Set(states.map((s) => resolveStateCode(s)).filter((s): s is string => Boolean(s))),
    );

    let gotLiveOrCache = false;
    for (const st of normalizedStates) {
      const cacheFile = this.findFreshCacheFile(st);
      if (cacheFile) {
        try {
          const parsed = JSON.parse(fs.readFileSync(cacheFile, "utf-8")) as RawRepeaterRecord[];
          if (Array.isArray(parsed) && parsed.length > 0) {
            rawRecords.push(...parsed);
            sources.push(`cache:${st}`);
            gotLiveOrCache = true;
            continue;
          }
        } catch {
          // Fall through to live/offline
        }
      }

      const live = await this.downloadStateRepeaters(st);
      if (live && live.length > 0) {
        rawRecords.push(...live);
        sources.push(`live:${st}`);
        gotLiveOrCache = true;
      }
    }

    // Always merge offline dataset when live/cache wasn't available for all requested states
    if (!gotLiveOrCache || normalizedStates.length === 0) {
      const offline = getOfflineRepeaters();
      rawRecords.push(...offline);
      sources.push("offline_fallback");
      if (normalizedStates.length > 0 && !this.offlineOnly) {
        warnings.push(
          `Using built-in offline repeater dataset (${offline.length} repeaters) for ${normalizedStates.join(", ")}.`,
        );
      }
    }

    if (includeGmrs) {
      rawRecords.push(...getGmrsRepeaters());
    }

    const channels: RadioChannel[] = [];
    rawRecords.forEach((rec, idx) => {
      const ch = normalizeRepeaterRecord(rec, idx, allowedUse);
      if (ch) channels.push(ch);
    });

    return { channels, sources, warnings };
  }
}
