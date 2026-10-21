"""Highway Route Corridor Planning Engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models.channel import RadioChannel
from core.providers.geocoding import (
    GeocodingProvider,
    GeoPoint,
    along_track_distance,
    cross_track_distance,
    haversine_distance,
)


@dataclass
class RouteCorridorResult:
    """Calculated corridor route results, resolved cities, and matched channels."""

    waypoints: list[GeoPoint]
    cumulative_mileages: list[float]
    total_distance_miles: float
    channels: list[RadioChannel] = field(default_factory=list)
    channel_counts_by_band: dict[str, int] = field(default_factory=dict)


class RouteCorridorEngine:
    """Calculates highway travel corridor repeater sequences along sequential waypoints."""

    def __init__(self, geocoder: GeocodingProvider | None = None):
        self.geocoder = geocoder or GeocodingProvider()

    def plan_route(
        self,
        waypoint_names: list[str],
        candidate_channels: list[RadioChannel],
        corridor_width_miles: float = 25.0,
        include_simplex: bool = True,
        unit: str = "MILES",
    ) -> RouteCorridorResult:
        """Resolve waypoints, calculate perpendicular cross-track corridor matches, and sort chronologically."""
        if len(waypoint_names) < 2:
            raise ValueError("Route corridor requires at least 2 waypoints (origin and destination).")

        # 1. Resolve waypoints to GeoPoints
        geo_points = [self.geocoder.resolve(name) for name in waypoint_names]

        # 2. Calculate cumulative mileages
        cumulative = [0.0]
        total = 0.0
        for i in range(len(geo_points) - 1):
            seg_dist = haversine_distance(geo_points[i], geo_points[i + 1], unit=unit)
            total += seg_dist
            cumulative.append(total)

        # 3. Create route legs
        legs: list[tuple[GeoPoint, GeoPoint, float, float]] = []
        for i in range(len(geo_points) - 1):
            start_p = geo_points[i]
            end_p = geo_points[i + 1]
            seg_len = cumulative[i + 1] - cumulative[i]
            legs.append((start_p, end_p, cumulative[i], seg_len))

        # 4. Filter and sequence candidate repeaters
        matched_items: list[tuple[float, RadioChannel]] = []

        for ch in candidate_channels:
            if not include_simplex and ch.is_simplex:
                continue
            if ch.lat is None or ch.lon is None:
                continue

            r_point = GeoPoint(lat=ch.lat, lon=ch.lon, name=ch.name)

            best_progress = None
            min_xtrack = float("inf")

            for start_p, end_p, leg_start_dist, leg_len in legs:
                # Fast Bounding Box pre-filter
                min_lat = min(start_p.lat, end_p.lat) - 1.0
                max_lat = max(start_p.lat, end_p.lat) + 1.0
                min_lon = min(start_p.lon, end_p.lon) - 1.0
                max_lon = max(start_p.lon, end_p.lon) + 1.0

                if not (min_lat <= r_point.lat <= max_lat and min_lon <= r_point.lon <= max_lon):
                    continue

                xtrack = cross_track_distance(r_point, start_p, end_p, unit=unit)
                atd = along_track_distance(r_point, start_p, end_p, unit=unit)

                if xtrack <= corridor_width_miles and -corridor_width_miles <= atd <= (leg_len + corridor_width_miles):
                    if xtrack < min_xtrack:
                        min_xtrack = xtrack
                        progress = leg_start_dist + atd
                        best_progress = progress

            if best_progress is not None:
                matched_items.append((best_progress, ch))

        # Sort repeaters chronologically from origin to destination
        matched_items.sort(key=lambda x: x[0])
        ordered_channels = [item[1] for item in matched_items]

        # Calculate frequency breakdown
        counts: dict[str, int] = {}
        for ch in ordered_channels:
            band = ch.band
            counts[band] = counts.get(band, 0) + 1

        return RouteCorridorResult(
            waypoints=geo_points,
            cumulative_mileages=cumulative,
            total_distance_miles=total,
            channels=ordered_channels,
            channel_counts_by_band=counts,
        )
