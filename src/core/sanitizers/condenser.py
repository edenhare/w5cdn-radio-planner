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
}


class NameCondenser:
    """Condenses long channel names using word-boundary abbreviations to fit radio LCD limits."""

    @classmethod
    def condense(cls, name: str, spec: TargetRadioSpec) -> str:
        """Condense channel name to fit spec.maxNameLength, character restrictions, and whitespace rules."""
        if not name:
            return "CH"

        result = name.strip()

        # If already fits and conforms, check allowed chars
        if len(result) <= spec.maxNameLength:
            return cls._apply_hardware_char_rules(result, spec)

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
            result_no_spaces = "".join(
                part for part in re.split(r"\s+", result) if part
            )
            if len(result_no_spaces) <= spec.maxNameLength or not spec.allowSpaces:
                result = result_no_spaces

        # 3. If still exceeds limit, truncate cleanly
        if len(result) > spec.maxNameLength:
            result = result[: spec.maxNameLength]

        return cls._apply_hardware_char_rules(result, spec)

    @classmethod
    def _apply_hardware_char_rules(cls, text: str, spec: TargetRadioSpec) -> str:
        """Filter characters according to allowDots, allowSpaces, and allowedSpecialChars."""
        cleaned = []
        for char in text:
            if char == "." and not spec.allowDots:
                continue
            if char == " " and not spec.allowSpaces:
                continue
            if char.isalnum() or char in spec.allowedSpecialChars:
                cleaned.append(char)
            else:
                # Replace unsupported special char with underscore or dash if allowed
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
