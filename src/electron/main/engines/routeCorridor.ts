/**
 * Highway Route Corridor Repeater Discovery Engine.
 * Discovers repeaters within `corridorMiles` of a multi-waypoint polyline and sorts them along-track.
 */

import { RadioChannel } from "../../shared/types";
import { pointToRouteMetrics } from "../providers/geocoding";

export interface CorridorChannelMatch {
  channel: RadioChannel;
  crossTrackMiles: number;
  alongTrackMiles: number;
}

export class RouteCorridorEngine {
  static filterAndOrder(
    candidates: RadioChannel[],
    routePoints: Array<[number, number]>,
    corridorMiles = 25.0,
  ): CorridorChannelMatch[] {
    if (routePoints.length < 2) return [];
    const matches: CorridorChannelMatch[] = [];

    for (const ch of candidates) {
      if (ch.lat === null || ch.lon === null) continue;
      const metrics = pointToRouteMetrics(ch.lat, ch.lon, routePoints);
      if (metrics.crossTrackMiles <= corridorMiles) {
        matches.push({
          channel: ch,
          crossTrackMiles: metrics.crossTrackMiles,
          alongTrackMiles: metrics.alongTrackMiles,
        });
      }
    }

    matches.sort((a, b) => {
      if (Math.abs(a.alongTrackMiles - b.alongTrackMiles) > 0.25) {
        return a.alongTrackMiles - b.alongTrackMiles;
      }
      return a.crossTrackMiles - b.crossTrackMiles;
    });

    return matches;
  }
}
