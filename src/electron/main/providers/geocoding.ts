/**
 * Offline & Online Geocoding, Haversine distance, Cross-Track distance, and IP Geolocation.
 */

import fs from "node:fs";
import path from "node:path";
import { resolveResourcesDir } from "../paths";

const EARTH_RADIUS_MILES = 3958.8;
const USER_AGENT = "W5CDN-RadioPlanner/0.2.0 (Amateur Radio Codeplug Studio)";

let offlineCitiesCache: Record<string, [number, number]> | null = null;

export function getOfflineCities(): Record<string, [number, number]> {
  if (offlineCitiesCache) return offlineCitiesCache;
  try {
    const filePath = path.join(resolveResourcesDir(), "offline_cities.json");
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf-8")) as Record<string, [number, number]>;
    offlineCitiesCache = parsed;
    return parsed;
  } catch {
    offlineCitiesCache = {};
    return offlineCitiesCache;
  }
}

export function haversineMiles(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const rLat1 = toRad(lat1);
  const rLat2 = toRad(lat2);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(rLat1) * Math.cos(rLat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));
  return EARTH_RADIUS_MILES * c;
}

/**
 * Compute perpendicular (cross-track) distance in miles from point (pLat, pLon) to segment A->B.
 */
export function pointToSegmentDistanceMiles(
  pLat: number,
  pLon: number,
  aLat: number,
  aLon: number,
  bLat: number,
  bLon: number,
): number {
  const cosLat = Math.cos((((aLat + bLat) / 2) * Math.PI) / 180);
  const px = pLon * cosLat;
  const py = pLat;
  const ax = aLon * cosLat;
  const ay = aLat;
  const bx = bLon * cosLat;
  const by = bLat;

  const dx = bx - ax;
  const dy = by - ay;
  const segLenSq = dx * dx + dy * dy;

  if (segLenSq < 1e-12) {
    return haversineMiles(pLat, pLon, aLat, aLon);
  }

  let t = ((px - ax) * dx + (py - ay) * dy) / segLenSq;
  t = Math.max(0, Math.min(1, t));
  const closestLat = aLat + t * (bLat - aLat);
  const closestLon = aLon + t * (bLon - aLon);
  return haversineMiles(pLat, pLon, closestLat, closestLon);
}

/**
 * Compute shortest distance from a point to a polyline and its along-track progress from start.
 */
export function pointToRouteMetrics(
  pLat: number,
  pLon: number,
  routePoints: Array<[number, number]>,
): { crossTrackMiles: number; alongTrackMiles: number } {
  if (routePoints.length === 0) {
    return { crossTrackMiles: Infinity, alongTrackMiles: 0 };
  }
  if (routePoints.length === 1) {
    return {
      crossTrackMiles: haversineMiles(pLat, pLon, routePoints[0][0], routePoints[0][1]),
      alongTrackMiles: 0,
    };
  }

  let bestDist = Infinity;
  let bestAlong = 0;
  let cumulative = 0;

  for (let i = 0; i < routePoints.length - 1; i++) {
    const [aLat, aLon] = routePoints[i];
    const [bLat, bLon] = routePoints[i + 1];
    const segMiles = haversineMiles(aLat, aLon, bLat, bLon);

    const cosLat = Math.cos((((aLat + bLat) / 2) * Math.PI) / 180);
    const dx = (bLon - aLon) * cosLat;
    const dy = bLat - aLat;
    const segLenSq = dx * dx + dy * dy;
    let t = 0;
    if (segLenSq > 1e-12) {
      t = (((pLon - aLon) * cosLat) * dx + (pLat - aLat) * dy) / segLenSq;
      t = Math.max(0, Math.min(1, t));
    }
    const cLat = aLat + t * (bLat - aLat);
    const cLon = aLon + t * (bLon - aLon);
    const dist = haversineMiles(pLat, pLon, cLat, cLon);

    if (dist < bestDist) {
      bestDist = dist;
      bestAlong = cumulative + t * segMiles;
    }
    cumulative += segMiles;
  }

  return { crossTrackMiles: bestDist, alongTrackMiles: bestAlong };
}

export class GeocodingProvider {
  private memoryCache = new Map<string, [number, number]>();
  private offlineOnly: boolean;

  constructor(offlineOnly = false) {
    this.offlineOnly = offlineOnly;
  }

  private lookupOffline(query: string): [number, number] | null {
    const cities = getOfflineCities();
    const cleaned = query.trim().toLowerCase();
    if (!cleaned) return null;

    if (cleaned in cities) return cities[cleaned];

    // Try stripping commas and normalizing whitespace
    const norm = cleaned.replace(/,/g, " ").replace(/\s+/g, " ").trim();
    for (const [k, coords] of Object.entries(cities)) {
      const kNorm = k.toLowerCase().replace(/,/g, " ").replace(/\s+/g, " ").trim();
      if (kNorm === norm) return coords;
    }

    // Try city-name prefix match (e.g., "Tyler" matches "tyler, tx")
    const firstToken = cleaned.split(",")[0].trim();
    if (firstToken.length >= 3) {
      for (const [k, coords] of Object.entries(cities)) {
        if (k.toLowerCase().split(",")[0].trim() === firstToken) {
          return coords;
        }
      }
    }
    return null;
  }

  /**
   * Geocode a location string ("Tyler, TX", "75701", "32.35,-95.30") to [lat, lon].
   */
  async geocode(location: string): Promise<[number, number] | null> {
    const raw = (location || "").trim();
    if (!raw) return null;

    // 1. Direct "lat, lon" pair
    const coordMatch = raw.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (coordMatch) {
      const lat = Number(coordMatch[1]);
      const lon = Number(coordMatch[2]);
      if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
        return [lat, lon];
      }
    }

    const key = raw.toLowerCase();
    const cached = this.memoryCache.get(key);
    if (cached) return cached;

    const offline = this.lookupOffline(raw);
    if (offline) {
      this.memoryCache.set(key, offline);
      return offline;
    }

    if (this.offlineOnly) return null;

    // 2. Online OpenStreetMap Nominatim lookup
    try {
      const url = new URL("https://nominatim.openstreetmap.org/search");
      url.searchParams.set("q", raw);
      url.searchParams.set("format", "json");
      url.searchParams.set("limit", "1");
      url.searchParams.set("countrycodes", "us,ca");

      const res = await fetch(url.toString(), {
        headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
        signal: AbortSignal.timeout(6000),
      });
      if (res.ok) {
        const data = (await res.json()) as Array<{ lat?: string; lon?: string }>;
        if (Array.isArray(data) && data.length > 0 && data[0].lat && data[0].lon) {
          const lat = Number(data[0].lat);
          const lon = Number(data[0].lon);
          if (Number.isFinite(lat) && Number.isFinite(lon)) {
            const pair: [number, number] = [lat, lon];
            this.memoryCache.set(key, pair);
            return pair;
          }
        }
      }
    } catch {
      // Offline or timeout
    }
    return null;
  }

  /**
   * Reverse-geocode [lat, lon] to a human-readable "City, ST" label.
   */
  async reverseGeocode(lat: number, lon: number): Promise<string | null> {
    if (!this.offlineOnly) {
      try {
        const url = new URL("https://nominatim.openstreetmap.org/reverse");
        url.searchParams.set("lat", String(lat));
        url.searchParams.set("lon", String(lon));
        url.searchParams.set("format", "json");
        url.searchParams.set("zoom", "10");

        const res = await fetch(url.toString(), {
          headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
          const data = (await res.json()) as {
            address?: { city?: string; town?: string; village?: string; county?: string; state?: string };
          };
          const addr = data?.address;
          if (addr) {
            const place = addr.city || addr.town || addr.village || addr.county || "";
            const state = addr.state || "";
            if (place && state) return `${place}, ${state}`;
            if (place) return place;
          }
        }
      } catch {
        // Fallback to nearest offline city
      }
    }

    // Nearest offline city fallback
    let nearestName: string | null = null;
    let nearestDist = Infinity;
    for (const [name, [cLat, cLon]] of Object.entries(getOfflineCities())) {
      const d = haversineMiles(lat, lon, cLat, cLon);
      if (d < nearestDist) {
        nearestDist = d;
        nearestName = name
          .split(",")
          .map((part, idx) => (idx === 1 ? part.trim().toUpperCase() : part.trim().replace(/\b\w/g, (c) => c.toUpperCase())))
          .join(", ");
      }
    }
    return nearestName;
  }

  /**
   * Estimate current user location via IP geolocation (falls back gracefully when offline).
   */
  async geolocateByIp(): Promise<{ lat: number; lon: number; label: string; source: string } | null> {
    if (this.offlineOnly) return null;
    try {
      const res = await fetch("http://ip-api.com/json/?fields=status,city,region,lat,lon", {
        headers: { "User-Agent": USER_AGENT },
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        const data = (await res.json()) as {
          status?: string;
          city?: string;
          region?: string;
          lat?: number;
          lon?: number;
        };
        if (data.status === "success" && typeof data.lat === "number" && typeof data.lon === "number") {
          const label = data.city && data.region ? `${data.city}, ${data.region}` : `${data.lat.toFixed(4)}, ${data.lon.toFixed(4)}`;
          return { lat: data.lat, lon: data.lon, label, source: "ip" };
        }
      }
    } catch {
      // Offline
    }
    return null;
  }
}
