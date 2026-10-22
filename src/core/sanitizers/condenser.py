"""Intelligent Name Condensation Algorithm for target radio LCD displays."""

from __future__ import annotations

import re

from core.models.radio_spec import TargetRadioSpec

# Standard Radio Name Abbreviations Dictionary
ABBREVIATIONS = {
    "REPEATER": "RPT",
    "REPEATERS": "RPTS",
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
    "CENTRAL": "CTR",
    "EMERGENCY": "EMG",
    "WEATHER": "WX",
    "SIMPLEX": "SMP",
    "CALLING": "CALL",
    "COUNTY": "CNTY",
    "POLICE": "PD",
    "SHERIFF": "SO",
    "FIRE": "FD",
    "HOSPITAL": "HOSP",
    "AIRPORT": "ARPT",
    "REGIONAL": "RGNL",
    "NATIONAL": "NAT",
    "HIGHWAY": "HWY",
    "INTERSTATE": "I",
    "MOUNTAIN": "MTN",
    "POINT": "PT",
    "VALLEY": "VLY",
    "DEPARTMENT": "DEPT",
    "SECURITY": "SEC",
    "TRANSIT": "TRN",
    "ATIS": "AT",
    "CTAF": "CT",
    "TWR": "TW",
    "GND": "GD",
    "APP": "AP",
    "DEP": "DP",
    "UNICOM": "UN",
    "AWOS": "AW",
    "ASOS": "AS",
    "CLNC": "CL",
}


class NameCondenser:
    """Condenses long channel names using word-boundary abbreviations to fit radio LCD limits."""

    @classmethod
    def format_city_frequency(
        cls,
        city: str,
        rx_freq: float,
        spec: TargetRadioSpec,
    ) -> str:
        """Format repeater name as 'City x.xx' (1 digit before decimal, 2 after), shortening city to fit."""
        int_part = int(rx_freq)
        digit_before = int_part % 10
        decimal_part = int(round((rx_freq - int_part) * 100)) % 100
        freq_tag = f"{digit_before}.{decimal_part:02d}" if spec.allowDots else f"{digit_before}{decimal_part:02d}"

        # Clean city name (remove any trailing state abbreviations, punctuation, or spaces)
        clean_city = city.split(",")[0].strip()

        # Apply abbreviations if any (e.g. Fort -> Ft, Mount -> Mt, North -> N)
        for full_word, abbr in ABBREVIATIONS.items():
            clean_city = re.sub(rf"\b{full_word}\b", abbr, clean_city, flags=re.IGNORECASE)

        use_space = spec.allowSpaces and (spec.maxNameLength - len(freq_tag) >= 4)
        suffix = f" {freq_tag}" if use_space else freq_tag
        suffix_len = len(suffix)

        max_city_len = max(1, spec.maxNameLength - suffix_len)
        shortened_city = clean_city[:max_city_len].strip()
        if not shortened_city:
            shortened_city = "RPT"[:max_city_len]

        candidate = f"{shortened_city}{suffix}"
        return cls._apply_hardware_char_rules(candidate, spec)

    @classmethod
    def condense_channel(
        cls,
        ch: any,
        spec: TargetRadioSpec,
        naming_format: str = "CITY_FREQ",
    ) -> str:
        """Condense RadioChannel name respecting radio hardware limits and user naming format."""
        if getattr(ch, "specialType", None) in {"CALLING", "WX", "AVIATION"}:
            return cls.condense(ch.name, spec)

        city = getattr(ch, "city", None)
        rx_freq = getattr(ch, "rxFreq", None)
        callsign = getattr(ch, "callsign", None)

        if naming_format == "CITY_FREQ" and city and rx_freq:
            return cls.format_city_frequency(city, rx_freq, spec)
        elif naming_format == "CALLSIGN_FREQ" and callsign and rx_freq:
            return cls.format_city_frequency(callsign, rx_freq, spec)
        elif naming_format == "CALLSIGN" and callsign:
            return cls.condense(callsign, spec)

        # Fallback to general condenser
        return cls.condense(getattr(ch, "name", "CH"), spec)

    @classmethod
    def condense(cls, name: str, spec: TargetRadioSpec) -> str:
        """Condense channel name to fit spec.maxNameLength, character restrictions, and whitespace rules."""
        if not name:
            return "CH"

        result = name.strip()

        # If already fits and conforms, check allowed chars
        if len(result) <= spec.maxNameLength:
            return cls._apply_hardware_char_rules(result, spec)

        # Check if name is in "City Frequency" pattern (e.g. "Tyler 147.20" or "Tyler 147.2000")
        freq_match = re.search(r"^(.*?)\s+(\d{2,4}\.\d{2,5})$", result)
        if freq_match:
            city_part = freq_match.group(1).strip()
            if city_part and not any(city_part.upper().startswith(t) for t in ("WX", "NOAA", "AIR")):
                try:
                    rx_val = float(freq_match.group(2))
                    return cls.format_city_frequency(city_part, rx_val, spec)
                except ValueError:
                    pass

        # 1. Apply word abbreviations
        words = re.split(r"(\s+|-|_|/)", result)
        condensed_words = []
        for word in words:
            upper_word = word.upper()
            if upper_word in ABBREVIATIONS:
                # Preserve case pattern if originally capitalized
                abbrev = ABBREVIATIONS[upper_word]
                if word.isupper():
                    condensed_words.append(abbrev)
                elif word.istitle():
                    condensed_words.append(abbrev.capitalize())
                else:
                    condensed_words.append(abbrev.lower())
            else:
                condensed_words.append(word)

        result = "".join(condensed_words)

        # 2. If still exceeds limit, remove spaces if not allowed or if needed to fit
        if len(result) > spec.maxNameLength and (not spec.allowSpaces or " " in result):
            # Try removing spaces between words
            result_no_spaces = "".join(part for part in re.split(r"\s+", result) if part)
            if len(result_no_spaces) <= spec.maxNameLength or not spec.allowSpaces:
                result = result_no_spaces

        # 3. If still exceeds limit, truncate cleanly
        if len(result) > spec.maxNameLength:
            result = result[: spec.maxNameLength]

        return cls._apply_hardware_char_rules(result, spec)

    @classmethod
    def _apply_hardware_char_rules(
        cls, text: str, spec: TargetRadioSpec
    ) -> str:
        """Filter characters according to allowDots, allowSpaces, and allowedSpecialChars."""
        cleaned = []
        for char in text:
            if char == ".":
                if spec.allowDots:
                    cleaned.append(".")
                continue
            if char == " ":
                if spec.allowSpaces:
                    cleaned.append(" ")
                continue
            if char.isalnum() or char in spec.allowedSpecialChars:
                cleaned.append(char)
            else:
                # Replace unsupported special char with dash, underscore, or space if allowed
                if "-" in spec.allowedSpecialChars:
                    cleaned.append("-")
                elif "_" in spec.allowedSpecialChars:
                    cleaned.append("_")
                elif spec.allowSpaces:
                    cleaned.append(" ")

        res = "".join(cleaned).strip()
        if not res:
            res = "CH"
        return res[: spec.maxNameLength]
