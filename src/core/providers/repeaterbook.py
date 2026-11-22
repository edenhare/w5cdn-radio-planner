"""RepeaterBook REST API Client and Local Cache Provider."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime
from pathlib import Path

import httpx

from core.config.paths import get_data_dir
from core.models.channel import RadioChannel

logger = logging.getLogger(__name__)

# Comprehensive offline repeaters along I-20 corridor (Tyler, TX -> Shreveport, LA -> Jackson, MS)
# and Dallas-Fort Worth metro area
OFFLINE_REPEATERS: list[dict] = [
    # Tyler, TX Area (Smith County)
    {
        "name": "Tyler RPT 146.94",
        "callsign": "W5ETX",
        "rxFreq": 146.94000,
        "txFreq": 146.34000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Tyler",
        "state": "TX",
        "lat": 32.3513,
        "lon": -95.3011,
        "comment": "Smith County ARES / Tyler ARC Primary",
    },
    {
        "name": "Tyler UHF 442.20",
        "callsign": "W5ETX",
        "rxFreq": 442.20000,
        "txFreq": 447.20000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Tyler",
        "state": "TX",
        "lat": 32.3600,
        "lon": -95.3100,
        "comment": "Tyler UHF Wide Area Link",
    },
    {
        "name": "Tyler 145.430",
        "callsign": "K5TYR",
        "rxFreq": 145.43000,
        "txFreq": 144.83000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Tyler",
        "state": "TX",
        "lat": 32.3450,
        "lon": -95.2900,
        "comment": "Smith County Emergency Hospital Net",
    },
    {
        "name": "Tyler DMR 444.85",
        "callsign": "W5ETX",
        "rxFreq": 444.85000,
        "txFreq": 449.85000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 1,
        "city": "Tyler",
        "state": "TX",
        "lat": 32.3550,
        "lon": -95.3050,
        "comment": "Tyler East DMR Repeater",
    },
    {
        "name": "Lindale 147.08",
        "callsign": "N5LND",
        "rxFreq": 147.08000,
        "txFreq": 147.68000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Lindale",
        "state": "TX",
        "lat": 32.5085,
        "lon": -95.4080,
        "comment": "Lindale I-20 North Skywarn",
    },
    # Kilgore / Gladewater, TX
    {
        "name": "Kilgore 146.68",
        "callsign": "K5KIL",
        "rxFreq": 146.68000,
        "txFreq": 146.08000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Kilgore",
        "state": "TX",
        "lat": 32.3860,
        "lon": -94.8755,
        "comment": "Kilgore ARC Repeater",
    },
    {
        "name": "Kilgore DMR 443.40",
        "callsign": "W5KIL",
        "rxFreq": 443.40000,
        "txFreq": 448.40000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 1,
        "city": "Kilgore",
        "state": "TX",
        "lat": 32.3900,
        "lon": -94.8800,
        "comment": "Kilgore DMR BrandMeister",
    },
    # Longview, TX Area (Gregg County)
    {
        "name": "Longview 147.34",
        "callsign": "K5LTR",
        "rxFreq": 147.34000,
        "txFreq": 147.94000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Longview",
        "state": "TX",
        "lat": 32.5007,
        "lon": -94.7405,
        "comment": "Gregg County East Texas Repeater Association",
    },
    {
        "name": "Longview UHF 444.35",
        "callsign": "K5LTR",
        "rxFreq": 444.35000,
        "txFreq": 449.35000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Longview",
        "state": "TX",
        "lat": 32.5100,
        "lon": -94.7300,
        "comment": "Longview UHF Wide Area Net",
    },
    {
        "name": "Longview 146.74",
        "callsign": "W5LOK",
        "rxFreq": 146.74000,
        "txFreq": 146.14000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Longview",
        "state": "TX",
        "lat": 32.4950,
        "lon": -94.7500,
        "comment": "Longview South Emergency Net",
    },
    {
        "name": "Longview DMR 442.85",
        "callsign": "N5ETX",
        "rxFreq": 442.85000,
        "txFreq": 447.85000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 2,
        "timeSlot": 1,
        "city": "Longview",
        "state": "TX",
        "lat": 32.5050,
        "lon": -94.7450,
        "comment": "Longview DMR Repeater",
    },
    # Marshall / Waskom, TX (Harrison County)
    {
        "name": "Marshall 147.12",
        "callsign": "W5MHL",
        "rxFreq": 147.12000,
        "txFreq": 147.72000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Marshall",
        "state": "TX",
        "lat": 32.5449,
        "lon": -94.3674,
        "comment": "Harrison County Amateur Radio Club",
    },
    {
        "name": "Marshall UHF 444.40",
        "callsign": "W5MHL",
        "rxFreq": 444.40000,
        "txFreq": 449.40000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Marshall",
        "state": "TX",
        "lat": 32.5500,
        "lon": -94.3600,
        "comment": "Marshall UHF Emergency Services",
    },
    {
        "name": "Waskom 147.24",
        "callsign": "K5WSK",
        "rxFreq": 147.24000,
        "txFreq": 147.84000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Waskom",
        "state": "TX",
        "lat": 32.4746,
        "lon": -94.0621,
        "comment": "TX-LA Border I-20 Travel Link",
    },
    # Shreveport / Bossier City, LA (Caddo / Bossier Parishes)
    {
        "name": "Greenwood 147.18",
        "callsign": "N5GWD",
        "rxFreq": 147.18000,
        "txFreq": 147.78000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "186.2",
        "city": "Greenwood",
        "state": "LA",
        "lat": 32.4418,
        "lon": -93.9735,
        "comment": "Greenwood West Shreveport Gateway",
    },
    {
        "name": "Shreveport 146.82",
        "callsign": "K5SHV",
        "rxFreq": 146.82000,
        "txFreq": 146.22000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "186.2",
        "city": "Shreveport",
        "state": "LA",
        "lat": 32.5252,
        "lon": -93.7502,
        "comment": "Shreveport Amateur Radio Association",
    },
    {
        "name": "Shreveport DMR 444.1",
        "callsign": "W5LA",
        "rxFreq": 444.10000,
        "txFreq": 449.10000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 1,
        "city": "Shreveport",
        "state": "LA",
        "lat": 32.5300,
        "lon": -93.7600,
        "comment": "Shreveport DMR Regional Hub",
    },
    {
        "name": "Shreveport 146.64",
        "callsign": "W5SRA",
        "rxFreq": 146.64000,
        "txFreq": 146.04000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "186.2",
        "city": "Shreveport",
        "state": "LA",
        "lat": 32.5100,
        "lon": -93.7400,
        "comment": "Caddo Parish ARES Net",
    },
    {
        "name": "Shreveport UHF 443.20",
        "callsign": "K5SHV",
        "rxFreq": 443.20000,
        "txFreq": 448.20000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "186.2",
        "city": "Shreveport",
        "state": "LA",
        "lat": 32.5200,
        "lon": -93.7550,
        "comment": "Shreveport UHF Wide Area Net",
    },
    {
        "name": "Bossier City 147.39",
        "callsign": "W5BCR",
        "rxFreq": 147.39000,
        "txFreq": 147.99000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "186.2",
        "city": "Bossier City",
        "state": "LA",
        "lat": 32.5160,
        "lon": -93.7321,
        "comment": "Bossier Parish Skywarn Repeater",
    },
    {
        "name": "Bossier City DMR 444.75",
        "callsign": "K5BC",
        "rxFreq": 444.75000,
        "txFreq": 449.75000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 2,
        "city": "Bossier City",
        "state": "LA",
        "lat": 32.5200,
        "lon": -93.7250,
        "comment": "Bossier City DMR BrandMeister",
    },
    {
        "name": "Haughton 145.15",
        "callsign": "N5HGT",
        "rxFreq": 145.15000,
        "txFreq": 144.55000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "186.2",
        "city": "Haughton",
        "state": "LA",
        "lat": 32.5304,
        "lon": -93.5427,
        "comment": "Haughton I-20 Travel Link",
    },
    # Minden / Arcadia, LA (Webster / Bienville Parishes)
    {
        "name": "Minden 147.30",
        "callsign": "W5MND",
        "rxFreq": 147.30000,
        "txFreq": 147.90000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "186.2",
        "city": "Minden",
        "state": "LA",
        "lat": 32.6154,
        "lon": -93.2868,
        "comment": "Webster Parish Amateur Radio Club",
    },
    {
        "name": "Minden UHF 443.85",
        "callsign": "W5MND",
        "rxFreq": 443.85000,
        "txFreq": 448.85000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "186.2",
        "city": "Minden",
        "state": "LA",
        "lat": 32.6100,
        "lon": -93.2800,
        "comment": "Minden UHF Emergency Net",
    },
    {
        "name": "Arcadia 147.06",
        "callsign": "N5ARC",
        "rxFreq": 147.06000,
        "txFreq": 147.66000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Arcadia",
        "state": "LA",
        "lat": 32.5532,
        "lon": -92.9224,
        "comment": "Bienville Parish ARES Corridor Link",
    },
    # Ruston, LA (Lincoln Parish)
    {
        "name": "Ruston 146.94",
        "callsign": "W5LGT",
        "rxFreq": 146.94000,
        "txFreq": 146.34000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Ruston",
        "state": "LA",
        "lat": 32.5232,
        "lon": -92.6379,
        "comment": "Lincoln Parish ARC Primary",
    },
    {
        "name": "Ruston UHF 444.50",
        "callsign": "W5LGT",
        "rxFreq": 444.50000,
        "txFreq": 449.50000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Ruston",
        "state": "LA",
        "lat": 32.5250,
        "lon": -92.6300,
        "comment": "Louisiana Tech Campus UHF Net",
    },
    {
        "name": "Ruston DMR 147.18",
        "callsign": "K5LGT",
        "rxFreq": 147.18000,
        "txFreq": 147.78000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 1,
        "city": "Ruston",
        "state": "LA",
        "lat": 32.5200,
        "lon": -92.6400,
        "comment": "Ruston VHF DMR Repeater",
    },
    # West Monroe / Monroe, LA (Ouachita Parish)
    {
        "name": "West Monroe 146.85",
        "callsign": "W5WMO",
        "rxFreq": 146.85000,
        "txFreq": 146.25000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "West Monroe",
        "state": "LA",
        "lat": 32.5185,
        "lon": -92.1474,
        "comment": "West Monroe ARC Repeater",
    },
    {
        "name": "Monroe 146.70",
        "callsign": "W5MRO",
        "rxFreq": 146.70000,
        "txFreq": 146.10000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Monroe",
        "state": "LA",
        "lat": 32.5093,
        "lon": -92.1193,
        "comment": "Ouachita Valley ARC Primary",
    },
    {
        "name": "Monroe UHF 444.90",
        "callsign": "W5MRO",
        "rxFreq": 444.90000,
        "txFreq": 449.90000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Monroe",
        "state": "LA",
        "lat": 32.5050,
        "lon": -92.1150,
        "comment": "Ouachita Valley UHF Skywarn Net",
    },
    {
        "name": "Monroe DMR 442.15",
        "callsign": "K5OVR",
        "rxFreq": 442.15000,
        "txFreq": 447.15000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 1,
        "city": "Monroe",
        "state": "LA",
        "lat": 32.5150,
        "lon": -92.1250,
        "comment": "Monroe Metro DMR Hub",
    },
    # Rayville / Delhi / Tallulah, LA (Richland / Madison Parishes)
    {
        "name": "Rayville 147.15",
        "callsign": "N5RYV",
        "rxFreq": 147.15000,
        "txFreq": 147.75000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Rayville",
        "state": "LA",
        "lat": 32.4743,
        "lon": -91.7543,
        "comment": "Richland Parish ARES",
    },
    {
        "name": "Delhi 146.61",
        "callsign": "W5DLH",
        "rxFreq": 146.61000,
        "txFreq": 146.01000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Delhi",
        "state": "LA",
        "lat": 32.4549,
        "lon": -91.4937,
        "comment": "Delhi I-20 Travel Net",
    },
    {
        "name": "Tallulah 147.03",
        "callsign": "W5TLH",
        "rxFreq": 147.03000,
        "txFreq": 147.63000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Tallulah",
        "state": "LA",
        "lat": 32.4085,
        "lon": -91.1868,
        "comment": "Madison Parish Emergency Net",
    },
    {
        "name": "Tallulah UHF 443.70",
        "callsign": "W5TLH",
        "rxFreq": 443.70000,
        "txFreq": 448.70000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Tallulah",
        "state": "LA",
        "lat": 32.4050,
        "lon": -91.1800,
        "comment": "Tallulah UHF Link to Mississippi",
    },
    # Vicksburg, MS (Warren County)
    {
        "name": "Vicksburg 146.91",
        "callsign": "W5VBG",
        "rxFreq": 146.91000,
        "txFreq": 146.31000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Vicksburg",
        "state": "MS",
        "lat": 32.3526,
        "lon": -90.8779,
        "comment": "Vicksburg Amateur Radio Club Primary",
    },
    {
        "name": "Vicksburg UHF 444.60",
        "callsign": "W5VBG",
        "rxFreq": 444.60000,
        "txFreq": 449.60000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Vicksburg",
        "state": "MS",
        "lat": 32.3550,
        "lon": -90.8750,
        "comment": "Vicksburg UHF Wide Area Skywarn",
    },
    {
        "name": "Vicksburg DMR 147.27",
        "callsign": "K5VBG",
        "rxFreq": 147.27000,
        "txFreq": 147.87000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 1,
        "city": "Vicksburg",
        "state": "MS",
        "lat": 32.3500,
        "lon": -90.8800,
        "comment": "Warren County DMR Repeater",
    },
    # Edwards / Clinton, MS (Hinds County West)
    {
        "name": "Edwards 147.36",
        "callsign": "N5EDW",
        "rxFreq": 147.36000,
        "txFreq": 147.96000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Edwards",
        "state": "MS",
        "lat": 32.3307,
        "lon": -90.6051,
        "comment": "Edwards I-20 Travel Corridor Net",
    },
    {
        "name": "Clinton 147.12",
        "callsign": "W5CLN",
        "rxFreq": 147.12000,
        "txFreq": 147.72000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Clinton",
        "state": "MS",
        "lat": 32.3415,
        "lon": -90.3218,
        "comment": "Hinds County West ARES",
    },
    {
        "name": "Clinton UHF 444.05",
        "callsign": "W5CLN",
        "rxFreq": 444.05000,
        "txFreq": 449.05000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Clinton",
        "state": "MS",
        "lat": 32.3450,
        "lon": -90.3200,
        "comment": "Clinton UHF Skywarn Link",
    },
    # Jackson, MS Metro Area (Hinds / Rankin / Madison Counties)
    {
        "name": "Jackson 146.76",
        "callsign": "W5MS",
        "rxFreq": 146.76000,
        "txFreq": 146.16000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Jackson",
        "state": "MS",
        "lat": 32.2988,
        "lon": -90.1848,
        "comment": "Jackson ARC Central MS Primary",
    },
    {
        "name": "Jackson UHF 444.70",
        "callsign": "W5MS",
        "rxFreq": 444.70000,
        "txFreq": 449.70000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Jackson",
        "state": "MS",
        "lat": 32.3000,
        "lon": -90.1800,
        "comment": "Jackson ARC UHF Wide Area",
    },
    {
        "name": "Jackson DMR 145.39",
        "callsign": "K5JCK",
        "rxFreq": 145.39000,
        "txFreq": 144.79000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 1,
        "city": "Jackson",
        "state": "MS",
        "lat": 32.2950,
        "lon": -90.1900,
        "comment": "Jackson Metro DMR VHF Hub",
    },
    {
        "name": "Jackson 146.94",
        "callsign": "K5MS",
        "rxFreq": 146.94000,
        "txFreq": 146.34000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Jackson",
        "state": "MS",
        "lat": 32.3050,
        "lon": -90.1750,
        "comment": "Hinds County Emergency Services Net",
    },
    {
        "name": "Pearl 147.33",
        "callsign": "W5PRL",
        "rxFreq": 147.33000,
        "txFreq": 147.93000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Pearl",
        "state": "MS",
        "lat": 32.2743,
        "lon": -90.1320,
        "comment": "Rankin County ARES Primary",
    },
    {
        "name": "Brandon 145.23",
        "callsign": "W5BDN",
        "rxFreq": 145.23000,
        "txFreq": 144.63000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Brandon",
        "state": "MS",
        "lat": 32.2732,
        "lon": -89.9859,
        "comment": "Brandon Metro Repeater",
    },
    {
        "name": "Brandon UHF 442.50",
        "callsign": "W5BDN",
        "rxFreq": 442.50000,
        "txFreq": 447.50000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Brandon",
        "state": "MS",
        "lat": 32.2750,
        "lon": -89.9800,
        "comment": "Brandon UHF Emergency Link",
    },
    {
        "name": "Madison 146.88",
        "callsign": "W5MAD",
        "rxFreq": 146.88000,
        "txFreq": 146.28000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Madison",
        "state": "MS",
        "lat": 32.4607,
        "lon": -90.1154,
        "comment": "Madison County ARC North Net",
    },
    {
        "name": "Madison DMR 444.25",
        "callsign": "N5MAD",
        "rxFreq": 444.25000,
        "txFreq": 449.25000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 2,
        "city": "Madison",
        "state": "MS",
        "lat": 32.4550,
        "lon": -90.1200,
        "comment": "Madison DMR BrandMeister Hub",
    },
    # Dallas / Fort Worth Metro Area (Proximity Mode Test Data)
    {
        "name": "Dallas 146.88",
        "callsign": "W5FC",
        "rxFreq": 146.88000,
        "txFreq": 146.28000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Dallas",
        "state": "TX",
        "lat": 32.7767,
        "lon": -96.7970,
        "comment": "Dallas Amateur Radio Club Primary",
    },
    {
        "name": "Dallas 442.075 DMR",
        "callsign": "W5DFW",
        "rxFreq": 442.07500,
        "txFreq": 447.07500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "DMR",
        "toneMode": "None",
        "colorCode": 1,
        "timeSlot": 1,
        "city": "Dallas",
        "state": "TX",
        "lat": 32.7900,
        "lon": -96.8000,
        "comment": "Dallas Metro DMR Repeater",
    },
    {
        "name": "Dallas 145.27",
        "callsign": "K5DLS",
        "rxFreq": 145.27000,
        "txFreq": 144.67000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Dallas",
        "state": "TX",
        "lat": 32.7800,
        "lon": -96.8100,
        "comment": "Dallas County ARES Net",
    },
    {
        "name": "Dallas UHF 444.10",
        "callsign": "W5FC",
        "rxFreq": 444.10000,
        "txFreq": 449.10000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Dallas",
        "state": "TX",
        "lat": 32.7700,
        "lon": -96.7900,
        "comment": "Dallas ARC UHF Link",
    },
    {
        "name": "Fort Worth 146.94",
        "callsign": "W5FW",
        "rxFreq": 146.94000,
        "txFreq": 146.34000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Fort Worth",
        "state": "TX",
        "lat": 32.7555,
        "lon": -97.3308,
        "comment": "Kilocycle Club of Fort Worth",
    },
    {
        "name": "Fort Worth 444.20",
        "callsign": "W5FW",
        "rxFreq": 444.20000,
        "txFreq": 449.20000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Fort Worth",
        "state": "TX",
        "lat": 32.7500,
        "lon": -97.3200,
        "comment": "Fort Worth UHF Wide Area",
    },
    {
        "name": "Arlington 147.14",
        "callsign": "K5ARL",
        "rxFreq": 147.14000,
        "txFreq": 147.74000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Arlington",
        "state": "TX",
        "lat": 32.7357,
        "lon": -97.1081,
        "comment": "Arlington ARC Primary",
    },
    {
        "name": "Irving 146.72",
        "callsign": "W5IRV",
        "rxFreq": 146.72000,
        "txFreq": 146.12000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Irving",
        "state": "TX",
        "lat": 32.8140,
        "lon": -96.9489,
        "comment": "Irving ARC Repeater",
    },
    {
        "name": "Garland 146.66",
        "callsign": "K5GAR",
        "rxFreq": 146.66000,
        "txFreq": 146.06000,
        "offset": 0.60000,
        "offsetDir": "-",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Garland",
        "state": "TX",
        "lat": 32.9126,
        "lon": -96.6389,
        "comment": "Garland ARC Primary Net",
    },
    {
        "name": "Plano 147.18",
        "callsign": "K5PLN",
        "rxFreq": 147.18000,
        "txFreq": 147.78000,
        "offset": 0.60000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Plano",
        "state": "TX",
        "lat": 33.0198,
        "lon": -96.6989,
        "comment": "Plano ARES Emergency Net",
    },
]

# Built-in Regional GMRS Repeater Database (462.550 - 462.725 MHz, +5.000 MHz offset)
# RepeaterBook's Ham API only covers amateur radio bands; this dataset provides regional
# GMRS repeaters for Route Corridor and Proximity Ring planning.
GMRS_REPEATERS: list[dict] = [
    {
        "name": "Tyler 462.675",
        "callsign": "WRTX675",
        "rxFreq": 462.67500,
        "txFreq": 467.67500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Tyler",
        "state": "TX",
        "lat": 32.3450,
        "lon": -95.2980,
        "comment": "Tyler East Texas GMRS 675 Travel Tone Repeater",
    },
    {
        "name": "Tyler 462.600",
        "callsign": "WRTX600",
        "rxFreq": 462.60000,
        "txFreq": 467.60000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Tyler",
        "state": "TX",
        "lat": 32.3320,
        "lon": -95.3120,
        "comment": "Smith County GMRS 600 Wide-Area Repeater",
    },
    {
        "name": "Lindale 462.550",
        "callsign": "WRLN550",
        "rxFreq": 462.55000,
        "txFreq": 467.55000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Lindale",
        "state": "TX",
        "lat": 32.5160,
        "lon": -95.4090,
        "comment": "Lindale I-20 Corridor GMRS 550 Repeater",
    },
    {
        "name": "Longview 462.625",
        "callsign": "WRLV625",
        "rxFreq": 462.62500,
        "txFreq": 467.62500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Longview",
        "state": "TX",
        "lat": 32.5007,
        "lon": -94.7405,
        "comment": "Longview Gregg County GMRS 625 Repeater",
    },
    {
        "name": "Kilgore 462.700",
        "callsign": "WRKG700",
        "rxFreq": 462.70000,
        "txFreq": 467.70000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Kilgore",
        "state": "TX",
        "lat": 32.3863,
        "lon": -94.8758,
        "comment": "Kilgore I-20 East Texas GMRS 700 Repeater",
    },
    {
        "name": "Marshall 462.650",
        "callsign": "WRMR650",
        "rxFreq": 462.65000,
        "txFreq": 467.65000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Marshall",
        "state": "TX",
        "lat": 32.5449,
        "lon": -94.3674,
        "comment": "Marshall Harrison County GMRS 650 Repeater",
    },
    {
        "name": "Canton 462.725",
        "callsign": "WRCN725",
        "rxFreq": 462.72500,
        "txFreq": 467.72500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Canton",
        "state": "TX",
        "lat": 32.5565,
        "lon": -95.8633,
        "comment": "Canton Van Zandt I-20 GMRS 725 Repeater",
    },
    {
        "name": "Athens 462.575",
        "callsign": "WRAT575",
        "rxFreq": 462.57500,
        "txFreq": 467.57500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "123.0",
        "city": "Athens",
        "state": "TX",
        "lat": 32.2049,
        "lon": -95.8555,
        "comment": "Athens Henderson County GMRS 575 Repeater",
    },
    {
        "name": "Jacksonville 462.650",
        "callsign": "WRJK650",
        "rxFreq": 462.65000,
        "txFreq": 467.65000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "136.5",
        "city": "Jacksonville",
        "state": "TX",
        "lat": 31.9638,
        "lon": -95.2705,
        "comment": "Jacksonville Cherokee County GMRS 650 Repeater",
    },
    {
        "name": "Dallas 462.675",
        "callsign": "WRDL675",
        "rxFreq": 462.67500,
        "txFreq": 467.67500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Dallas",
        "state": "TX",
        "lat": 32.7767,
        "lon": -96.7970,
        "comment": "Dallas Metroplex GMRS 675 Travel Tone Repeater",
    },
    {
        "name": "Dallas 462.600",
        "callsign": "WRDL600",
        "rxFreq": 462.60000,
        "txFreq": 467.60000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Dallas",
        "state": "TX",
        "lat": 32.7900,
        "lon": -96.8100,
        "comment": "North Texas GMRS 600 Linked Repeater",
    },
    {
        "name": "Fort Worth 462.550",
        "callsign": "WRFW550",
        "rxFreq": 462.55000,
        "txFreq": 467.55000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "110.9",
        "city": "Fort Worth",
        "state": "TX",
        "lat": 32.7555,
        "lon": -97.3308,
        "comment": "Fort Worth Tarrant GMRS 550 Repeater",
    },
    {
        "name": "Terrell 462.575",
        "callsign": "WRTR575",
        "rxFreq": 462.57500,
        "txFreq": 467.57500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Terrell",
        "state": "TX",
        "lat": 32.7359,
        "lon": -96.2753,
        "comment": "Terrell Kaufman County I-20 GMRS 575 Repeater",
    },
    {
        "name": "Houston 462.675",
        "callsign": "WRHT675",
        "rxFreq": 462.67500,
        "txFreq": 467.67500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Houston",
        "state": "TX",
        "lat": 29.7604,
        "lon": -95.3698,
        "comment": "Houston Metro GMRS 675 Travel Tone Repeater",
    },
    {
        "name": "Austin 462.625",
        "callsign": "WRAU625",
        "rxFreq": 462.62500,
        "txFreq": 467.62500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Austin",
        "state": "TX",
        "lat": 30.2672,
        "lon": -97.7431,
        "comment": "Austin Central Texas GMRS 625 Repeater",
    },
    {
        "name": "Shreveport 462.675",
        "callsign": "WRSH675",
        "rxFreq": 462.67500,
        "txFreq": 467.67500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Shreveport",
        "state": "LA",
        "lat": 32.5252,
        "lon": -93.7502,
        "comment": "Shreveport Ark-La-Tex GMRS 675 Travel Tone Repeater",
    },
    {
        "name": "Bossier City 462.575",
        "callsign": "WRBC575",
        "rxFreq": 462.57500,
        "txFreq": 467.57500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "107.2",
        "city": "Bossier City",
        "state": "LA",
        "lat": 32.5160,
        "lon": -93.7321,
        "comment": "Bossier City I-20 GMRS 575 Repeater",
    },
    {
        "name": "Minden 462.600",
        "callsign": "WRMN600",
        "rxFreq": 462.60000,
        "txFreq": 467.60000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Minden",
        "state": "LA",
        "lat": 32.6154,
        "lon": -93.2868,
        "comment": "Minden Webster Parish I-20 GMRS 600 Repeater",
    },
    {
        "name": "Ruston 462.650",
        "callsign": "WRRS650",
        "rxFreq": 462.65000,
        "txFreq": 467.65000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Ruston",
        "state": "LA",
        "lat": 32.5232,
        "lon": -92.6379,
        "comment": "Ruston Lincoln Parish I-20 GMRS 650 Repeater",
    },
    {
        "name": "Monroe 462.700",
        "callsign": "WRMO700",
        "rxFreq": 462.70000,
        "txFreq": 467.70000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Monroe",
        "state": "LA",
        "lat": 32.5093,
        "lon": -92.1193,
        "comment": "Monroe Northeast Louisiana GMRS 700 Repeater",
    },
    {
        "name": "Tallulah 462.550",
        "callsign": "WRTL550",
        "rxFreq": 462.55000,
        "txFreq": 467.55000,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Tallulah",
        "state": "LA",
        "lat": 32.4085,
        "lon": -91.1868,
        "comment": "Tallulah I-20 Mississippi River GMRS 550 Repeater",
    },
    {
        "name": "Vicksburg 462.625",
        "callsign": "WRVK625",
        "rxFreq": 462.62500,
        "txFreq": 467.62500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Vicksburg",
        "state": "MS",
        "lat": 32.3526,
        "lon": -90.8779,
        "comment": "Vicksburg Warren County I-20 GMRS 625 Repeater",
    },
    {
        "name": "Clinton 462.575",
        "callsign": "WRCL575",
        "rxFreq": 462.57500,
        "txFreq": 467.57500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Clinton",
        "state": "MS",
        "lat": 32.3415,
        "lon": -90.3218,
        "comment": "Clinton Hinds County I-20 GMRS 575 Repeater",
    },
    {
        "name": "Jackson 462.675",
        "callsign": "WRJX675",
        "rxFreq": 462.67500,
        "txFreq": 467.67500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "141.3",
        "city": "Jackson",
        "state": "MS",
        "lat": 32.2988,
        "lon": -90.1848,
        "comment": "Jackson Metro GMRS 675 Travel Tone Repeater",
    },
    {
        "name": "Jackson 462.725",
        "callsign": "WRJX725",
        "rxFreq": 462.72500,
        "txFreq": 467.72500,
        "offset": 5.00000,
        "offsetDir": "+",
        "mode": "FM",
        "toneMode": "Tone",
        "ctcss": "100.0",
        "city": "Jackson",
        "state": "MS",
        "lat": 32.3100,
        "lon": -90.1750,
        "comment": "Central Mississippi GMRS 725 Wide-Area Repeater",
    },
]

US_STATE_ABBR: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
    # Canadian Provinces & Territories
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB",
    "newfoundland": "NL", "newfoundland and labrador": "NL", "northwest territories": "NT",
    "nova scotia": "NS", "nunavut": "NU", "ontario": "ON", "prince edward island": "PE",
    "quebec": "QC", "saskatchewan": "SK", "yukon": "YT", "yukon territory": "YT",
}

FIPS_STATE_ABBR: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY",
    "1": "AL", "2": "AK", "4": "AZ", "5": "AR", "6": "CA", "8": "CO", "9": "CT",
    # Canadian Provinces & Territories (RepeaterBook CA state_id codes)
    "CA01": "AB", "CA02": "BC", "CA03": "MB", "CA04": "NB", "CA05": "NL",
    "CA06": "NT", "CA07": "NS", "CA08": "ON", "CA09": "PE", "CA10": "QC",
    "CA11": "SK", "CA12": "YT", "CA13": "NT", "CA14": "NU",
}


STATE_TO_FIPS: dict[str, str] = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09",
    "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17",
    "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31",
    "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54",
    "WI": "55", "WY": "56",
    # Canadian Provinces & Territories
    "AB": "CA01", "BC": "CA02", "MB": "CA03", "NB": "CA04", "NL": "CA05",
    "NT": "CA06", "NS": "CA07", "ON": "CA08", "PE": "CA09", "QC": "CA10",
    "SK": "CA11", "YT": "CA12", "NU": "CA14",
}


# Geographic bounding regions (min_lat, max_lat, min_lon, max_lon) for US states & Canadian provinces
US_STATE_REGIONS: dict[str, list[tuple[float, float, float, float]]] = {
    "AL": [(30.22, 35.01, -88.47, -84.89)],
    "AK": [(51.21, 71.37, -179.15, -129.98)],
    "AZ": [(31.33, 37.00, -114.82, -109.05)],
    "AR": [(33.00, 36.50, -94.62, -89.64)],
    "CA": [(32.53, 42.01, -124.41, -114.13)],
    "CO": [(36.99, 41.00, -109.06, -102.04)],
    "CT": [(40.98, 42.05, -73.73, -71.79)],
    "DC": [(38.79, 38.99, -77.12, -76.91)],
    "DE": [(38.45, 39.84, -75.79, -75.05)],
    "FL": [(24.52, 30.70, -83.50, -80.03), (29.50, 31.00, -87.63, -82.00)],
    "GA": [(30.36, 35.00, -85.61, -80.84)],
    "HI": [(18.91, 22.24, -160.25, -154.81)],
    "ID": [(41.99, 49.00, -117.24, -111.04)],
    "IL": [(36.97, 42.51, -91.51, -87.49)],
    "IN": [(37.77, 41.76, -88.10, -84.78)],
    "IA": [(40.38, 43.50, -96.64, -90.14)],
    "KS": [(36.99, 40.00, -102.05, -94.59)],
    "KY": [(36.50, 39.15, -89.57, -81.96)],
    "LA": [(31.00, 33.02, -94.04, -90.90), (28.93, 31.00, -94.04, -88.82)],
    "ME": [(43.06, 47.46, -71.08, -66.95)],
    "MD": [(37.91, 39.72, -79.49, -75.05)],
    "MA": [(41.24, 42.89, -73.51, -69.93)],
    "MI": [(41.70, 48.24, -90.42, -82.41)],
    "MN": [(43.50, 49.38, -97.24, -89.49)],
    "MS": [(31.00, 35.00, -91.65, -88.10), (30.15, 31.00, -89.75, -88.10)],
    "MO": [(35.99, 40.61, -95.77, -89.10)],
    "MT": [(44.36, 49.00, -116.05, -104.04)],
    "NE": [(40.00, 43.00, -104.05, -95.31)],
    "NV": [(35.00, 42.00, -120.01, -114.04)],
    "NH": [(42.70, 45.31, -72.56, -70.61)],
    "NJ": [(38.93, 41.36, -75.56, -73.89)],
    "NM": [(31.33, 37.00, -109.05, -103.00)],
    "NY": [(40.50, 45.01, -79.76, -71.86)],
    "NC": [(33.84, 36.59, -84.32, -75.46)],
    "ND": [(45.94, 49.00, -104.05, -96.55)],
    "OH": [(38.40, 41.98, -84.82, -80.52)],
    "OK": [(33.62, 37.00, -100.00, -94.43), (36.50, 37.00, -103.00, -100.00)],
    "OR": [(41.99, 46.29, -124.57, -116.46)],
    "PA": [(39.72, 42.27, -80.52, -74.69)],
    "RI": [(41.15, 42.02, -71.86, -71.12)],
    "SC": [(32.03, 35.22, -83.35, -78.54)],
    "SD": [(42.48, 45.95, -104.06, -96.44)],
    "TN": [(34.98, 36.68, -90.31, -81.65)],
    "TX": [(25.84, 34.00, -106.65, -93.51), (34.00, 36.50, -103.05, -100.00)],
    "UT": [(37.00, 42.00, -114.05, -109.04)],
    "VT": [(42.73, 45.02, -73.44, -71.46)],
    "VA": [(36.54, 39.47, -83.68, -75.24)],
    "WA": [(45.54, 49.00, -124.85, -116.92)],
    "WV": [(37.20, 40.64, -82.64, -77.72)],
    "WI": [(42.49, 47.08, -92.89, -86.81)],
    "WY": [(40.99, 45.01, -111.06, -104.05)],
    # Canadian Provinces & Territories (lat, lon bounding boxes)
    "AB": [(49.00, 60.00, -120.00, -110.00)],
    "BC": [(48.30, 50.00, -139.06, -114.05), (50.00, 60.00, -139.06, -115.50)],
    "MB": [(49.00, 60.00, -102.00, -88.98)],
    "NB": [(44.60, 48.07, -69.06, -63.77)],
    "NL": [(46.61, 51.65, -59.42, -52.62), (51.65, 60.38, -67.80, -55.62)],
    "NS": [(43.42, 47.03, -66.32, -59.68)],
    "NT": [(60.00, 78.76, -136.44, -102.00)],
    "NU": [(60.00, 83.11, -120.68, -61.08)],
    "ON": [(41.68, 46.50, -83.15, -74.34), (46.50, 56.86, -95.15, -79.00)],
    "PE": [(45.95, 47.06, -64.41, -61.97)],
    "QC": [(45.00, 49.50, -79.52, -64.15), (49.50, 62.58, -79.76, -57.10)],
    "SK": [(49.00, 60.00, -110.00, -101.36)],
    "YT": [(60.00, 69.65, -141.00, -123.81)],
}


def resolve_state_code(item: dict) -> str:
    """Resolve standard two-letter state abbreviation or uppercase name for state file naming."""
    state_name = str(item.get("State", "")).strip().lower()
    if state_name in US_STATE_ABBR:
        return US_STATE_ABBR[state_name]
    state_id = str(item.get("State ID", "")).strip()
    if state_id in FIPS_STATE_ABBR:
        return FIPS_STATE_ABBR[state_id]
    if len(state_name) == 2 and state_name.isalpha():
        return state_name.upper()
    return state_name.upper() if state_name else (state_id or "UNKNOWN")


def extract_state_from_text(text: str) -> str | None:
    """Extract a 2-letter US state abbreviation from a location string (e.g. 'Tyler, TX' or 'Shreveport, Louisiana')."""
    if not text:
        return None
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 2:
        tail = parts[-1]
        tail_upper = tail.upper()
        if tail_upper in STATE_TO_FIPS:
            return tail_upper
        tail_lower = tail.lower()
        if tail_lower in US_STATE_ABBR:
            return US_STATE_ABBR[tail_lower]

    for full_name, code in US_STATE_ABBR.items():
        if re.search(rf"\b{re.escape(full_name)}\b", text, re.IGNORECASE):
            return code
    for code in STATE_TO_FIPS:
        if re.search(rf",\s*{code}\b", text, re.IGNORECASE):
            return code
    return None


def identify_states_for_point_and_radius(
    lat: float,
    lon: float,
    radius_miles: float = 50.0,
    hint_state: str | None = None,
) -> list[str]:
    """Identify US state 2-letter codes intersecting a geographic circle around (lat, lon)."""
    states: list[str] = []
    if hint_state and hint_state.upper() in STATE_TO_FIPS:
        states.append(hint_state.upper())

    delta_lat = radius_miles / 69.0
    cos_lat = max(0.1, math.cos(math.radians(lat)))
    delta_lon = radius_miles / (69.0 * cos_lat)

    q_min_lat, q_max_lat = lat - delta_lat, lat + delta_lat
    q_min_lon, q_max_lon = lon - delta_lon, lon + delta_lon

    for st_code, boxes in US_STATE_REGIONS.items():
        if st_code in states:
            continue
        for b_min_lat, b_max_lat, b_min_lon, b_max_lon in boxes:
            if not (q_max_lat < b_min_lat or q_min_lat > b_max_lat or q_max_lon < b_min_lon or q_min_lon > b_max_lon):
                states.append(st_code)
                break

    return states if states else ["TX"]


def identify_states_for_route(
    waypoints: list[str],
    geo_points: list | None = None,
    corridor_width_miles: float = 25.0,
) -> list[str]:
    """Identify US states traversed by a route plan (from waypoint strings and intermediate leg coordinates)."""
    states: list[str] = []
    for wp in waypoints:
        st = extract_state_from_text(wp)
        if st and st not in states:
            states.append(st)

    # Also check intermediate points along route legs to catch pass-through states
    if geo_points and len(geo_points) >= 2:
        for i in range(len(geo_points) - 1):
            p1, p2 = geo_points[i], geo_points[i + 1]
            steps = 8
            for step in range(steps + 1):
                frac = step / steps
                s_lat = p1.lat + frac * (p2.lat - p1.lat)
                s_lon = p1.lon + frac * (p2.lon - p1.lon)
                for st_code, boxes in US_STATE_REGIONS.items():
                    if st_code in states:
                        continue
                    for b_min_lat, b_max_lat, b_min_lon, b_max_lon in boxes:
                        if b_min_lat <= s_lat <= b_max_lat and b_min_lon <= s_lon <= b_max_lon:
                            states.append(st_code)
                            break

    return states if states else ["TX"]


def identify_states_for_proximity(
    center_location: str,
    center_point=None,
    radius_miles: float = 50.0,
) -> list[str]:
    """Identify US states covered by a radial proximity search."""
    hint = extract_state_from_text(center_location)
    if center_point is not None:
        return identify_states_for_point_and_radius(
            center_point.lat,
            center_point.lon,
            radius_miles=radius_miles,
            hint_state=hint,
        )
    return [hint] if hint else ["TX"]


class RepeaterBookProvider:
    """Queries RepeaterBook REST API with automatic offline sample and disk cache fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 10.0,
        cache_dir: Path | None = None,
    ):
        self.api_key, self.token_source = self._discover_api_key(api_key)
        self.timeout = timeout
        self.cache_dir = cache_dir or (get_data_dir() / "repeaterbook")
        self.last_status: str = "CONFIGURED" if self.api_key else "NO_KEY"
        self._cached_channels: list[RadioChannel] | None = None

    @staticmethod
    def _discover_api_key(provided_key: str | None = None) -> tuple[str | None, str | None]:
        """Discovers RepeaterBook API key from parameter, env var, or tokens file."""
        if provided_key is not None:
            if provided_key.strip():
                return provided_key.strip(), "preferences_or_parameter"
            return None, None

        env_key = os.environ.get("REPEATERBOOK_API_KEY")
        if env_key and env_key.strip():
            return env_key.strip(), "environment_variable"

        # Check project root, docs, and user config directory
        possible_paths = [
            Path("docs/RepeaterBookPythonClientApiToken.txt"),
            Path(__file__).resolve().parent.parent.parent.parent / "docs" / "RepeaterBookPythonClientApiToken.txt",
            Path.home() / ".config" / "radioplanner" / "tokens" / "repeaterbook.txt",
            Path.home() / ".config" / "radioplanner" / "tokens" / "repeaterbook",
        ]
        for p in possible_paths:
            try:
                if p.is_file():
                    content = p.read_text(encoding="utf-8").strip()
                    if content:
                        if "repeaterBookApiKey:" in content:
                            import yaml
                            parsed = yaml.safe_load(content)
                            if isinstance(parsed, dict) and parsed.get("repeaterBookApiKey"):
                                return str(parsed["repeaterBookApiKey"]).strip(), str(p)
                        return content, str(p)
            except Exception:
                pass

        return None, None

    def has_api_key(self) -> bool:
        """Returns True if a valid RepeaterBook API key is configured."""
        return bool(self.api_key and self.api_key.strip())

    def get_state_file_info(self, state_code: str, max_age_days: int = 30) -> dict:
        """Check whether a downloaded state file (rb_STATE_DATE.json) exists on disk and whether it is fresh or stale."""
        st_upper = state_code.strip().upper()
        if not self.cache_dir.is_dir():
            return {"state": st_upper, "status": "MISSING", "path": None, "date": None, "age_days": None}

        matched = sorted(self.cache_dir.glob(f"rb_{st_upper}_*.json"), reverse=True)
        if not matched:
            return {"state": st_upper, "status": "MISSING", "path": None, "date": None, "age_days": None}

        newest = matched[0]
        parts = newest.stem.split("_", 2)
        date_str = parts[2] if len(parts) >= 3 else ""
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            age_days = max(0, (datetime.now().date() - file_date).days)
            status = "FRESH" if age_days <= max_age_days else "STALE"
            return {
                "state": st_upper,
                "status": status,
                "path": newest,
                "date": date_str,
                "age_days": age_days,
            }
        except ValueError:
            return {
                "state": st_upper,
                "status": "STALE",
                "path": newest,
                "date": date_str,
                "age_days": None,
            }

    def get_repeaters_for_states(
        self,
        states: list[str],
        max_age_days: int = 30,
        allowed_use: list[str] | set[str] | None = None,
    ) -> list[RadioChannel]:
        """Load repeaters for only the specified states, downloading or refreshing only missing or old state files."""
        allowed_set = {u.strip().upper() for u in (allowed_use or ["OPEN"]) if u.strip()} or {"OPEN"}
        unique_states: list[str] = []
        for s in states:
            s_up = s.strip().upper()
            if s_up and s_up not in unique_states:
                unique_states.append(s_up)

        if not unique_states:
            unique_states = ["TX"]

        all_channels: list[RadioChannel] = []
        used_live = False
        used_disk = False
        fallback_error: str | None = None
        idx = 1

        for st in unique_states:
            info = self.get_state_file_info(st, max_age_days=max_age_days)

            # 1. If fresh state file exists on disk, load directly without downloading
            if info["status"] == "FRESH" and info["path"] is not None:
                st_chans = self._load_single_state_file(info["path"], start_idx=idx, allowed_use=allowed_set)
                all_channels.extend(st_chans)
                idx += len(st_chans)
                used_disk = True
                continue

            # 2. File is MISSING or STALE -> download if API key is configured
            if self.has_api_key():
                try:
                    st_chans = self.download_state(st, allowed_use=allowed_set)
                    for ch in st_chans:
                        all_channels.append(ch.model_copy(update={"number": idx}))
                        idx += 1
                    used_live = True
                    continue
                except Exception as e:
                    fallback_error = str(e)

            # 3. Fallback to stale file on disk if available
            if info["path"] is not None:
                st_chans = self._load_single_state_file(info["path"], start_idx=idx, allowed_use=allowed_set)
                all_channels.extend(st_chans)
                idx += len(st_chans)
                used_disk = True

        if fallback_error:
            self.last_status = f"LIVE_API_FALLBACK ({fallback_error})"
        elif used_live:
            self.last_status = "LIVE_API_SUCCESS"
        elif used_disk:
            self.last_status = "DISK_CACHE"

        if all_channels:
            self._cached_channels = all_channels
            return all_channels

        # 4. Final fallback if no files on disk and no live response
        return self._get_offline_repeaters()

    def get_repeaters_near(
        self,
        lat: float,
        lon: float,
        radius_miles: float = 50.0,
        states: list[str] | None = None,
        max_age_days: int = 30,
        allowed_use: list[str] | set[str] | None = None,
    ) -> list[RadioChannel]:
        """Fetch repeaters for the states within radius of coordinates (downloading only missing/old state files)."""
        target_states = states or identify_states_for_point_and_radius(lat, lon, radius_miles=radius_miles)
        return self.get_repeaters_for_states(
            states=target_states,
            max_age_days=max_age_days,
            allowed_use=allowed_use,
        )

    def _query_live_api(
        self,
        lat: float,
        lon: float,
        radius_miles: float,
        allowed_use: set[str] | None = None,
    ) -> list[RadioChannel]:
        """Query RepeaterBook API for states within radius of (lat, lon)."""
        target_states = identify_states_for_point_and_radius(lat, lon, radius_miles=radius_miles)
        channels: list[RadioChannel] = []
        for st in target_states:
            channels.extend(self.download_state(st, allowed_use=allowed_use))
        return channels

    def download_state(
        self,
        state_code: str,
        date_str: str | None = None,
        allowed_use: list[str] | set[str] | None = None,
    ) -> list[RadioChannel]:
        """Download complete repeater dataset for a state via RepeaterBook API and save to disk."""
        allowed_set = {u.strip().upper() for u in (allowed_use or ["OPEN"]) if u.strip()} or {"OPEN"}
        st_upper = state_code.upper()
        fips = STATE_TO_FIPS.get(st_upper)
        if not fips:
            raise ValueError(f"Unknown state code '{state_code}'")

        if fips.startswith("CA"):
            url = f"https://www.repeaterbook.com/api/export.php?state_id={fips}&country=Canada"
        else:
            url = f"https://www.repeaterbook.com/api/export.php?state_id={fips}"
        headers = {
            "X-RB-App-Token": self.api_key or "",
            "User-Agent": "RepeaterBook Python Client/0.6.0 (+micael@jarniac.dev)",
            "Accept": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                self._save_to_disk_cache(data, date_str=date_str, default_state=st_upper)
                results = data if isinstance(data, list) else data.get("results", [])
                channels = []
                idx = 1
                for item in results:
                    item_st = resolve_state_code(item)
                    if item_st not in {"UNKNOWN", st_upper}:
                        continue
                    ch = self._parse_api_item(idx, item, allowed_use=allowed_set)
                    if ch:
                        channels.append(ch)
                        idx += 1
                return channels
            else:
                raise RuntimeError(f"HTTP {resp.status_code}")

    def _save_to_disk_cache(
        self,
        data: dict | list,
        date_str: str | None = None,
        default_state: str | None = None,
    ) -> None:
        """Persist downloaded RepeaterBook state data to ~/.config/radioplanner/data/repeaterbook/ as rb_STATE_DATE.json."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            results = data if isinstance(data, list) else data.get("results", [])
            current_date = date_str or datetime.now().strftime("%Y-%m-%d")

            # Group by state and save per-state files: rb_STATE_DATE.json
            by_state: dict[str, list[dict]] = {}
            for item in results:
                st_code = resolve_state_code(item)
                if st_code == "UNKNOWN" and default_state:
                    st_code = default_state.upper()
                by_state.setdefault(st_code, []).append(item)

            for st_code, items in by_state.items():
                # Remove older cached files for this state before writing the refreshed one
                for old_file in self.cache_dir.glob(f"rb_{st_code}_*.json"):
                    if old_file.name != f"rb_{st_code}_{current_date}.json":
                        try:
                            old_file.unlink()
                        except OSError:
                            pass

                st_file = self.cache_dir / f"rb_{st_code}_{current_date}.json"
                st_payload = {
                    "count": len(items),
                    "state": st_code,
                    "download_date": current_date,
                    "results": items,
                }
                st_file.write_text(json.dumps(st_payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not persist RepeaterBook data to disk: {e}")

    def _load_single_state_file(
        self,
        st_file: Path,
        start_idx: int = 1,
        allowed_use: set[str] | None = None,
    ) -> list[RadioChannel]:
        """Load and filter channels from a single downloaded state file."""
        try:
            data = json.loads(st_file.read_text(encoding="utf-8"))
            results = data if isinstance(data, list) else data.get("results", [])
            channels: list[RadioChannel] = []
            idx = start_idx
            for item in results:
                ch = self._parse_api_item(idx, item, allowed_use=allowed_use)
                if ch:
                    channels.append(ch)
                    idx += 1
            return channels
        except Exception as e:
            logger.warning(f"Could not read state file '{st_file}': {e}")
            return []

    def _load_from_disk_cache(
        self,
        states: list[str] | None = None,
        allowed_use: list[str] | set[str] | None = None,
    ) -> list[RadioChannel]:
        """Load repeaters from newest downloaded state files (rb_STATE_DATE.json) in data cache."""
        if not self.cache_dir.is_dir():
            return []

        allowed_set = {u.strip().upper() for u in (allowed_use or ["OPEN"]) if u.strip()} or {"OPEN"}
        target_set = {s.strip().upper() for s in states} if states else None

        try:
            rb_files = sorted(self.cache_dir.glob("rb_*_*.json"))
            if not rb_files:
                return []

            # Group by state code and select the newest date file for each state
            newest_by_state: dict[str, Path] = {}
            for f in rb_files:
                parts = f.stem.split("_", 2)
                if len(parts) >= 3:
                    st_code = parts[1].upper()
                    if st_code == "ALL":
                        continue
                    if target_set and st_code not in target_set:
                        continue
                    if st_code not in newest_by_state or f.name > newest_by_state[st_code].name:
                        newest_by_state[st_code] = f

            channels: list[RadioChannel] = []
            idx = 1
            for st_file in newest_by_state.values():
                st_chans = self._load_single_state_file(st_file, start_idx=idx, allowed_use=allowed_set)
                channels.extend(st_chans)
                idx += len(st_chans)
            return channels
        except Exception as e:
            logger.warning(f"Could not load RepeaterBook data from downloaded files: {e}")
            return []

    def list_cached_state_files(self) -> list[dict]:
        """Return structured summary of available cached state files with dates and counts."""
        if not self.cache_dir.is_dir():
            return []

        entries = []
        for f in sorted(self.cache_dir.glob("rb_*_*.json")):
            parts = f.stem.split("_", 2)
            if len(parts) >= 3:
                state_code = parts[1]
                if state_code == "ALL":
                    continue
                date_part = parts[2]
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    count = data.get("count", len(data.get("results", [])))
                except Exception:
                    count = 0
                entries.append({
                    "state": state_code,
                    "date": date_part,
                    "filename": f.name,
                    "path": f,
                    "count": count,
                })
        return entries

    def _parse_api_item(
        self,
        idx: int,
        item: dict,
        allowed_use: set[str] | None = None,
    ) -> RadioChannel | None:
        """Parse raw RepeaterBook API item into RadioChannel CIR, filtering for On-air and allowed Use types."""
        try:
            # 1. Operational Status: Only On-air repeaters
            op_status = str(item.get("Operational Status", "")).strip().lower()
            if op_status and op_status != "on-air":
                return None

            # 2. Use: Filter against allowed access types (default: OPEN only)
            allowed_set = allowed_use if allowed_use is not None else {"OPEN"}
            use_val = str(item.get("Use", "")).strip().upper()
            if use_val and use_val not in allowed_set:
                return None

            rx_freq = float(item.get("Frequency", item.get("rxFreq", 0.0)) or 0.0)
            if rx_freq <= 0.0:
                return None
            tx_freq = float(item.get("Input Freq", item.get("txFreq", rx_freq)) or rx_freq)
            if tx_freq <= 0.0:
                tx_freq = rx_freq
            offset = abs(tx_freq - rx_freq)
            offset_dir = "+" if tx_freq > rx_freq else ("-" if tx_freq < rx_freq else "off")
            name = item.get("Nearest City", item.get("name", f"RPT {rx_freq:.3f}"))
            callsign = item.get("Callsign", item.get("callsign"))
            raw_pl = str(item.get("PL", item.get("ctcss", "None")) or "None").strip()
            ctcss = "None"
            dcs = "None"
            tone_mode = "None"
            if raw_pl.upper().startswith("D") and raw_pl[1:4].isdigit():
                tone_mode = "DCS"
                dcs = raw_pl[1:4]
            else:
                try:
                    pl_float = float(raw_pl)
                    if 50.0 < pl_float < 300.0:
                        tone_mode = "Tone"
                        ctcss = f"{pl_float:.1f}"
                except (ValueError, TypeError):
                    pass

            mode = "DMR" if item.get("DMR") == "Yes" or "DMR" in str(item.get("Operational Mode", "")).upper() else "FM"
            cc_val = item.get("DMR Color Code")
            color_code = int(cc_val) if cc_val and str(cc_val).isdigit() else None

            return RadioChannel(
                number=idx,
                name=f"{name[:12]} {rx_freq:.2f}"[:16],
                callsign=callsign,
                rxFreq=rx_freq,
                txFreq=tx_freq,
                offset=round(offset, 4),
                offsetDir=offset_dir,
                mode=mode,
                toneMode=tone_mode,
                ctcss=ctcss,
                dcs=dcs,
                city=item.get("Nearest City", item.get("city")),
                state=item.get("State", item.get("state")),
                lat=float(item.get("Lat", item.get("lat", 0.0))),
                lon=float(item.get("Long", item.get("lon", 0.0))),
                specialType="REPEATERS",
                colorCode=color_code,
                comment=item.get("Use", item.get("comment", "")),
            )
        except Exception:
            return None

    def get_gmrs_repeaters_for_states(self, states: list[str] | None = None) -> list[RadioChannel]:
        """Return regional GMRS repeaters (462.550-462.725 MHz, +5.000 MHz offset) for the requested states."""
        target_states = {s.strip().upper() for s in states if s.strip()} if states else None
        channels: list[RadioChannel] = []
        idx = 1
        for item in GMRS_REPEATERS:
            st = str(item.get("state", "")).strip().upper()
            if target_states and st and st not in target_states:
                continue
            ch = RadioChannel(
                number=idx,
                name=item["name"],
                callsign=item.get("callsign"),
                rxFreq=item["rxFreq"],
                txFreq=item["txFreq"],
                offset=item.get("offset", 5.0),
                offsetDir=item.get("offsetDir", "+"),
                mode=item.get("mode", "FM"),
                toneMode=item.get("toneMode", "Tone"),
                ctcss=item.get("ctcss", "141.3"),
                city=item.get("city"),
                state=st or None,
                lat=item.get("lat"),
                lon=item.get("lon"),
                specialType="REPEATERS",
                comment=item.get("comment", ""),
            )
            channels.append(ch)
            idx += 1
        return channels

    def _get_offline_repeaters(self) -> list[RadioChannel]:
        """Convert comprehensive offline records (Ham + GMRS) into RadioChannel CIR instances."""
        channels = []
        for idx, item in enumerate(list(OFFLINE_REPEATERS) + list(GMRS_REPEATERS), start=1):
            ch = RadioChannel(
                number=idx,
                name=item["name"],
                callsign=item.get("callsign"),
                rxFreq=item["rxFreq"],
                txFreq=item["txFreq"],
                offset=item.get("offset", 0.0),
                offsetDir=item.get("offsetDir", "off"),
                mode=item.get("mode", "FM"),
                toneMode=item.get("toneMode", "None"),
                ctcss=item.get("ctcss", "None"),
                city=item.get("city"),
                state=item.get("state"),
                lat=item.get("lat"),
                lon=item.get("lon"),
                specialType="REPEATERS",
                colorCode=item.get("colorCode"),
                timeSlot=item.get("timeSlot"),
                comment=item.get("comment", ""),
            )
            channels.append(ch)
        return channels
