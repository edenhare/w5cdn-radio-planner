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
    "monroe, la": (32.5093, -92.1193),
    "vicksburg, ms": (32.3526, -90.8779),
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
        """Resolve a city/state query into a GeoPoint."""
        normalized = query.strip().lower()

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
