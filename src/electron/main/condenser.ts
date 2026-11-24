/**
 * Intelligent Name Condensation Algorithm for target radio LCD displays.
 * Exact TypeScript port of core/sanitizers/condenser.py.
 */

import { RadioChannel, TargetRadioSpec } from "../shared/types";

export const ABBREVIATIONS: Record<string, string> = {
  REPEATER: "RPT",
  REPEATERS: "RPTS",
  NORTH: "N",
  SOUTH: "S",
  EAST: "E",
  WEST: "W",
  NORTHEAST: "NE",
  NORTHWEST: "NW",
  SOUTHEAST: "SE",
  SOUTHWEST: "SW",
  CENTRAL: "CTR",
  EMERGENCY: "EMG",
  WEATHER: "WX",
  SIMPLEX: "SMP",
  CALLING: "CALL",
  COUNTY: "CNTY",
  POLICE: "PD",
  SHERIFF: "SO",
  FIRE: "FD",
  HOSPITAL: "HOSP",
  AIRPORT: "ARPT",
  REGIONAL: "RGNL",
  NATIONAL: "NAT",
  HIGHWAY: "HWY",
  INTERSTATE: "I",
  MOUNTAIN: "MTN",
  POINT: "PT",
  VALLEY: "VLY",
  DEPARTMENT: "DEPT",
  SECURITY: "SEC",
  TRANSIT: "TRN",
  ATIS: "AT",
  CTAF: "CT",
  TWR: "TW",
  GND: "GD",
  APP: "AP",
  DEP: "DP",
  UNICOM: "UN",
  AWOS: "AW",
  ASOS: "AS",
  CLNC: "CL",
};

function isTitleWord(w: string): boolean {
  if (!w) return false;
  const first = w[0];
  const rest = w.slice(1);
  return first === first.toUpperCase() && first !== first.toLowerCase() && rest === rest.toLowerCase();
}

function capitalize(w: string): string {
  if (!w) return w;
  return w[0].toUpperCase() + w.slice(1).toLowerCase();
}

function isAlnum(ch: string): boolean {
  return /^[a-zA-Z0-9]$/.test(ch);
}

export class NameCondenser {
  static formatCityFrequency(city: string, rxFreq: number, spec: TargetRadioSpec): string {
    const intPart = Math.trunc(rxFreq);
    const digitBefore = Math.abs(intPart) % 10;
    const decimalPart = Math.round((rxFreq - intPart) * 100) % 100;
    const decStr = String(Math.abs(decimalPart)).padStart(2, "0");
    const freqTag = spec.allowDots ? `${digitBefore}.${decStr}` : `${digitBefore}${decStr}`;

    let cleanCity = (city || "").split(",")[0].trim();
    for (const [fullWord, abbr] of Object.entries(ABBREVIATIONS)) {
      cleanCity = cleanCity.replace(new RegExp(`\\b${fullWord}\\b`, "gi"), abbr);
    }

    const useSpace = spec.allowSpaces && spec.maxNameLength - freqTag.length >= 4;
    const suffix = useSpace ? ` ${freqTag}` : freqTag;
    const maxCityLen = Math.max(1, spec.maxNameLength - suffix.length);
    let shortenedCity = cleanCity.slice(0, maxCityLen).trim();
    if (!shortenedCity) {
      shortenedCity = "RPT".slice(0, maxCityLen);
    }

    return this.applyHardwareCharRules(`${shortenedCity}${suffix}`, spec);
  }

  static formatAviationPrefixType(prefix: string, svcType: string, spec: TargetRadioSpec): string {
    const cleanPrefix = (prefix || "").split(",")[0].trim();
    const fullCandidate = `${cleanPrefix} ${svcType}`.trim();
    if (fullCandidate.length <= spec.maxNameLength && spec.allowSpaces) {
      return this.applyHardwareCharRules(fullCandidate, spec);
    }

    const shortSvc = ABBREVIATIONS[svcType.toUpperCase()] ?? svcType.slice(0, 2).toUpperCase();
    const useSpace = spec.allowSpaces && spec.maxNameLength - shortSvc.length >= 5;
    const suffix = useSpace ? ` ${shortSvc}` : shortSvc;
    const maxPrefLen = Math.max(1, spec.maxNameLength - suffix.length);
    const shortPref = cleanPrefix.slice(0, maxPrefLen).trim();
    return this.applyHardwareCharRules(`${shortPref}${suffix}`, spec);
  }

  static condenseChannel(ch: RadioChannel, spec: TargetRadioSpec, namingFormat = "CITY_FREQ"): string {
    const specialType = ch.specialType;
    const city = ch.city;
    if (specialType === "CALLING" || specialType === "WX" || (specialType === "GMRS" && !city)) {
      return this.condense(ch.name, spec);
    }

    const rxFreq = ch.rxFreq;
    const callsign = ch.callsign;

    if (specialType === "AVIATION") {
      const rawName = ch.name || "AIR";
      const parts = rawName.split(/\s+/).filter(Boolean);
      const svcType = parts.length > 1 ? parts[parts.length - 1] : "CTAF";
      const ident = callsign || (parts.length > 0 ? parts[0] : "AIR");
      if (namingFormat === "CITY_TYPE" && city) {
        return this.formatAviationPrefixType(city, svcType, spec);
      }
      if ((namingFormat === "IDENT_FREQ" || namingFormat === "ICAO_FREQ") && ident && rxFreq) {
        return this.formatCityFrequency(ident, rxFreq, spec);
      }
      if (namingFormat === "TYPE_FREQ" && rxFreq) {
        return this.formatCityFrequency(svcType, rxFreq, spec);
      }
      if (namingFormat === "IDENT_ONLY" && ident) {
        return this.condense(ident, spec, false);
      }
      return this.condense(`${ident} ${svcType}`.trim(), spec, false);
    }

    if (namingFormat === "CITY_FREQ" && city && rxFreq) {
      return this.formatCityFrequency(city, rxFreq, spec);
    }
    if (namingFormat === "CALLSIGN_FREQ" && callsign && rxFreq) {
      return this.formatCityFrequency(callsign, rxFreq, spec);
    }
    if (namingFormat === "CALLSIGN" && callsign) {
      return this.condense(callsign, spec);
    }
    if (namingFormat === "CITY" && city) {
      const cleanCity = city.split(",")[0].trim();
      return this.condense(cleanCity, spec, false);
    }
    if (namingFormat === "STANDARD") {
      let rawName = ch.name || "CH";
      if (city && rxFreq) {
        const cleanCity = city.split(",")[0].trim();
        const existingForms = new Set<string>([
          callsign ?? "",
          this.formatCityFrequency(city, rxFreq, spec),
          callsign ? this.formatCityFrequency(callsign, rxFreq, spec) : "",
          this.condense(cleanCity, spec, false),
        ]);
        if (existingForms.has(rawName)) {
          rawName = `${cleanCity} ${rxFreq.toFixed(2)}`;
        }
      }
      return this.condense(rawName, spec, false);
    }

    return this.condense(ch.name || "CH", spec);
  }

  static condense(name: string, spec: TargetRadioSpec, allowFreqShorthand = true): string {
    if (!name) return "CH";

    let result = name.trim();
    if (result.length <= spec.maxNameLength) {
      return this.applyHardwareCharRules(result, spec);
    }

    if (allowFreqShorthand) {
      const freqMatch = result.match(/^(.*?)\s+(\d{2,4}\.\d{2,5})$/);
      if (freqMatch) {
        const cityPart = freqMatch[1].trim();
        const cityUpper = cityPart.toUpperCase();
        if (cityPart && !cityUpper.startsWith("WX") && !cityUpper.startsWith("NOAA") && !cityUpper.startsWith("AIR")) {
          const rxVal = Number(freqMatch[2]);
          if (Number.isFinite(rxVal)) {
            return this.formatCityFrequency(cityPart, rxVal, spec);
          }
        }
      }
    }

    const words = result.split(/(\s+|-|_|\/)/);
    const condensedWords = words.map((word) => {
      const upper = word.toUpperCase();
      if (upper in ABBREVIATIONS) {
        const abbrev = ABBREVIATIONS[upper];
        if (word === word.toUpperCase() && word !== word.toLowerCase()) {
          return abbrev;
        }
        if (isTitleWord(word)) {
          return capitalize(abbrev);
        }
        return abbrev.toLowerCase();
      }
      return word;
    });

    result = condensedWords.join("");

    if (result.length > spec.maxNameLength && (!spec.allowSpaces || result.includes(" "))) {
      const noSpaces = result.split(/\s+/).filter(Boolean).join("");
      if (noSpaces.length <= spec.maxNameLength || !spec.allowSpaces) {
        result = noSpaces;
      }
    }

    if (result.length > spec.maxNameLength) {
      result = result.slice(0, spec.maxNameLength);
    }

    return this.applyHardwareCharRules(result, spec);
  }

  static applyHardwareCharRules(text: string, spec: TargetRadioSpec): string {
    const cleaned: string[] = [];
    const allowedSpecial = spec.allowedSpecialChars ?? " -_./#";
    for (const ch of text) {
      if (ch === ".") {
        if (spec.allowDots) cleaned.push(".");
        continue;
      }
      if (ch === " ") {
        if (spec.allowSpaces) cleaned.push(" ");
        continue;
      }
      if (isAlnum(ch) || allowedSpecial.includes(ch)) {
        cleaned.push(ch);
      } else if (allowedSpecial.includes("-")) {
        cleaned.push("-");
      } else if (allowedSpecial.includes("_")) {
        cleaned.push("_");
      } else if (spec.allowSpaces) {
        cleaned.push(" ");
      }
    }

    let res = cleaned.join("").trim();
    if (!res) res = "CH";
    return res.slice(0, spec.maxNameLength);
  }
}
