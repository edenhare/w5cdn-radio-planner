/**
 * Radial Proximity Search Repeater Discovery Engine.
 */

import { RadioChannel } from "../../shared/types";
import { haversineMiles } from "../providers/geocoding";

export interface ProximityChannelMatch {
  channel: RadioChannel;
  distanceMiles: number;
}

export class ProximityEngine {
  static filterAndOrder(
    candidates: RadioChannel[],
    centerLat: number,
    centerLon: number,
    radiusMiles = 50.0,
  ): ProximityChannelMatch[] {
    const matches: ProximityChannelMatch[] = [];
    for (const ch of candidates) {
      if (ch.lat === null || ch.lon === null) continue;
      const dist = haversineMiles(centerLat, centerLon, ch.lat, ch.lon);
      if (dist <= radiusMiles) {
        matches.push({ channel: ch, distanceMiles: dist });
      }
    }
    matches.sort((a, b) => a.distanceMiles - b.distanceMiles);
    return matches;
  }
}
