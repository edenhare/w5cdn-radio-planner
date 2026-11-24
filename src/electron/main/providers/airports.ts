/**
 * Aviation Airfields & Frequencies Provider (offline bundled dataset).
 */

import fs from "node:fs";
import path from "node:path";
import { AirfieldRecord, RadioChannel, createRadioChannel } from "../../shared/types";
import { resolveResourcesDir } from "../paths";
import { haversineMiles } from "./geocoding";

let offlineAirfieldsCache: AirfieldRecord[] | null = null;

export function getOfflineAirfields(): AirfieldRecord[] {
  if (offlineAirfieldsCache) return offlineAirfieldsCache;
  try {
    const filePath = path.join(resolveResourcesDir(), "offline_airfields.json");
    offlineAirfieldsCache = JSON.parse(fs.readFileSync(filePath, "utf-8")) as AirfieldRecord[];
  } catch {
    offlineAirfieldsCache = [];
  }
  return offlineAirfieldsCache;
}

export class AirportsProvider {
  private airfields: AirfieldRecord[];

  constructor(airfields?: AirfieldRecord[]) {
    this.airfields = airfields ?? getOfflineAirfields();
  }

  findAirportsNear(centerLat: number, centerLon: number, radiusMiles = 35.0): Array<{ airfield: AirfieldRecord; distanceMiles: number }> {
    const matches: Array<{ airfield: AirfieldRecord; distanceMiles: number }> = [];
    for (const af of this.airfields) {
      const d = haversineMiles(centerLat, centerLon, af.latitude, af.longitude);
      if (d <= radiusMiles) {
        matches.push({ airfield: af, distanceMiles: d });
      }
    }
    matches.sort((a, b) => a.distanceMiles - b.distanceMiles);
    return matches;
  }

  convertToChannels(airfields: AirfieldRecord[]): RadioChannel[] {
    const channels: RadioChannel[] = [];
    let num = 1;
    for (const af of airfields) {
      for (const freq of af.frequencies) {
        channels.push(
          createRadioChannel({
            number: num++,
            name: `${af.ident} ${freq.type}`,
            callsign: af.ident,
            rxFreq: freq.frequencyMhz,
            txFreq: freq.frequencyMhz,
            offset: 0.0,
            offsetDir: "off",
            mode: "AM",
            power: "Low",
            toneMode: "None",
            city: af.municipality || null,
            state: af.state || null,
            lat: af.latitude,
            lon: af.longitude,
            specialType: "AVIATION",
            comment: `${af.name} - ${freq.description || freq.type}`.trim(),
          }),
        );
      }
    }
    return channels;
  }
}
