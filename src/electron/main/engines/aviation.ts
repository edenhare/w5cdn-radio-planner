/**
 * Local Aviation Planner Engine.
 */

import { AirfieldRecord, RadioChannel } from "../../shared/types";
import { AirportsProvider } from "../providers/airports";

export interface AviationPlanResult {
  airfields: Array<{ airfield: AirfieldRecord; distanceMiles: number }>;
  channels: RadioChannel[];
}

export class AviationEngine {
  private provider: AirportsProvider;

  constructor(provider = new AirportsProvider()) {
    this.provider = provider;
  }

  discover(centerLat: number, centerLon: number, radiusMiles = 35.0): AviationPlanResult {
    const matches = this.provider.findAirportsNear(centerLat, centerLon, radiusMiles);
    const channels = this.provider.convertToChannels(matches.map((m) => m.airfield));
    return { airfields: matches, channels };
  }
}
