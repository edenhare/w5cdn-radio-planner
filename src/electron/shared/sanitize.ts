/**
 * Sanitization, frequency-band classification, CSV safety, and path-safety helpers.
 */

import path from "node:path";
import { RadioChannel, TargetRadioSpec } from "./types";

const CONTROL_CHARS_RE = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
const DANGEROUS_CSV_PREFIX_RE = /^[=+\-@\t\r]/;

export function utcNowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function cleanSingleLine(value: unknown, maxLen = 256): string {
  if (value === null || value === undefined) return "";
  const cleaned = String(value).replace(CONTROL_CHARS_RE, "").replace(/[\r\n]+/g, " ").trim();
  return cleaned.length > maxLen ? cleaned.slice(0, maxLen) : cleaned;
}

export function sanitizeText(value: unknown, maxLen = 2000): string {
  if (value === null || value === undefined) return "";
  const cleaned = String(value).replace(CONTROL_CHARS_RE, "").trim();
  return cleaned.length > maxLen ? cleaned.slice(0, maxLen) : cleaned;
}

export function sanitizeFilename(name: string, fallback = "export"): string {
  const cleaned = (name || "")
    .replace(/[\\/:*?"<>|\x00-\x1f]/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^[._]+|[._]+$/g, "");
  return cleaned || fallback;
}

export function sanitizeSlug(raw: string, fallback = "item"): string {
  const slug = (raw || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return slug || fallback;
}

export function sanitizeHttpUrl(rawUrl: unknown): string | null {
  if (typeof rawUrl !== "string") return null;
  const trimmed = rawUrl.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

export function csvSafeCell(value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  if (s && DANGEROUS_CSV_PREFIX_RE.test(s)) {
    return `'${s}`;
  }
  return s;
}

/**
 * Safely resolve a filename inside a base directory, rejecting any path traversal.
 */
export function safeChildPath(baseDir: string, filename: string): string {
  const raw = String(filename || "").trim();
  if (!raw || raw.includes("\0") || raw.includes("/") || raw.includes("\\") || raw === "." || raw === ".." || raw.includes("..")) {
    throw new Error(`Unsafe filename: ${filename}`);
  }
  const resolvedBase = path.resolve(baseDir);
  const resolvedTarget = path.resolve(resolvedBase, raw);
  if (resolvedTarget !== resolvedBase && !resolvedTarget.startsWith(resolvedBase + path.sep)) {
    throw new Error(`Path escapes base directory: ${filename}`);
  }
  return resolvedTarget;
}

export function channelIsSimplex(ch: Pick<RadioChannel, "rxFreq" | "txFreq" | "offsetDir">): boolean {
  return Math.abs(ch.rxFreq - ch.txFreq) < 1e-5 || ch.offsetDir === "off";
}

export function channelBand(rxFreq: number): string {
  if (rxFreq >= 161.0 && rxFreq <= 163.0) return "WX";
  if (rxFreq >= 108.0 && rxFreq <= 137.0) return "Airband";
  if (rxFreq >= 28.0 && rxFreq <= 29.7) return "10m";
  if (rxFreq >= 50.0 && rxFreq <= 54.0) return "6m";
  if (rxFreq >= 144.0 && rxFreq <= 148.0) return "2m";
  if (rxFreq >= 222.0 && rxFreq <= 225.0) return "1.25m";
  if (rxFreq >= 420.0 && rxFreq <= 450.0) return "70cm";
  if (rxFreq >= 462.0 && rxFreq <= 468.0) return "GMRS";
  return "Other";
}

export function cleanFreqDisplay(freq: number): string {
  if (!Number.isFinite(freq)) return "0.00000";
  return freq.toFixed(5);
}

/**
 * Hardware data sanitizer: removes unsupported bands/modes and enforces channel capacity.
 */
export interface SanitizerResult {
  channels: RadioChannel[];
  droppedCount: number;
  droppedDetails: string[];
  truncatedCount: number;
}

export function sanitizeChannelsForRadio(
  channels: RadioChannel[],
  radioSpec: TargetRadioSpec | null,
): SanitizerResult {
  if (!radioSpec) {
    return {
      channels: channels.map((ch, idx) => ({ ...ch, number: idx + 1 })),
      droppedCount: 0,
      droppedDetails: [],
      truncatedCount: 0,
    };
  }

  const supportedBands = new Set((radioSpec.supportedBands || []).map((b) => b.toLowerCase()));
  const supportedModes = new Set((radioSpec.supportedModes || []).map((m) => m.toUpperCase()));

  const kept: RadioChannel[] = [];
  const droppedDetails: string[] = [];

  for (const ch of channels) {
    const band = channelBand(ch.rxFreq);
    const bandAllowed = supportedBands.size === 0 || supportedBands.has(band.toLowerCase());
    if (!bandAllowed) {
      droppedDetails.push(`Dropped '${ch.name}' (${ch.rxFreq.toFixed(4)} MHz): band ${band} not supported by ${radioSpec.brand} ${radioSpec.model}`);
      continue;
    }

    const modeUp = (ch.mode || "FM").toUpperCase();
    const isAnalog = modeUp === "FM" || modeUp === "NFM" || modeUp === "AM" || modeUp === "ANALOG";
    const isDigital = modeUp === "DMR" || modeUp === "DIGITAL";
    let modeAllowed = supportedModes.size === 0 || supportedModes.has(modeUp);
    if (!modeAllowed && isAnalog && (supportedModes.has("ANALOG") || supportedModes.has("FM"))) {
      modeAllowed = modeUp !== "AM" || supportedModes.has("AM");
    }
    if (!modeAllowed && isDigital && (supportedModes.has("DMR") || supportedModes.has("DIGITAL"))) {
      modeAllowed = true;
    }
    if (!modeAllowed) {
      droppedDetails.push(`Dropped '${ch.name}': mode ${ch.mode} not supported by ${radioSpec.brand} ${radioSpec.model}`);
      continue;
    }

    kept.push(ch);
  }

  let truncatedCount = 0;
  const maxSlots = Math.max(1, radioSpec.maxChannels || 999);
  const startChannel = Math.max(0, radioSpec.startChannel ?? 1);
  let finalList = kept;
  if (kept.length > maxSlots) {
    truncatedCount = kept.length - maxSlots;
    finalList = kept.slice(0, maxSlots);
  }

  return {
    channels: finalList.map((ch, idx) => ({ ...ch, number: startChannel + idx })),
    droppedCount: droppedDetails.length,
    droppedDetails,
    truncatedCount,
  };
}
