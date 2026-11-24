/**
 * Codeplug CSV Exporters: CHIRP (21-column standard), RT Systems, and Generic CSV.
 */

import { csvSafeCell } from "../shared/sanitize";
import { RadioChannel, TargetRadioSpec } from "../shared/types";
import { NameCondenser } from "./condenser";

export const CHIRP_COLUMNS = [
  "Location",
  "Name",
  "Frequency",
  "Duplex",
  "Offset",
  "Tone",
  "rToneFreq",
  "cToneFreq",
  "DtcsCode",
  "DtcsPolarity",
  "RxDtcsCode",
  "CrossMode",
  "Mode",
  "TStep",
  "Skip",
  "Power",
  "Comment",
  "URCALL",
  "RPT1CALL",
  "RPT2CALL",
  "DVCODE",
] as const;

export const DEFAULT_RT_SYSTEMS_COLUMNS = [
  "Receive Frequency",
  "Transmit Frequency",
  "Offset Frequency",
  "Offset direction",
  "Operating Mode",
  "Name",
  "Tone Mode",
  "CTCSS",
  "Rx CTCSS",
  "DCS",
  "Rx DCS",
  "DCS Polarity",
  "Tx Power",
  "Comment",
] as const;

export const DEFAULT_GENERIC_COLUMNS = [
  "Channel Number",
  "Name",
  "Receive Frequency",
  "Transmit Frequency",
  "Offset",
  "Offset Direction",
  "Mode",
  "Power",
  "Tone Mode",
  "CTCSS",
  "Rx CTCSS",
  "DCS",
  "Rx DCS",
  "DCS Polarity",
  "Bandwidth",
  "City",
  "State",
  "Latitude",
  "Longitude",
  "Comment",
] as const;

function csvEscapeField(val: string | number | null | undefined): string {
  const s = val === null || val === undefined ? "" : String(val);
  if (s.includes(",") || s.includes('"') || s.includes("\n") || s.includes("\r")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function toCsvLine(fields: Array<string | number | null | undefined>): string {
  return fields.map(csvEscapeField).join(",");
}

export function prepareChannelsForExport(channels: RadioChannel[], spec: TargetRadioSpec): RadioChannel[] {
  const startChannel = Math.max(0, spec.startChannel ?? 1);
  const maxChannels = Math.max(1, spec.maxChannels || 999);
  const limited = channels.slice(0, maxChannels);
  return limited.map((ch, idx) => ({
    ...ch,
    number: startChannel + idx,
    name: NameCondenser.condense(ch.name, spec, false),
  }));
}

export function exportChirpCsv(channels: RadioChannel[], spec: TargetRadioSpec): string {
  const prepared = prepareChannelsForExport(channels, spec);
  const lines: string[] = [toCsvLine([...CHIRP_COLUMNS])];

  for (const ch of prepared) {
    let duplex = ch.offsetDir === "+" || ch.offsetDir === "-" ? ch.offsetDir : "";
    if (Math.abs(ch.offset) < 1e-5) duplex = "";

    let tone = "";
    let rTone = "88.5";
    let cTone = "88.5";
    let dtcsCode = "023";
    let rxDtcsCode = "023";

    const rawCtcss = (ch.ctcss || "").trim();
    let validCtcss: string | null = null;
    if (rawCtcss && rawCtcss !== "None") {
      const fVal = Number(rawCtcss);
      if (Number.isFinite(fVal) && fVal > 50.0 && fVal < 300.0) {
        validCtcss = fVal.toFixed(1);
      }
    }

    const toneModeUpper = (ch.toneMode || "None").toUpperCase();
    if (rawCtcss.toUpperCase().startsWith("D") && /^\d{3}/.test(rawCtcss.slice(1, 4))) {
      tone = "DTCS";
      dtcsCode = String(parseInt(rawCtcss.slice(1, 4), 10)).padStart(3, "0");
      rxDtcsCode = dtcsCode;
    } else if (toneModeUpper === "TONE") {
      if (validCtcss) {
        tone = "Tone";
        rTone = validCtcss;
      }
    } else if (toneModeUpper === "TSQL" || toneModeUpper === "CTCSS") {
      if (validCtcss) {
        tone = "TSQL";
        cTone = validCtcss;
        rTone = validCtcss;
      }
    } else if (toneModeUpper === "DCS" || toneModeUpper === "DTCS") {
      tone = "DTCS";
      dtcsCode =
        ch.dcs && ch.dcs !== "None" && /^\d+$/.test(ch.dcs)
          ? String(parseInt(ch.dcs, 10)).padStart(3, "0")
          : "023";
      rxDtcsCode =
        ch.rxDcs && ch.rxDcs !== "None" && /^\d+$/.test(ch.rxDcs)
          ? String(parseInt(ch.rxDcs, 10)).padStart(3, "0")
          : dtcsCode;
    }

    const pwrRaw = (ch.power || "High").trim().toLowerCase();
    let power = "50W";
    if (pwrRaw === "low") power = "5.0W";
    else if (pwrRaw === "mid" || pwrRaw === "medium" || pwrRaw === "med") power = "25W";
    else if (pwrRaw === "high") power = "50W";
    else if (pwrRaw.endsWith("w") || /^\d+(\.\d+)?$/.test(pwrRaw)) power = ch.power.trim();

    const mode = (ch.mode || "FM").toUpperCase() === "AM" ? "AM" : "FM";

    lines.push(
      toCsvLine([
        ch.number,
        ch.name,
        ch.rxFreq.toFixed(6),
        duplex,
        ch.offset.toFixed(6),
        tone,
        rTone,
        cTone,
        dtcsCode,
        ch.dcsPolarity || "NN",
        rxDtcsCode,
        "Tone->Tone",
        mode,
        "5.00",
        "",
        power,
        csvSafeCell(ch.comment || ""),
        "",
        "",
        "",
        "",
      ]),
    );
  }

  return `${lines.join("\n")}\n`;
}

export function exportRtSystemsCsv(channels: RadioChannel[], spec: TargetRadioSpec): string {
  const prepared = prepareChannelsForExport(channels, spec);
  const columns = spec.columns && spec.columns.length > 0 ? spec.columns : [...DEFAULT_RT_SYSTEMS_COLUMNS];
  const lines: string[] = [toCsvLine(columns)];

  for (const ch of prepared) {
    let offsetDir = ch.offsetDir === "+" || ch.offsetDir === "-" || ch.offsetDir === "off" ? ch.offsetDir : "off";
    if (Math.abs(ch.offset) < 1e-5) offsetDir = "off";

    let toneMode = ch.toneMode || "None";
    if (toneMode.toUpperCase() === "NONE" || toneMode.toUpperCase() === "OFF") {
      toneMode = "None";
    }

    const txPower = ch.power ? ch.power[0].toUpperCase() + ch.power.slice(1).toLowerCase() : "High";
    const chType = (ch.mode || "").toUpperCase() === "DMR" || ch.colorCode !== null ? "Digital" : "Analog";

    const rowMap: Record<string, string | number> = {
      "Channel Number": ch.number,
      "Receive Frequency": ch.rxFreq.toFixed(5),
      "Transmit Frequency": ch.txFreq.toFixed(5),
      "Offset Frequency": ch.offset.toFixed(5),
      "Offset direction": offsetDir,
      "Operating Mode": ch.mode,
      "Show Name": "Yes",
      Name: ch.name,
      "Channel Name": ch.name,
      "Channel Type": chType,
      "Tone Mode": toneMode,
      CTCSS: ch.ctcss && ch.ctcss !== "None" ? ch.ctcss : "88.5",
      "Rx CTCSS": ch.rxCtcss && ch.rxCtcss !== "None" ? ch.rxCtcss : "88.5",
      "CTCSS / DCS Decode": ch.rxCtcss && ch.rxCtcss !== "None" ? ch.rxCtcss : "None",
      "CTCSS / DCS Encode": ch.ctcss && ch.ctcss !== "None" ? ch.ctcss : "None",
      DCS: ch.dcs && ch.dcs !== "None" ? ch.dcs : "023",
      "Rx DCS": ch.rxDcs && ch.rxDcs !== "None" ? ch.rxDcs : "023",
      "DCS Polarity": ch.dcsPolarity || "NN",
      "Tx Power": txPower,
      "Transmit Power": txPower,
      Bandwidth: ch.bandwidth || "25KHz",
      "Scan Add": "On",
      Compander: "Off",
      Scrambler: "Off",
      "Busy Lock": "Off",
      FHSS: "Off",
      "Signal Code": "1",
      PTTID: "Off",
      Contact: ch.contact || "Local 9",
      "Contact Call Type": "Group Call",
      "Contact TG/DMR ID": ch.dmrId || "3100",
      "Radio ID": "1",
      "Color Code": ch.colorCode !== null ? ch.colorCode : 1,
      Slot: ch.timeSlot ? `Slot ${ch.timeSlot}` : "Slot 1",
      "Rx Group List": "None",
      "Tx Permit": "Always",
      "Scan List": "None",
      Squelch: "Normal",
      TOT: "180",
      "Standby Color": "Blue",
      "Rx Color": "Orange",
      "Tx Color": "Red",
      Comment: csvSafeCell(ch.comment || ""),
    };

    lines.push(toCsvLine(columns.map((col) => rowMap[col] ?? "")));
  }

  return `${lines.join("\n")}\n`;
}

export function exportGenericCsv(channels: RadioChannel[], spec: TargetRadioSpec): string {
  const prepared = prepareChannelsForExport(channels, spec);
  const columns = spec.columns && spec.columns.length > 0 ? spec.columns : [...DEFAULT_GENERIC_COLUMNS];
  const lines: string[] = [toCsvLine(columns)];

  for (const ch of prepared) {
    const rowMap: Record<string, string | number> = {
      "Channel Number": ch.number,
      Name: csvSafeCell(ch.name),
      "Receive Frequency": ch.rxFreq.toFixed(5),
      "Transmit Frequency": ch.txFreq.toFixed(5),
      Offset: ch.offset.toFixed(5),
      "Offset Direction": ch.offsetDir,
      Mode: ch.mode,
      Power: ch.power,
      "Tone Mode": ch.toneMode,
      CTCSS: ch.ctcss,
      "Rx CTCSS": ch.rxCtcss,
      DCS: ch.dcs,
      "Rx DCS": ch.rxDcs,
      "DCS Polarity": ch.dcsPolarity,
      Bandwidth: ch.bandwidth,
      City: csvSafeCell(ch.city || ""),
      State: csvSafeCell(ch.state || ""),
      Latitude: ch.lat !== null ? ch.lat.toFixed(5) : "",
      Longitude: ch.lon !== null ? ch.lon.toFixed(5) : "",
      Comment: csvSafeCell(ch.comment || ""),
    };
    lines.push(toCsvLine(columns.map((col) => rowMap[col] ?? "")));
  }

  return `${lines.join("\n")}\n`;
}

export function exportCodeplugCsv(channels: RadioChannel[], spec: TargetRadioSpec, formatType = "RT_SYSTEMS"): string {
  const fmt = (formatType || spec.programmerType || "RT_SYSTEMS").trim().toUpperCase();
  if (fmt === "CHIRP") {
    return exportChirpCsv(channels, spec);
  }
  if (fmt === "GENERIC" || fmt === "GENERIC_CSV") {
    return exportGenericCsv(channels, spec);
  }
  return exportRtSystemsCsv(channels, spec);
}
