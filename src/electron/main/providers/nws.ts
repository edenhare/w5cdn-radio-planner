/**
 * National Weather Service (NWS) Active Weather Alerts Provider.
 */

import { utcNowIso } from "../../shared/sanitize";

export interface NwsAlertItem {
  id: string;
  event: string;
  severity: string;
  headline: string;
  area: string;
  areaDesc: string;
  effective: string;
  expires: string;
  description: string;
  instruction: string;
}

export interface NwsAlertsResponse {
  online: boolean;
  states: string[];
  count: number;
  fetched_at: string;
  alerts: NwsAlertItem[];
  briefing_text: string;
  error?: string;
}

export class NwsAlertsService {
  private offlineOnly: boolean;

  constructor(offlineOnly = false) {
    this.offlineOnly = offlineOnly;
  }

  async getAlertsForStates(states: string[]): Promise<NwsAlertsResponse> {
    const cleanStates = Array.from(
      new Set(
        states
          .map((s) => String(s || "").trim().toUpperCase())
          .filter((s) => /^[A-Z]{2}$/.test(s)),
      ),
    );
    const fetchedAt = utcNowIso();

    if (cleanStates.length === 0) {
      return {
        online: true,
        states: [],
        count: 0,
        fetched_at: fetchedAt,
        alerts: [],
        briefing_text: "No states selected for NWS alert query.",
      };
    }

    if (this.offlineOnly) {
      return {
        online: false,
        states: cleanStates,
        count: 0,
        fetched_at: fetchedAt,
        alerts: [],
        briefing_text: `Offline mode — NWS alerts skipped for ${cleanStates.join(", ")}.`,
        error: "Offline mode — NWS alerts unavailable.",
      };
    }

    try {
      const areaParam = cleanStates.join(",");
      const url = `https://api.weather.gov/alerts/active?area=${encodeURIComponent(areaParam)}&status=actual`;
      const res = await fetch(url, {
        headers: {
          "User-Agent": "(W5CDN-RadioPlanner/0.2.0, w5cdn@example.org)",
          Accept: "application/geo+json",
        },
        signal: AbortSignal.timeout(7000),
      });
      if (!res.ok) {
        return {
          online: false,
          states: cleanStates,
          count: 0,
          fetched_at: fetchedAt,
          alerts: [],
          briefing_text: "",
          error: `NWS API HTTP ${res.status}`,
        };
      }
      const data = (await res.json()) as {
        features?: Array<{
          id?: string;
          properties?: {
            event?: string;
            severity?: string;
            headline?: string;
            areaDesc?: string;
            effective?: string;
            expires?: string;
            description?: string;
            instruction?: string;
          };
        }>;
      };
      const alerts: NwsAlertItem[] = (data.features || []).slice(0, 40).map((f, idx) => {
        const area = String(f.properties?.areaDesc || "");
        return {
          id: String(f.id || `alert-${idx}`),
          event: String(f.properties?.event || "Weather Advisory"),
          severity: String(f.properties?.severity || "Unknown"),
          headline: String(f.properties?.headline || ""),
          area,
          areaDesc: area,
          effective: String(f.properties?.effective || ""),
          expires: String(f.properties?.expires || ""),
          description: String(f.properties?.description || ""),
          instruction: String(f.properties?.instruction || ""),
        };
      });

      const briefingLines = [
        `NWS ACTIVE WEATHER BRIEFING (${cleanStates.join(", ")}) — ${fetchedAt}`,
        alerts.length === 0
          ? "ALL CLEAR — No active NWS watches, warnings, or advisories."
          : alerts.map((a) => `[${a.severity.toUpperCase()}] ${a.event}: ${a.headline || a.area}`).join("\n"),
      ];

      return {
        online: true,
        states: cleanStates,
        count: alerts.length,
        fetched_at: fetchedAt,
        alerts,
        briefing_text: briefingLines.join("\n"),
      };
    } catch (err) {
      return {
        online: false,
        states: cleanStates,
        count: 0,
        fetched_at: fetchedAt,
        alerts: [],
        briefing_text: "",
        error: err instanceof Error ? err.message : "NWS fetch failed",
      };
    }
  }
}
