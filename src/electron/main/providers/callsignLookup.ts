/**
 * Amateur Radio Callsign Lookup Service (QRZ.com XML API + Callook.info fallback).
 * Uses single-pass XML entity unescaping (CodeQL safe) and rejects XXE / DOCTYPE payloads.
 */

const USER_AGENT = "W5CDN-RadioPlanner/0.2.0";

const XML_ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&apos;": "'",
};

function decodeXmlEntities(raw: string): string {
  return raw.replace(/&(amp|lt|gt|quot|apos);/g, (match) => XML_ENTITIES[match] ?? match);
}

function extractXmlTag(xml: string, tag: string): string | null {
  if (/<!DOCTYPE|<!ENTITY/i.test(xml)) {
    throw new Error("Rejected unsafe XML with DOCTYPE/ENTITY declaration.");
  }
  const re = new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)</${tag}>`, "i");
  const match = xml.match(re);
  if (!match) return null;
  return decodeXmlEntities(match[1].trim());
}

export interface CallsignLookupResult {
  callsign: string;
  name: string;
  city: string;
  state: string;
  grid: string;
  lat: number | null;
  lon: number | null;
  licenseClass: string;
  source: string;
}

export class CallsignLookupService {
  private qrzUsername: string | null;
  private qrzPassword: string | null;
  private sessionKey: string | null = null;

  constructor(qrzUsername?: string | null, qrzPassword?: string | null) {
    this.qrzUsername = qrzUsername?.trim() || null;
    this.qrzPassword = qrzPassword?.trim() || null;
  }

  private async authenticateQrz(): Promise<{ key: string | null; error?: string }> {
    if (!this.qrzUsername || !this.qrzPassword) {
      return { key: null, error: "QRZ credentials not configured." };
    }
    try {
      const url = new URL("https://xmldata.qrz.com/xml/current/");
      url.searchParams.set("username", this.qrzUsername);
      url.searchParams.set("password", this.qrzPassword);
      url.searchParams.set("agent", USER_AGENT);
      const res = await fetch(url.toString(), {
        headers: { "User-Agent": USER_AGENT },
        signal: AbortSignal.timeout(7000),
      });
      if (!res.ok) return { key: null, error: `QRZ HTTP ${res.status}` };
      const xml = await res.text();
      const key = extractXmlTag(xml, "Key");
      const err = extractXmlTag(xml, "Error");
      if (key) {
        this.sessionKey = key;
        return { key };
      }
      return { key: null, error: err || "QRZ authentication failed." };
    } catch (err) {
      return { key: null, error: err instanceof Error ? err.message : "QRZ network error" };
    }
  }

  async testQrzLogin(): Promise<{ ok: boolean; message: string }> {
    const auth = await this.authenticateQrz();
    if (auth.key) {
      return { ok: true, message: "QRZ XML session authenticated successfully." };
    }
    return { ok: false, message: auth.error || "QRZ authentication failed." };
  }

  private async lookupQrz(callsign: string): Promise<CallsignLookupResult | null> {
    if (!this.qrzUsername || !this.qrzPassword) return null;
    if (!this.sessionKey) {
      const auth = await this.authenticateQrz();
      if (!auth.key) return null;
    }

    try {
      const url = new URL("https://xmldata.qrz.com/xml/current/");
      url.searchParams.set("s", this.sessionKey!);
      url.searchParams.set("callsign", callsign);
      const res = await fetch(url.toString(), {
        headers: { "User-Agent": USER_AGENT },
        signal: AbortSignal.timeout(7000),
      });
      if (!res.ok) return null;
      const xml = await res.text();
      const call = extractXmlTag(xml, "call");
      if (!call) return null;

      const fname = extractXmlTag(xml, "fname") || "";
      const lname = extractXmlTag(xml, "name") || "";
      const latStr = extractXmlTag(xml, "lat");
      const lonStr = extractXmlTag(xml, "lon");
      const lat = latStr !== null && Number.isFinite(Number(latStr)) ? Number(latStr) : null;
      const lon = lonStr !== null && Number.isFinite(Number(lonStr)) ? Number(lonStr) : null;

      return {
        callsign: call.toUpperCase(),
        name: `${fname} ${lname}`.trim(),
        city: extractXmlTag(xml, "addr2") || "",
        state: extractXmlTag(xml, "state") || "",
        grid: extractXmlTag(xml, "grid") || "",
        lat,
        lon,
        licenseClass: extractXmlTag(xml, "class") || "",
        source: "QRZ",
      };
    } catch {
      return null;
    }
  }

  private async lookupCallook(callsign: string): Promise<CallsignLookupResult | null> {
    try {
      const url = `https://callook.info/${encodeURIComponent(callsign)}/json`;
      const res = await fetch(url, {
        headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
        signal: AbortSignal.timeout(6000),
      });
      if (!res.ok) return null;
      const data = (await res.json()) as {
        status?: string;
        current?: { callsign?: string; operClass?: string };
        name?: string;
        address?: { line2?: string };
        location?: { latitude?: string; longitude?: string; gridsquare?: string };
      };
      if (data.status !== "VALID") return null;

      const line2 = data.address?.line2 || "";
      let city = "";
      let state = "";
      const match = line2.match(/^(.+?),\s*([A-Z]{2})\b/);
      if (match) {
        city = match[1].trim();
        state = match[2].trim();
      }

      const lat = data.location?.latitude ? Number(data.location.latitude) : null;
      const lon = data.location?.longitude ? Number(data.location.longitude) : null;

      return {
        callsign: (data.current?.callsign || callsign).toUpperCase(),
        name: data.name || "",
        city,
        state,
        grid: data.location?.gridsquare || "",
        lat: lat !== null && Number.isFinite(lat) ? lat : null,
        lon: lon !== null && Number.isFinite(lon) ? lon : null,
        licenseClass: data.current?.operClass || "",
        source: "Callook.info",
      };
    } catch {
      return null;
    }
  }

  async lookup(callsign: string): Promise<CallsignLookupResult | null> {
    const clean = (callsign || "").trim().toUpperCase().replace(/[^A-Z0-9/]/g, "");
    if (!clean) return null;

    if (this.qrzUsername && this.qrzPassword) {
      const qrz = await this.lookupQrz(clean);
      if (qrz) return qrz;
    }
    return this.lookupCallook(clean);
  }
}
