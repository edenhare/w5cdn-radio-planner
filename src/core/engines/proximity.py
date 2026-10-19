"""Radial Proximity 5-Ring Search Engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models.channel import RadioChannel
from core.providers.geocoding import (
    GeocodingProvider,
    GeoPoint,
    haversine_distance,
)


@dataclass
class ProximityResult:
    """Calculated proximity rings result."""

    center_point: GeoPoint
    radius_miles: float
    channels: list[RadioChannel] = field(default_factory=list)
    rings: dict[int, list[RadioChannel]] = field(default_factory=dict)
    channel_counts_by_band: dict[str, int] = field(default_factory=dict)


class ProximityEngine:
    """Gathers and organizes repeaters into 5 concentric distance bands."""

    def __init__(self, geocoder: GeocodingProvider | None = None):
        self.geocoder = geocoder or GeocodingProvider()

    def search_proximity(
        self,
        center_location: str,
        candidate_channels: list[RadioChannel],
        radius_miles: float = 50.0,
        include_simplex: bool = True,
        unit: str = "MILES",
    ) -> ProximityResult:
        """Resolve center point and distribute repeaters across 5 concentric distance rings."""
        center = self.geocoder.resolve(center_location)

        ring_step = radius_miles / 5.0
        rings: dict[int, list[tuple[float, RadioChannel]]] = {
            1: [],
            2: [],
            3: [],
            4: [],
            5: [],
        }
        all_matched: list[tuple[float, RadioChannel]] = []

        for ch in candidate_channels:
            if not include_simplex and ch.is_simplex:
                continue
            if ch.lat is None or ch.lon is None:
                continue

            r_point = GeoPoint(lat=ch.lat, lon=ch.lon, name=ch.name)
            dist = haversine_distance(center, r_point, unit=unit)

            if dist <= radius_miles:
                # Determine ring 1 to 5
                ring_idx = min(5, max(1, int(dist // ring_step) + 1))
                comment_with_dist = f"{ch.comment} [Ring {ring_idx}: {dist:.1f} mi]".strip()
                annotated_ch = ch.model_copy(update={"comment": comment_with_dist})

                rings[ring_idx].append((dist, annotated_ch))
                all_matched.append((dist, annotated_ch))

        # Sort each ring by distance
        sorted_rings: dict[int, list[RadioChannel]] = {}
        for ring_idx in range(1, 6):
            rings[ring_idx].sort(key=lambda x: x[0])
            sorted_rings[ring_idx] = [item[1] for item in rings[ring_idx]]

        all_matched.sort(key=lambda x: x[0])
        ordered_channels = [item[1] for item in all_matched]

        counts: dict[str, int] = {}
        for ch in ordered_channels:
            band = ch.band
            counts[band] = counts.get(band, 0) + 1

        return ProximityResult(
            center_point=center,
            radius_miles=radius_miles,
            channels=ordered_channels,
            rings=sorted_rings,
            channel_counts_by_band=counts,
        )
