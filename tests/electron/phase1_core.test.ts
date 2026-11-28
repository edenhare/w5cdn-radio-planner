import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { NameCondenser } from "../../src/electron/main/condenser";
import { AviationEngine } from "../../src/electron/main/engines/aviation";
import { ProximityEngine } from "../../src/electron/main/engines/proximity";
import { RouteCorridorEngine } from "../../src/electron/main/engines/routeCorridor";
import {
  SequenceOrganizer,
  getNationalCallingChannels,
  getNoaaWxChannels,
} from "../../src/electron/main/engines/sequence";
import {
  exportChirpCsv,
  exportCodeplugCsv,
  exportGenericCsv,
  exportRtSystemsCsv,
} from "../../src/electron/main/exporters";
import {
  getConfigDir,
  getSharedSuiteDir,
  getW5cdnSuiteRoot,
  readSharedSuiteConfig,
} from "../../src/electron/main/paths";
import {
  GeocodingProvider,
  haversineMiles,
  pointToRouteMetrics,
  pointToSegmentDistanceMiles,
} from "../../src/electron/main/providers/geocoding";
import { RadioIdProvider } from "../../src/electron/main/providers/radioId";
import {
  RepeaterBookProvider,
  extractStateFromText,
  identifyStatesForProximity,
  identifyStatesForRoute,
  resolveStateCode,
} from "../../src/electron/main/providers/repeaterbook";
import {
  channelBand,
  channelIsSimplex,
  cleanSingleLine,
  csvSafeCell,
  safeChildPath,
  sanitizeChannelsForRadio,
  sanitizeFilename,
  sanitizeHttpUrl,
} from "../../src/electron/shared/sanitize";
import {
  TargetRadioSpec,
  createRadioChannel,
  resolveCockpitTheme,
  resolveUiFont,
  sanitizePanelLayout,
} from "../../src/electron/shared/types";
import {
  YamlDiagnosticError,
  dumpYamlText,
  normalizeUserPreferences,
  parseYamlText,
  validateRadioSpec,
  validateRecipe,
  validateTemplateFile,
} from "../../src/electron/shared/yamlDiagnostics";

const SAMPLE_SPEC: TargetRadioSpec = {
  id: "baofeng_5rm",
  brand: "Baofeng",
  model: "5RM",
  description: "Baofeng 5RM",
  startChannel: 1,
  maxChannels: 999,
  maxNameLength: 10,
  allowDots: true,
  allowSpaces: true,
  allowedSpecialChars: " -_./+#*",
  supportedBands: ["2m", "1.25m", "70cm", "GMRS", "Airband", "WX"],
  supportedModes: ["FM", "AM"],
  programmerType: "RT_SYSTEMS",
  columns: [],
};

describe("Phase 1: Core Sanitization, Paths & YAML Diagnostics", () => {
  const prevRpHome = process.env.RADIOPLANNER_HOME;
  const prevSuite = process.env.W5CDN_SUITE_DIR;

  afterEach(() => {
    if (prevRpHome === undefined) delete process.env.RADIOPLANNER_HOME;
    else process.env.RADIOPLANNER_HOME = prevRpHome;
    if (prevSuite === undefined) delete process.env.W5CDN_SUITE_DIR;
    else process.env.W5CDN_SUITE_DIR = prevSuite;
  });

  it("classifies radio frequency bands and simplex status accurately", () => {
    expect(channelBand(29.6)).toBe("10m");
    expect(channelBand(52.525)).toBe("6m");
    expect(channelBand(126.25)).toBe("Airband");
    expect(channelBand(146.52)).toBe("2m");
    expect(channelBand(162.55)).toBe("WX");
    expect(channelBand(223.5)).toBe("1.25m");
    expect(channelBand(446.0)).toBe("70cm");
    expect(channelBand(462.675)).toBe("GMRS");
    expect(channelBand(902.5)).toBe("Other");

    expect(channelIsSimplex({ rxFreq: 146.52, txFreq: 146.52, offsetDir: "off" })).toBe(true);
    expect(channelIsSimplex({ rxFreq: 147.2, txFreq: 147.8, offsetDir: "+" })).toBe(false);
  });

  it("sanitizes filenames, CSV formula cells, URLs, and rejects path traversal", () => {
    expect(cleanSingleLine("  Hello\r\nWorld\x00! ")).toBe("Hello World!");
    expect(sanitizeFilename("My:Trip/2026*.csv")).toBe("My_Trip_2026_.csv");
    expect(csvSafeCell("=CMD|'/C calc'!A0")).toBe("'=CMD|'/C calc'!A0");
    expect(csvSafeCell("Normal comment")).toBe("Normal comment");
    expect(sanitizeHttpUrl("https://github.com/edenhare/w5cdn-radio-planner")).toBe(
      "https://github.com/edenhare/w5cdn-radio-planner",
    );
    expect(sanitizeHttpUrl("javascript:alert(1)")).toBeNull();

    const base = path.join(os.tmpdir(), "rp_path_test");
    expect(safeChildPath(base, "my_plan.yaml")).toBe(path.resolve(base, "my_plan.yaml"));
    expect(() => safeChildPath(base, "../secret.yaml")).toThrow();
    expect(() => safeChildPath(base, "sub/file.yaml")).toThrow();
  });

  it("resolves unified W5CDN Suite directories and shared config.txt", () => {
    const tmpSuite = fs.mkdtempSync(path.join(os.tmpdir(), "rp_suite_"));
    try {
      delete process.env.RADIOPLANNER_HOME;
      process.env.W5CDN_SUITE_DIR = tmpSuite;
      expect(getW5cdnSuiteRoot()).toBe(path.resolve(tmpSuite));
      expect(getConfigDir()).toBe(path.join(path.resolve(tmpSuite), "RadioPlanner"));
      expect(getSharedSuiteDir()).toBe(path.join(path.resolve(tmpSuite), "shared"));

      fs.mkdirSync(getSharedSuiteDir(), { recursive: true });
      fs.writeFileSync(
        path.join(getSharedSuiteDir(), "config.txt"),
        "# Shared W5CDN config\nOPERATOR_CALL=W5CDN\nQRZ_USER=W5CDN\n",
        "utf-8",
      );
      const shared = readSharedSuiteConfig();
      expect(shared.OPERATOR_CALL).toBe("W5CDN");
      expect(shared.QRZ_USER).toBe("W5CDN");
    } finally {
      fs.rmSync(tmpSuite, { recursive: true, force: true });
    }
  });

  it("parses and validates YAML strictly with actionable line/column diagnostics", () => {
    const validRadioYaml = dumpYamlText(SAMPLE_SPEC, "Test radio header");
    const parsed = parseYamlText(validRadioYaml, "test.yaml");
    const validated = validateRadioSpec(parsed, "test.yaml");
    expect(validated.id).toBe("baofeng_5rm");
    expect(validated.maxNameLength).toBe(10);

    // Invalid YAML syntax (tabs / broken mapping)
    expect(() => parseYamlText("id: test\n\tbad: [unclosed", "broken.yaml")).toThrow(YamlDiagnosticError);

    // Schema validation errors on hand-edited radio YAML
    try {
      validateRadioSpec({ id: "bad slug!", brand: "", model: "X", maxChannels: 0, programmerType: "BOGUS" }, "bad.yaml");
      expect.unreachable("Should have thrown YamlDiagnosticError");
    } catch (err) {
      expect(err).toBeInstanceOf(YamlDiagnosticError);
      const diag = err as YamlDiagnosticError;
      expect(diag.issues.length).toBeGreaterThanOrEqual(4);
      expect(diag.formatReport()).toContain("Field 'id'");
    }

    // Schema validation errors on template & recipe YAML
    expect(() => validateTemplateFile({ id: "t1", name: "T1", channels: [{ name: "", rxFreq: -5 }] })).toThrow(
      YamlDiagnosticError,
    );
    expect(() => validateRecipe({ mode: "ROUTE_CORRIDOR", corridor: { waypoints: ["Only One"] } })).toThrow(
      YamlDiagnosticError,
    );

    // Preference & cockpit theme normalization
    const prefs = normalizeUserPreferences({
      callsign: " w5cdn ",
      colorTheme: "DARK",
      fontFamily: "SANS",
      uiFontSize: 99,
      repeaterAccess: "ALL",
    });
    expect(prefs.callsign).toBe("W5CDN");
    expect(resolveCockpitTheme(prefs.colorTheme)).toBe("shack-dark");
    expect(resolveUiFont(prefs.fontFamily)).toBe("system");
    expect(prefs.uiFontSize).toBe(22);
    expect(prefs.repeaterAccess).toEqual(["OPEN", "CLOSED", "PRIVATE"]);
    expect(sanitizePanelLayout({ builder: { visible: false, position: "top" } }).builder).toEqual({
      visible: false,
      position: "top",
    });
  });
});

describe("Phase 1: NameCondenser, Engines, Providers & Exporters", () => {
  it("condenses channel names accurately for LCD width and character constraints", () => {
    const ch = createRadioChannel({
      name: "Tyler 147.20",
      callsign: "W5ETX",
      rxFreq: 147.2,
      txFreq: 147.8,
      city: "Tyler",
      state: "TX",
    });
    expect(NameCondenser.condenseChannel(ch, SAMPLE_SPEC, "CITY_FREQ")).toBe("Tyler 7.20");
    expect(NameCondenser.condenseChannel(ch, SAMPLE_SPEC, "CALLSIGN_FREQ")).toBe("W5ETX 7.20");
    expect(NameCondenser.condenseChannel(ch, SAMPLE_SPEC, "CALLSIGN")).toBe("W5ETX");

    const tightSpec: TargetRadioSpec = {
      ...SAMPLE_SPEC,
      maxNameLength: 6,
      allowDots: false,
      allowSpaces: false,
    };
    const tightName = NameCondenser.condenseChannel(ch, tightSpec, "CITY_FREQ");
    expect(tightName.length).toBeLessThanOrEqual(6);
    expect(tightName).not.toContain(".");
    expect(tightName).not.toContain(" ");

    const airCh = createRadioChannel({
      name: "KTYR ATIS",
      callsign: "KTYR",
      rxFreq: 126.25,
      mode: "AM",
      city: "Tyler",
      specialType: "AVIATION",
    });
    expect(NameCondenser.condenseChannel(airCh, SAMPLE_SPEC, "IDENT_TYPE")).toBe("KTYR ATIS");
    expect(NameCondenser.condenseChannel(airCh, SAMPLE_SPEC, "CITY_TYPE")).toBe("Tyler ATIS");
  });

  it("geocodes offline cities, computes corridor/proximity distances, and identifies states", async () => {
    const geo = new GeocodingProvider(true);
    const tyler = await geo.geocode("Tyler, TX");
    const shreveport = await geo.geocode("Shreveport, LA");
    expect(tyler).not.toBeNull();
    expect(shreveport).not.toBeNull();

    const miles = haversineMiles(tyler![0], tyler![1], shreveport![0], shreveport![1]);
    expect(miles).toBeGreaterThan(80);
    expect(miles).toBeLessThan(120);

    const segDist = pointToSegmentDistanceMiles(tyler![0], tyler![1], tyler![0], tyler![1], shreveport![0], shreveport![1]);
    expect(segDist).toBeLessThan(0.01);

    const routeMetrics = pointToRouteMetrics(shreveport![0], shreveport![1], [tyler!, shreveport!]);
    expect(routeMetrics.crossTrackMiles).toBeLessThan(0.01);
    expect(routeMetrics.alongTrackMiles).toBeCloseTo(miles, 0);

    expect(resolveStateCode("Texas")).toBe("TX");
    expect(extractStateFromText("Shreveport, LA")).toBe("LA");
    const routeStates = identifyStatesForRoute([tyler!, shreveport!], 25, ["Tyler, TX", "Shreveport, LA"]);
    expect(routeStates).toContain("TX");
    expect(routeStates).toContain("LA");

    const proxStates = identifyStatesForProximity(tyler![0], tyler![1], 50, "Tyler, TX");
    expect(proxStates).toContain("TX");
  });

  it("runs RouteCorridor, Proximity, Aviation, and SequenceOrganizer engines offline", async () => {
    const rb = new RepeaterBookProvider({ offlineOnly: true });
    const { channels } = await rb.getRepeatersForStates(["TX", "LA"], { allowedUse: ["OPEN"] });
    expect(channels.length).toBeGreaterThan(10);

    const geo = new GeocodingProvider(true);
    const tyler = (await geo.geocode("Tyler, TX"))!;
    const shreveport = (await geo.geocode("Shreveport, LA"))!;

    const corridorMatches = RouteCorridorEngine.filterAndOrder(channels, [tyler, shreveport], 30);
    expect(corridorMatches.length).toBeGreaterThan(0);

    const proxMatches = ProximityEngine.filterAndOrder(channels, tyler[0], tyler[1], 60);
    expect(proxMatches.length).toBeGreaterThan(0);

    const aviation = new AviationEngine().discover(tyler[0], tyler[1], 60);
    expect(aviation.airfields.length).toBeGreaterThan(0);
    expect(aviation.channels.length).toBeGreaterThan(0);

    const assembled = SequenceOrganizer.assemble({
      codeplugName: "Test Plan",
      sequenceKeys: ["TEMPLATE:calling_channels", "ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"],
      primaryChannels: corridorMatches.map((m) => m.channel),
      targetSpec: SAMPLE_SPEC,
      allowedBands: ["2m", "70cm", "WX"],
      allowedModes: ["FM", "AM"],
      namingFormat: "CITY_FREQ",
    });
    expect(assembled.channels.length).toBeGreaterThan(5);
    expect(assembled.channels.some((c) => c.name.includes("GMRS"))).toBe(false);
    expect(getNoaaWxChannels().length).toBe(7);

    // GMRS call channels are included when GMRS band is active on a GMRS-capable radio
    const gmrsAssembled = SequenceOrganizer.assemble({
      codeplugName: "Test Plan GMRS",
      sequenceKeys: ["TEMPLATE:calling_channels"],
      primaryChannels: [],
      targetSpec: SAMPLE_SPEC,
      allowedBands: ["2m", "70cm", "GMRS"],
      allowedModes: ["FM"],
      namingFormat: "CITY_FREQ",
    });
    expect(gmrsAssembled.channels.some((c) => c.rxFreq === 462.675)).toBe(true);

    // Hardware sanitizer drops unsupported Airband for 2m/70cm-only radio
    const vhfOnly: TargetRadioSpec = { ...SAMPLE_SPEC, supportedBands: ["2m", "70cm"], maxChannels: 3 };
    const sanitized = sanitizeChannelsForRadio([...aviation.channels, ...assembled.channels], vhfOnly);
    expect(sanitized.channels.length).toBeLessThanOrEqual(3);
    expect(sanitized.droppedCount).toBeGreaterThan(0);
  });

  it("exports CHIRP (21-column), RT Systems, and Generic CSV + DMR talkgroup expansion", () => {
    const ch1 = createRadioChannel({
      number: 1,
      name: "Tyler 7.20",
      callsign: "W5ETX",
      rxFreq: 147.2,
      txFreq: 147.8,
      offset: 0.6,
      offsetDir: "+",
      mode: "FM",
      power: "High",
      toneMode: "Tone",
      ctcss: "136.5",
      comment: "=SUM(1,2) Test",
    });
    const ch2 = createRadioChannel({
      number: 2,
      name: "DMR Local",
      callsign: "W5DMR",
      rxFreq: 444.5,
      txFreq: 449.5,
      offset: 5.0,
      offsetDir: "+",
      mode: "DMR",
      colorCode: 1,
      timeSlot: 2,
      toneMode: "DCS",
      dcs: "023",
    });

    const chirp = exportChirpCsv([ch1, ch2], SAMPLE_SPEC);
    const chirpHeader = chirp.split("\n")[0].split(",");
    expect(chirpHeader.length).toBe(21);
    expect(chirp).toContain("147.200000,+,0.600000,Tone,136.5");
    expect(chirp).toContain("'=SUM(1,2) Test");

    const rt = exportRtSystemsCsv([ch1, ch2], SAMPLE_SPEC);
    expect(rt).toContain("Receive Frequency,Transmit Frequency");
    expect(rt).toContain("147.20000,147.80000");

    const gen = exportGenericCsv([ch1, ch2], SAMPLE_SPEC);
    expect(gen).toContain("Channel Number,Name,Receive Frequency");
    expect(exportCodeplugCsv([ch1], SAMPLE_SPEC, "CHIRP")).toContain("Location,Name,Frequency");

    const expanded = RadioIdProvider.duplicateChannelForTalkgroups(ch2);
    expect(expanded.length).toBe(5);
    expect(expanded[0].dmrId).toBe("9");
  });
});
