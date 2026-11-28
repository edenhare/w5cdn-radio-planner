/**
 * Sequence Organizer & Channel Assembly Engine.
 * Merges sequence blocks (templates + primary plan), filters for radio hardware & bands/modes,
 * deduplicates, condenses LCD names, and renumbers slots starting at radioSpec.startChannel.
 */

import fs from "node:fs";
import path from "node:path";
import { channelBand } from "../../shared/sanitize";
import { RadioChannel, TargetRadioSpec, createRadioChannel } from "../../shared/types";
import { NameCondenser } from "../condenser";
import { resolveResourcesDir } from "../paths";

interface SpecialChannelsResource {
  calling: Array<Partial<RadioChannel> & { name: string; rxFreq: number }>;
  weather: Array<Partial<RadioChannel> & { name: string; rxFreq: number }>;
}

let specialChannelsCache: SpecialChannelsResource | null = null;

function loadSpecialChannels(): SpecialChannelsResource {
  if (specialChannelsCache) return specialChannelsCache;
  try {
    const filePath = path.join(resolveResourcesDir(), "special_channels.json");
    specialChannelsCache = JSON.parse(fs.readFileSync(filePath, "utf-8")) as SpecialChannelsResource;
  } catch {
    specialChannelsCache = { calling: [], weather: [] };
  }
  return specialChannelsCache;
}

export function getNationalCallingChannels(): RadioChannel[] {
  return loadSpecialChannels().calling.map((c) => createRadioChannel(c));
}

export function getNoaaWxChannels(): RadioChannel[] {
  return loadSpecialChannels().weather.map((c) => createRadioChannel(c));
}

export function filterChannelsForRadio(
  channels: RadioChannel[],
  spec: TargetRadioSpec,
  opts?: { allowedBands?: string[] | null; allowedModes?: string[] | null },
): RadioChannel[] {
  const radioBands = new Set((spec.supportedBands || []).map((b) => b.toLowerCase()));
  const radioModes = new Set((spec.supportedModes || []).map((m) => m.toUpperCase()));
  const userBands =
    opts?.allowedBands && opts.allowedBands.length > 0
      ? new Set(opts.allowedBands.map((b) => b.toLowerCase()))
      : null;
  const userModes =
    opts?.allowedModes && opts.allowedModes.length > 0
      ? new Set(opts.allowedModes.map((m) => m.toUpperCase()))
      : null;

  return channels.filter((ch) => {
    const band = channelBand(ch.rxFreq).toLowerCase();
    const isSpecialAlways =
      (ch.specialType === "CALLING" && band !== "gmrs") ||
      ch.specialType === "CUSTOM" ||
      (ch.specialType === "WX" && ch.lat === null && ch.lon === null);

    if (radioBands.size > 0 && !radioBands.has(band)) {
      return false;
    }
    if (userBands && !isSpecialAlways && !userBands.has(band)) {
      return false;
    }

    const modeUp = (ch.mode || "FM").toUpperCase();
    const modeMatchesSet = (set: Set<string>): boolean => {
      if (set.size === 0 || set.has(modeUp)) return true;
      if ((modeUp === "FM" || modeUp === "NFM" || modeUp === "ANALOG") && (set.has("FM") || set.has("ANALOG"))) {
        return true;
      }
      if ((modeUp === "DMR" || modeUp === "DIGITAL") && (set.has("DMR") || set.has("DIGITAL"))) {
        return true;
      }
      return false;
    };

    if (!modeMatchesSet(radioModes)) return false;
    if (userModes && !isSpecialAlways && !modeMatchesSet(userModes)) return false;
    return true;
  });
}

export interface TemplateLookup {
  hasTemplate(id: string): boolean;
  getTemplateChannels(id: string): RadioChannel[];
}

export interface AssembleOptions {
  codeplugName: string;
  sequenceKeys: string[];
  primaryChannels: RadioChannel[];
  targetSpec: TargetRadioSpec;
  customTemplates?: Record<string, RadioChannel[]>;
  templateManager?: TemplateLookup;
  allowedBands?: string[] | null;
  allowedModes?: string[] | null;
  deduplicate?: boolean;
  namingFormat?: string;
}

export class SequenceOrganizer {
  static assemble(opts: AssembleOptions): { name: string; channels: RadioChannel[] } {
    const customMap = opts.customTemplates ?? {};
    const rawCombined: RadioChannel[] = [];

    for (const key of opts.sequenceKeys) {
      if (key === "ROUTE_PLAN" || key === "PROXIMITY_PLAN" || key === "AVIATION_BLOCK") {
        rawCombined.push(...opts.primaryChannels);
      } else if (key in customMap) {
        rawCombined.push(...customMap[key]);
      } else if (key.startsWith("TEMPLATE:")) {
        const tplId = key.slice("TEMPLATE:".length);
        if (opts.templateManager && opts.templateManager.hasTemplate(tplId)) {
          rawCombined.push(...opts.templateManager.getTemplateChannels(tplId));
        } else if (tplId === "calling_channels" || tplId === "builtin_calling_channels") {
          rawCombined.push(...getNationalCallingChannels());
        } else if (tplId === "noaa_wx_channels" || tplId === "builtin_noaa_wx_channels") {
          rawCombined.push(...getNoaaWxChannels());
        }
      }
    }

    let filtered = filterChannelsForRadio(rawCombined, opts.targetSpec, {
      allowedBands: opts.allowedBands,
      allowedModes: opts.allowedModes,
    });

    if (opts.deduplicate !== false) {
      const seen = new Set<string>();
      const unique: RadioChannel[] = [];
      for (const ch of filtered) {
        const chKey = [
          ch.rxFreq.toFixed(4),
          ch.txFreq.toFixed(4),
          ch.toneMode,
          ch.ctcss,
          ch.dcs,
          ch.callsign ?? "",
        ].join("|");
        if (!seen.has(chKey)) {
          seen.add(chKey);
          unique.push(ch);
        }
      }
      filtered = unique;
    }

    const namingFormat = opts.namingFormat ?? "CITY_FREQ";
    const startSlot = Math.max(0, opts.targetSpec.startChannel ?? 1);
    const maxSlots = Math.max(1, opts.targetSpec.maxChannels || 999);
    const condensed = filtered.slice(0, maxSlots).map((ch, idx) => ({
      ...ch,
      number: startSlot + idx,
      name: NameCondenser.condenseChannel(ch, opts.targetSpec, namingFormat),
    }));

    return {
      name: opts.codeplugName,
      channels: condensed,
    };
  }
}
