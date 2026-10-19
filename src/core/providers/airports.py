"""OurAirports Aeronautical Data Provider."""

from __future__ import annotations

from core.models.aviation import AirfieldRecord, AviationFrequency
from core.models.channel import RadioChannel
from core.providers.geocoding import GeoPoint, haversine_distance

OFFLINE_AIRFIELDS: list[AirfieldRecord] = [
    AirfieldRecord(
        ident="KTYR",
        name="Tyler Pounds Regional Airport",
        latitude=32.3541,
        longitude=-95.4024,
        municipality="Tyler",
        frequencies=[
            AviationFrequency(
                type="ATIS", description="Tyler Pounds ATIS", frequencyMhz=126.250
            ),
            AviationFrequency(
                type="CTAF", description="Tower / CTAF", frequencyMhz=120.100
            ),
            AviationFrequency(
                type="TWR", description="Pounds Tower", frequencyMhz=120.100
            ),
            AviationFrequency(
                type="GND", description="Ground Control", frequencyMhz=121.900
            ),
            AviationFrequency(
                type="APP", description="Regional Approach", frequencyMhz=128.750
            ),
        ],
    ),
    AirfieldRecord(
        ident="KGGG",
        name="East Texas Regional Airport",
        latitude=32.3840,
        longitude=-94.7115,
        municipality="Longview",
        frequencies=[
            AviationFrequency(
                type="ATIS", description="Longview ATIS", frequencyMhz=119.850
            ),
            AviationFrequency(
                type="CTAF", description="Tower / CTAF", frequencyMhz=119.200
            ),
            AviationFrequency(
                type="TWR", description="Gregg Tower", frequencyMhz=119.200
            ),
            AviationFrequency(
                type="GND", description="Ground Control", frequencyMhz=121.600
            ),
        ],
    ),
    AirfieldRecord(
        ident="KSHV",
        name="Shreveport Regional Airport",
        latitude=32.4466,
        longitude=-93.8256,
        municipality="Shreveport",
        frequencies=[
            AviationFrequency(
                type="ATIS", description="Shreveport ATIS", frequencyMhz=128.520
            ),
            AviationFrequency(
                type="CTAF", description="Tower / CTAF", frequencyMhz=121.400
            ),
            AviationFrequency(
                type="TWR", description="Shreveport Tower", frequencyMhz=121.400
            ),
            AviationFrequency(
                type="GND", description="Ground Control", frequencyMhz=121.120
            ),
        ],
    ),
    AirfieldRecord(
        ident="KDAL",
        name="Dallas Love Field Airport",
        latitude=32.8471,
        longitude=-96.8518,
        municipality="Dallas",
        frequencies=[
            AviationFrequency(
                type="ATIS", description="Love ATIS", frequencyMhz=120.150
            ),
            AviationFrequency(
                type="CTAF", description="Tower / CTAF", frequencyMhz=119.000
            ),
            AviationFrequency(
                type="TWR", description="Love Tower", frequencyMhz=119.000
            ),
            AviationFrequency(
                type="GND", description="Ground Control", frequencyMhz=121.750
            ),
        ],
    ),
]


class AirportsProvider:
    """Provides airport and aviation frequency queries with local dataset."""

    def __init__(self, airfields: list[AirfieldRecord] | None = None):
        self._airfields = airfields if airfields is not None else OFFLINE_AIRFIELDS

    def find_airports_near(
        self, lat: float, lon: float, radius_miles: float = 35.0
    ) -> list[AirfieldRecord]:
        """Find airports within radius_miles of coordinate point."""
        center = GeoPoint(lat=lat, lon=lon)
        matched = []
        for airport in self._airfields:
            pt = GeoPoint(lat=airport.latitude, lon=airport.longitude)
            dist = haversine_distance(center, pt, unit="MILES")
            if dist <= radius_miles:
                matched.append(airport)
        return matched

    def convert_to_channels(
        self, airfields: list[AirfieldRecord]
    ) -> list[RadioChannel]:
        """Convert airfield frequencies to normalized CIR RadioChannel entries."""
        channels: list[RadioChannel] = []
        slot = 1
        for arpt in airfields:
            for freq in arpt.frequencies:
                ch = RadioChannel(
                    number=slot,
                    name=f"{arpt.ident} {freq.type}",
                    callsign=arpt.ident,
                    rxFreq=freq.frequencyMhz,
                    txFreq=freq.frequencyMhz,
                    offset=0.0,
                    offsetDir="off",
                    mode="AM",
                    power="Low",
                    toneMode="None",
                    city=arpt.municipality,
                    lat=arpt.latitude,
                    lon=arpt.longitude,
                    specialType="AVIATION",
                    comment=f"{arpt.name} - {freq.description}",
                )
                channels.append(ch)
                slot += 1
        return channels
