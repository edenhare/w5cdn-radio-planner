"""Local Aviation & Airport Communications Planner Engine."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models.aviation import AirfieldRecord
from core.models.channel import RadioChannel
from core.providers.airports import AirportsProvider
from core.providers.geocoding import GeocodingProvider, GeoPoint


@dataclass
class AviationResult:
    """Calculated local aviation planner result."""

    center_point: GeoPoint
    radius_miles: float
    matched_airports: list[AirfieldRecord]
    channels: list[RadioChannel] = field(default_factory=list)
    channel_counts_by_type: dict[str, int] = field(default_factory=dict)


class AviationEngine:
    """Resolves local airport communication frequencies for a target city and radius."""

    def __init__(
        self,
        geocoder: GeocodingProvider | None = None,
        airports_provider: AirportsProvider | None = None,
    ):
        self.geocoder = geocoder or GeocodingProvider()
        self.airports_provider = airports_provider or AirportsProvider()

    def plan_aviation(
        self,
        center_location: str,
        radius_miles: float = 35.0,
    ) -> AviationResult:
        """Find airports near location and build Airband channels list."""
        center = self.geocoder.resolve(center_location)
        airports = self.airports_provider.find_airports_near(
            center.lat, center.lon, radius_miles=radius_miles
        )
        channels = self.airports_provider.convert_to_channels(airports)

        # Count frequencies by type (CTAF, TWR, GND, ATIS, APP, etc.)
        counts: dict[str, int] = {}
        for ch in channels:
            # Extract type from name e.g. "KTYR CTAF" -> "CTAF"
            parts = ch.name.split()
            type_str = parts[-1] if len(parts) > 1 else "AIR"
            counts[type_str] = counts.get(type_str, 0) + 1

        return AviationResult(
            center_point=center,
            radius_miles=radius_miles,
            matched_airports=airports,
            channels=channels,
            channel_counts_by_type=counts,
        )
