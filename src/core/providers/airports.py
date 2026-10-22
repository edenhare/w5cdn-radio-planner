"""OurAirports Aeronautical Data Provider."""

from __future__ import annotations

from core.models.aviation import AirfieldRecord, AviationFrequency
from core.models.channel import RadioChannel
from core.providers.geocoding import GeoPoint, haversine_distance

OFFLINE_AIRFIELDS: list[AirfieldRecord] = [
    # --- Tyler & East Texas Area Airfields ---
    AirfieldRecord(
        ident="KTYR",
        name="Tyler Pounds Regional Airport",
        latitude=32.3541,
        longitude=-95.4024,
        municipality="Tyler",
        state="TX",
        frequencies=[
            AviationFrequency(type="ATIS", description="Tyler Pounds ATIS", frequencyMhz=126.250),
            AviationFrequency(type="CTAF", description="Tower / CTAF", frequencyMhz=120.100),
            AviationFrequency(type="TWR", description="Pounds Tower", frequencyMhz=120.100),
            AviationFrequency(type="GND", description="Ground Control", frequencyMhz=121.900),
            AviationFrequency(type="UNICOM", description="Tyler UNICOM", frequencyMhz=122.950),
            AviationFrequency(type="APP", description="Fort Worth Center App/Dep", frequencyMhz=135.250),
        ],
    ),
    AirfieldRecord(
        ident="7F3",
        name="Gladewater Municipal Airport",
        latitude=32.5289,
        longitude=-94.9715,
        municipality="Gladewater",
        state="TX",
        frequencies=[
            AviationFrequency(type="CTAF", description="Gladewater CTAF", frequencyMhz=122.900),
        ],
    ),
    AirfieldRecord(
        ident="3F9",
        name="Mineola Wisener Field Airport",
        latitude=32.6776,
        longitude=-95.5105,
        municipality="Mineola",
        state="TX",
        frequencies=[
            AviationFrequency(type="CTAF", description="Wisener CTAF / UNICOM", frequencyMhz=122.800),
        ],
    ),
    AirfieldRecord(
        ident="KJDD",
        name="Wood County Airport (Collins Field)",
        latitude=32.7422,
        longitude=-95.4963,
        municipality="Mineola",
        state="TX",
        frequencies=[
            AviationFrequency(type="AWOS", description="Wood County AWOS-3", frequencyMhz=118.225),
            AviationFrequency(type="CTAF", description="Wood County CTAF / UNICOM", frequencyMhz=123.050),
            AviationFrequency(type="APP", description="Fort Worth Center App/Dep", frequencyMhz=135.250),
        ],
    ),
    AirfieldRecord(
        ident="F12",
        name="Rusk County Airport",
        latitude=32.1404,
        longitude=-94.8529,
        municipality="Henderson",
        state="TX",
        frequencies=[
            AviationFrequency(type="AWOS", description="Rusk County AWOS-3", frequencyMhz=118.675),
            AviationFrequency(type="CTAF", description="Rusk County CTAF / UNICOM", frequencyMhz=122.800),
            AviationFrequency(type="APP", description="Longview Approach", frequencyMhz=128.750),
        ],
    ),
    AirfieldRecord(
        ident="F44",
        name="Athens Municipal Airport",
        latitude=32.1639,
        longitude=-95.8283,
        municipality="Athens",
        state="TX",
        frequencies=[
            AviationFrequency(type="AWOS", description="Athens AWOS-3", frequencyMhz=118.525),
            AviationFrequency(type="CTAF", description="Athens CTAF / UNICOM", frequencyMhz=122.800),
            AviationFrequency(type="APP", description="Fort Worth Center App/Dep", frequencyMhz=135.250),
        ],
    ),
    AirfieldRecord(
        ident="KJSO",
        name="Cherokee County Airport",
        latitude=31.8690,
        longitude=-95.2175,
        municipality="Jacksonville",
        state="TX",
        frequencies=[
            AviationFrequency(type="AWOS", description="Cherokee County AWOS-3", frequencyMhz=119.025),
            AviationFrequency(type="CTAF", description="Cherokee CTAF / UNICOM", frequencyMhz=122.800),
            AviationFrequency(type="APP", description="Fort Worth Center App/Dep", frequencyMhz=135.250),
        ],
    ),
    AirfieldRecord(
        ident="KGGG",
        name="East Texas Regional Airport",
        latitude=32.3840,
        longitude=-94.7115,
        municipality="Longview",
        state="TX",
        frequencies=[
            AviationFrequency(type="ATIS", description="Longview ATIS", frequencyMhz=119.850),
            AviationFrequency(type="CTAF", description="Tower / CTAF", frequencyMhz=119.200),
            AviationFrequency(type="TWR", description="Gregg Tower", frequencyMhz=119.200),
            AviationFrequency(type="GND", description="Ground Control", frequencyMhz=121.600),
            AviationFrequency(type="APP", description="Longview Approach", frequencyMhz=128.750),
        ],
    ),
    AirfieldRecord(
        ident="76F",
        name="Canton-Hackney Airport",
        latitude=32.5818,
        longitude=-95.8636,
        municipality="Canton",
        state="TX",
        frequencies=[
            AviationFrequency(type="CTAF", description="Canton CTAF", frequencyMhz=122.900),
        ],
    ),
    AirfieldRecord(
        ident="KPSN",
        name="Palestine Municipal Airport",
        latitude=31.7797,
        longitude=-95.7064,
        municipality="Palestine",
        state="TX",
        frequencies=[
            AviationFrequency(type="AWOS", description="Palestine AWOS-3", frequencyMhz=118.075),
            AviationFrequency(type="CTAF", description="Palestine CTAF / UNICOM", frequencyMhz=122.800),
        ],
    ),
    AirfieldRecord(
        ident="KASL",
        name="Harrison County Airport",
        latitude=32.5205,
        longitude=-94.3078,
        municipality="Marshall",
        state="TX",
        frequencies=[
            AviationFrequency(type="AWOS", description="Harrison County AWOS-3", frequencyMhz=119.975),
            AviationFrequency(type="CTAF", description="Marshall CTAF / UNICOM", frequencyMhz=122.800),
        ],
    ),
    # --- Shreveport, Bossier, & I-20 Corridor Airfields ---
    AirfieldRecord(
        ident="KSHV",
        name="Shreveport Regional Airport",
        latitude=32.4466,
        longitude=-93.8256,
        municipality="Shreveport",
        state="LA",
        frequencies=[
            AviationFrequency(type="ATIS", description="Shreveport ATIS", frequencyMhz=128.520),
            AviationFrequency(type="CTAF", description="Tower / CTAF", frequencyMhz=121.400),
            AviationFrequency(type="TWR", description="Shreveport Tower", frequencyMhz=121.400),
            AviationFrequency(type="GND", description="Ground Control", frequencyMhz=121.900),
            AviationFrequency(type="APP", description="Shreveport Approach", frequencyMhz=119.900),
        ],
    ),
    AirfieldRecord(
        ident="KDTN",
        name="Shreveport Downtown Airport",
        latitude=32.5402,
        longitude=-93.7450,
        municipality="Shreveport",
        state="LA",
        frequencies=[
            AviationFrequency(type="ATIS", description="Downtown ASOS", frequencyMhz=135.575),
            AviationFrequency(type="CTAF", description="Downtown Tower / CTAF", frequencyMhz=118.400),
            AviationFrequency(type="GND", description="Downtown Ground", frequencyMhz=121.600),
        ],
    ),
    AirfieldRecord(
        ident="KBAD",
        name="Barksdale Air Force Base",
        latitude=32.5018,
        longitude=-93.6627,
        municipality="Bossier City",
        state="LA",
        frequencies=[
            AviationFrequency(type="TWR", description="Barksdale Tower", frequencyMhz=126.200),
            AviationFrequency(type="APP", description="Shreveport Approach", frequencyMhz=123.750),
        ],
    ),
    AirfieldRecord(
        ident="KMLU",
        name="Monroe Regional Airport",
        latitude=32.5109,
        longitude=-92.0377,
        municipality="Monroe",
        state="LA",
        frequencies=[
            AviationFrequency(type="ATIS", description="Monroe ATIS", frequencyMhz=125.050),
            AviationFrequency(type="CTAF", description="Monroe Tower / CTAF", frequencyMhz=118.900),
            AviationFrequency(type="GND", description="Monroe Ground", frequencyMhz=121.900),
            AviationFrequency(type="APP", description="Monroe Approach", frequencyMhz=126.900),
        ],
    ),
    AirfieldRecord(
        ident="KJAN",
        name="Jackson-Medgar Wiley Evers Intl Airport",
        latitude=32.3112,
        longitude=-90.0759,
        municipality="Jackson",
        state="MS",
        frequencies=[
            AviationFrequency(type="ATIS", description="Jackson ATIS", frequencyMhz=120.900),
            AviationFrequency(type="CTAF", description="Jackson Tower / CTAF", frequencyMhz=120.900),
            AviationFrequency(type="TWR", description="Jackson Tower", frequencyMhz=118.700),
            AviationFrequency(type="GND", description="Jackson Ground", frequencyMhz=121.900),
            AviationFrequency(type="APP", description="Jackson Approach", frequencyMhz=123.900),
        ],
    ),
    AirfieldRecord(
        ident="KHKS",
        name="Hawkins Field Airport",
        latitude=32.3341,
        longitude=-90.2222,
        municipality="Jackson",
        state="MS",
        frequencies=[
            AviationFrequency(type="ATIS", description="Hawkins ASOS", frequencyMhz=126.425),
            AviationFrequency(type="CTAF", description="Hawkins Tower / CTAF", frequencyMhz=119.650),
            AviationFrequency(type="GND", description="Hawkins Ground", frequencyMhz=121.700),
        ],
    ),
    # --- Dallas-Fort Worth Metroplex Airfields ---
    AirfieldRecord(
        ident="KDAL",
        name="Dallas Love Field Airport",
        latitude=32.8471,
        longitude=-96.8518,
        municipality="Dallas",
        state="TX",
        frequencies=[
            AviationFrequency(type="ATIS", description="Love ATIS", frequencyMhz=120.150),
            AviationFrequency(type="CTAF", description="Tower / CTAF", frequencyMhz=118.700),
            AviationFrequency(type="TWR", description="Love Tower", frequencyMhz=123.700),
            AviationFrequency(type="GND", description="Ground Control", frequencyMhz=121.750),
        ],
    ),
    AirfieldRecord(
        ident="KDFW",
        name="Dallas/Fort Worth International Airport",
        latitude=32.8998,
        longitude=-97.0403,
        municipality="DFW Airport",
        state="TX",
        frequencies=[
            AviationFrequency(type="ATIS", description="DFW Arrival ATIS", frequencyMhz=123.775),
            AviationFrequency(type="TWR", description="DFW East Tower", frequencyMhz=126.550),
            AviationFrequency(type="TWR", description="DFW West Tower", frequencyMhz=124.150),
            AviationFrequency(type="GND", description="DFW Ground", frequencyMhz=121.800),
            AviationFrequency(type="APP", description="Regional Approach", frequencyMhz=125.025),
        ],
    ),
    AirfieldRecord(
        ident="KADS",
        name="Addison Airport",
        latitude=32.9686,
        longitude=-96.8364,
        municipality="Addison",
        state="TX",
        frequencies=[
            AviationFrequency(type="ATIS", description="Addison ATIS", frequencyMhz=133.400),
            AviationFrequency(type="CTAF", description="Addison Tower / CTAF", frequencyMhz=126.000),
            AviationFrequency(type="GND", description="Addison Ground", frequencyMhz=121.600),
        ],
    ),
    AirfieldRecord(
        ident="KRBD",
        name="Dallas Executive Airport",
        latitude=32.6809,
        longitude=-96.8682,
        municipality="Dallas",
        state="TX",
        frequencies=[
            AviationFrequency(type="ATIS", description="Executive ASOS", frequencyMhz=126.350),
            AviationFrequency(type="CTAF", description="Executive Tower / CTAF", frequencyMhz=127.250),
            AviationFrequency(type="GND", description="Executive Ground", frequencyMhz=121.900),
        ],
    ),
    AirfieldRecord(
        ident="KFTW",
        name="Fort Worth Meacham International Airport",
        latitude=32.8198,
        longitude=-97.3624,
        municipality="Fort Worth",
        state="TX",
        frequencies=[
            AviationFrequency(type="ATIS", description="Meacham ATIS", frequencyMhz=120.700),
            AviationFrequency(type="CTAF", description="Meacham Tower / CTAF", frequencyMhz=118.300),
            AviationFrequency(type="GND", description="Meacham Ground", frequencyMhz=121.900),
        ],
    ),
    AirfieldRecord(
        ident="KGKY",
        name="Arlington Municipal Airport",
        latitude=32.6639,
        longitude=-97.0943,
        municipality="Arlington",
        state="TX",
        frequencies=[
            AviationFrequency(type="ATIS", description="Arlington ASOS", frequencyMhz=127.375),
            AviationFrequency(type="CTAF", description="Arlington Tower / CTAF", frequencyMhz=128.550),
            AviationFrequency(type="GND", description="Arlington Ground", frequencyMhz=121.875),
        ],
    ),
]


class AirportsProvider:
    """Provides airport and aviation frequency queries with local dataset."""

    def __init__(self, airfields: list[AirfieldRecord] | None = None):
        self._airfields = airfields if airfields is not None else OFFLINE_AIRFIELDS

    def find_airports_near(self, lat: float, lon: float, radius_miles: float = 35.0) -> list[AirfieldRecord]:
        """Find airports within radius_miles of coordinate point, sorted by distance ascending."""
        center = GeoPoint(lat=lat, lon=lon)
        matched_with_dist: list[tuple[float, AirfieldRecord]] = []
        for airport in self._airfields:
            pt = GeoPoint(lat=airport.latitude, lon=airport.longitude)
            dist = haversine_distance(center, pt, unit="MILES")
            if dist <= radius_miles:
                matched_with_dist.append((dist, airport))
        matched_with_dist.sort(key=lambda item: item[0])
        return [item[1] for item in matched_with_dist]

    def convert_to_channels(self, airfields: list[AirfieldRecord]) -> list[RadioChannel]:
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
                    state=arpt.state or "TX",
                    lat=arpt.latitude,
                    lon=arpt.longitude,
                    specialType="AVIATION",
                    comment=f"{arpt.name} - {freq.description}",
                )
                channels.append(ch)
                slot += 1
        return channels
