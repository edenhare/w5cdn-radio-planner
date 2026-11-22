"""Geocoding and Spatial Geometry calculations with offline fallback."""

from __future__ import annotations

import math
from dataclasses import dataclass

import httpx

EARTH_RADIUS_MILES = 3958.8
EARTH_RADIUS_KM = 6371.0

# Embedded offline geocoding cache for standard test and common cities
OFFLINE_CITIES: dict[str, tuple[float, float]] = {
    "tyler, tx": (32.3513, -95.3011),
    "tyler": (32.3513, -95.3011),
    "shreveport, la": (32.5252, -93.7502),
    "shreveport": (32.5252, -93.7502),
    "jackson, ms": (32.2988, -90.1848),
    "jackson": (32.2988, -90.1848),
    "dallas, tx": (32.7767, -96.7970),
    "dallas": (32.7767, -96.7970),
    "fort worth, tx": (32.7555, -97.3308),
    "austin, tx": (30.2672, -97.7431),
    "houston, tx": (29.7604, -95.3698),
    "longview, tx": (32.5007, -94.7405),
    "marshall, tx": (32.5449, -94.3674),
    "kilgore, tx": (32.3850, -94.8750),
    "lindale, tx": (32.5140, -95.4080),
    "bossier city, la": (32.5160, -93.7322),
    "haughton, la": (32.5300, -93.5400),
    "minden, la": (32.6150, -93.2850),
    "arcadia, la": (32.5510, -92.9230),
    "ruston, la": (32.5232, -92.6379),
    "west monroe, la": (32.5180, -92.1470),
    "monroe, la": (32.5093, -92.1193),
    "rayville, la": (32.4740, -91.7560),
    "delhi, la": (32.4580, -91.4930),
    "tallulah, la": (32.4085, -91.1865),
    "vicksburg, ms": (32.3526, -90.8779),
    "clinton, ms": (32.3410, -90.3310),
    "pearl, ms": (32.2740, -90.1330),
    "brandon, ms": (32.2730, -89.9850),
    "madison, ms": (32.4280, -90.1150),
    "ridgeland, ms": (32.4280, -90.1150),
    # Canadian Cities
    "toronto, on": (43.6532, -79.3832),
    "toronto": (43.6532, -79.3832),
    "ottawa, on": (45.4215, -75.6972),
    "ottawa": (45.4215, -75.6972),
    "windsor, on": (42.3149, -83.0364),
    "montreal, qc": (45.5017, -73.5673),
    "montreal": (45.5017, -73.5673),
    "quebec city, qc": (46.8139, -71.2080),
    "vancouver, bc": (49.2827, -123.1207),
    "vancouver": (49.2827, -123.1207),
    "victoria, bc": (48.4284, -123.3656),
    "calgary, ab": (51.0447, -114.0719),
    "calgary": (51.0447, -114.0719),
    "edmonton, ab": (53.5461, -113.4938),
    "edmonton": (53.5461, -113.4938),
    "winnipeg, mb": (49.8951, -97.1384),
    "winnipeg": (49.8951, -97.1384),
    "regina, sk": (50.4452, -104.6189),
    "saskatoon, sk": (52.1579, -106.6702),
    "halifax, ns": (44.6488, -63.5752),
    "st. john's, nl": (47.5615, -52.7126),
}


@dataclass(frozen=True)
class GeoPoint:
    """Geographic point with latitude and longitude."""

    lat: float
    lon: float
    name: str = ""

    def to_radians(self) -> tuple[float, float]:
        return math.radians(self.lat), math.radians(self.lon)


def haversine_distance(p1: GeoPoint, p2: GeoPoint, unit: str = "MILES") -> float:
    """Calculate great-circle distance between two points using Haversine formula."""
    r = EARTH_RADIUS_MILES if unit.upper() == "MILES" else EARTH_RADIUS_KM
    lat1, lon1 = p1.to_radians()
    lat2, lon2 = p2.to_radians()

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def cross_track_distance(point: GeoPoint, start: GeoPoint, end: GeoPoint, unit: str = "MILES") -> float:
    """Calculate cross-track perpendicular distance from point to great circle segment (start -> end)."""
    r = EARTH_RADIUS_MILES if unit.upper() == "MILES" else EARTH_RADIUS_KM
    d13 = haversine_distance(start, point, unit=unit) / r  # Angular distance

    # Initial bearings
    lat1, lon1 = start.to_radians()
    lat2, lon2 = end.to_radians()
    lat3, lon3 = point.to_radians()

    # Bearing start -> end
    y12 = math.sin(lon2 - lon1) * math.cos(lat2)
    x12 = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    brng12 = math.atan2(y12, x12)

    # Bearing start -> point
    y13 = math.sin(lon3 - lon1) * math.cos(lat3)
    x13 = math.cos(lat1) * math.sin(lat3) - math.sin(lat1) * math.cos(lat3) * math.cos(lon3 - lon1)
    brng13 = math.atan2(y13, x13)

    xtrack_rad = math.asin(math.sin(d13) * math.sin(brng13 - brng12))
    return abs(xtrack_rad * r)


def along_track_distance(point: GeoPoint, start: GeoPoint, end: GeoPoint, unit: str = "MILES") -> float:
    """Calculate along-track distance from start point to projection of point onto great circle segment (start -> end)."""
    r = EARTH_RADIUS_MILES if unit.upper() == "MILES" else EARTH_RADIUS_KM
    d13 = haversine_distance(start, point, unit=unit) / r  # Angular distance

    lat1, lon1 = start.to_radians()
    lat2, lon2 = end.to_radians()
    lat3, lon3 = point.to_radians()

    # Bearing start -> end
    y12 = math.sin(lon2 - lon1) * math.cos(lat2)
    x12 = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    brng12 = math.atan2(y12, x12)

    # Bearing start -> point
    y13 = math.sin(lon3 - lon1) * math.cos(lat3)
    x13 = math.cos(lat1) * math.sin(lat3) - math.sin(lat1) * math.cos(lat3) * math.cos(lon3 - lon1)
    brng13 = math.atan2(y13, x13)

    delta_brng = brng13 - brng12
    atd_rad = math.atan2(math.tan(d13) * math.cos(delta_brng), 1.0)
    return atd_rad * r


class GeocodingProvider:
    """Resolves location names into geographic coordinates with online query and offline fallback."""

    def __init__(self, timeout: float = 4.0):
        self.timeout = timeout

    def resolve(self, query: str) -> GeoPoint:
        """Resolve a city/state query or 'lat, lon' coordinate pair into a GeoPoint."""
        normalized = query.strip().lower()

        # Support direct "lat, lon" coordinate strings (e.g. "32.3513, -95.3011")
        if "," in normalized:
            parts = [p.strip() for p in normalized.split(",", 1)]
            try:
                lat_val = float(parts[0])
                lon_val = float(parts[1])
                if -90.0 <= lat_val <= 90.0 and -180.0 <= lon_val <= 180.0:
                    return GeoPoint(lat=lat_val, lon=lon_val, name=query.strip())
            except ValueError:
                pass

        # Check offline cache first for instant resolution
        if normalized in OFFLINE_CITIES:
            lat, lon = OFFLINE_CITIES[normalized]
            return GeoPoint(lat=lat, lon=lon, name=query)

        # Attempt online Nominatim query
        try:
            url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "RadioPlanner/1.0 (amateur-radio-route-planner)"}
            params = {"q": query, "format": "json", "limit": 1}
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        lat = float(data[0]["lat"])
                        lon = float(data[0]["lon"])
                        return GeoPoint(lat=lat, lon=lon, name=query)
        except Exception:
            pass

        # If not found online and not in cache, fallback search partial keys
        for key, (lat, lon) in OFFLINE_CITIES.items():
            if key in normalized or normalized in key:
                return GeoPoint(lat=lat, lon=lon, name=query)

        raise ValueError(f"Unable to geocode location: '{query}'. Please check spelling or verify internet connection.")

    def reverse_geocode(self, lat: float, lon: float) -> str:
        """Reverse-geocode latitude/longitude into 'City, ST' with Nominatim and nearest offline city fallback."""
        from core.providers.repeaterbook import US_STATE_ABBR

        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            headers = {"User-Agent": "RadioPlanner/1.0 (amateur-radio-route-planner)"}
            params = {"lat": str(lat), "lon": str(lon), "format": "json", "zoom": 10}
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    addr = data.get("address", {})
                    city = (
                        addr.get("city")
                        or addr.get("town")
                        or addr.get("village")
                        or addr.get("municipality")
                        or addr.get("county")
                    )
                    state = addr.get("state") or addr.get("province") or ""
                    iso_lvl = addr.get("ISO3166-2-lvl4", "")
                    if iso_lvl and "-" in iso_lvl:
                        st_abbr = iso_lvl.split("-", 1)[1].upper()
                    else:
                        st_abbr = US_STATE_ABBR.get(state.lower(), state)
                    if city and st_abbr:
                        return f"{city}, {st_abbr}"
                    if city:
                        return str(city)
        except Exception:
            pass

        # Fallback to nearest known city within 60 miles, or formatted coordinates
        target = GeoPoint(lat=lat, lon=lon)
        best_city = None
        best_dist = 999999.0
        for name_key, (c_lat, c_lon) in OFFLINE_CITIES.items():
            if "," not in name_key:
                continue
            d = haversine_distance(target, GeoPoint(lat=c_lat, lon=c_lon))
            if d < best_dist:
                best_dist = d
                parts = name_key.split(",")
                best_city = f"{parts[0].strip().title()}, {parts[1].strip().upper()}"
        if best_city and best_dist <= 60.0:
            return best_city
        return f"{lat:.4f}, {lon:.4f}"

    def detect_ip_location(self) -> dict[str, float | str]:
        """Detect approximate current location via IP geolocation API."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get("http://ip-api.com/json/?fields=status,city,region,regionName,lat,lon")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        city = data.get("city", "")
                        region = data.get("region", "")
                        lat = float(data.get("lat", 0.0))
                        lon = float(data.get("lon", 0.0))
                        label = f"{city}, {region}".strip(", ")
                        return {"location": label, "lat": lat, "lon": lon}
        except Exception:
            pass
        raise ValueError("Could not automatically detect current location.")
