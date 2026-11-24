/**
 * RadioID.net DMR Callsign Lookup and Talkgroup Expansion Helper.
 */

import { RadioChannel } from "../../shared/types";

export interface DmrTalkgroup {
  name: string;
  tgId: string;
  timeSlot: number;
}

export const DEFAULT_DMR_TALKGROUPS: DmrTalkgroup[] = [
  { name: "Local 9", tgId: "9", timeSlot: 2 },
  { name: "Parrot", tgId: "9990", timeSlot: 2 },
  { name: "Statewide", tgId: "3148", timeSlot: 1 },
  { name: "USA Nationwide", tgId: "3100", timeSlot: 1 },
  { name: "TAC 310", tgId: "310", timeSlot: 1 },
];

export interface RadioIdResult {
  callsign: string;
  dmrId: string;
  fname: string;
  surname: string;
  city: string;
  state: string;
  country: string;
}

export class RadioIdProvider {
  private offlineOnly: boolean;

  constructor(offlineOnly = false) {
    this.offlineOnly = offlineOnly;
  }

  async lookupCallsign(callsign: string): Promise<RadioIdResult | null> {
    const clean = (callsign || "").trim().toUpperCase();
    if (!clean || this.offlineOnly) return null;
    try {
      const url = `https://radioid.net/api/dmr/user/?callsign=${encodeURIComponent(clean)}`;
      const res = await fetch(url, {
        headers: { "User-Agent": "W5CDN-RadioPlanner/0.2.0", Accept: "application/json" },
        signal: AbortSignal.timeout(6000),
      });
      if (!res.ok) return null;
      const body = (await res.json()) as {
        results?: Array<{
          callsign?: string;
          id?: number | string;
          fname?: string;
          surname?: string;
          city?: string;
          state?: string;
          country?: string;
        }>;
      };
      const first = body?.results?.[0];
      if (!first || !first.id) return null;
      return {
        callsign: String(first.callsign || clean).toUpperCase(),
        dmrId: String(first.id),
        fname: String(first.fname || ""),
        surname: String(first.surname || ""),
        city: String(first.city || ""),
        state: String(first.state || ""),
        country: String(first.country || ""),
      };
    } catch {
      return null;
    }
  }

  static duplicateChannelForTalkgroups(
    channel: RadioChannel,
    talkgroups: DmrTalkgroup[] = DEFAULT_DMR_TALKGROUPS,
  ): RadioChannel[] {
    return talkgroups.map((tg, idx) => ({
      ...channel,
      number: channel.number + idx,
      mode: "DMR",
      colorCode: channel.colorCode ?? 1,
      timeSlot: tg.timeSlot,
      dmrId: tg.tgId,
      contact: tg.name,
      name: `${(channel.city || channel.callsign || channel.name).slice(0, 8)} ${tg.name.slice(0, 6)}`.trim(),
      comment: `${channel.comment ? `${channel.comment} | ` : ""}DMR TG ${tg.tgId} (${tg.name}) TS${tg.timeSlot}`,
    }));
  }
}
