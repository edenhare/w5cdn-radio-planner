import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CallsignLookupService } from "../../src/electron/main/providers/callsignLookup";
import { GeocodingProvider } from "../../src/electron/main/providers/geocoding";
import { NwsAlertsService } from "../../src/electron/main/providers/nws";
import { RadioIdProvider } from "../../src/electron/main/providers/radioId";
import { RepeaterBookProvider } from "../../src/electron/main/providers/repeaterbook";
import { ApiRouter } from "../../src/electron/main/router";
import {
  isNewerVersion,
  parseSemver,
  parseSha256Sums,
  selectReleaseAsset,
  validateDownloadUrl,
  verifySha256,
} from "../../src/electron/main/updater";
import { WebWorkspace } from "../../src/electron/main/workspace";

describe("Phase 3: Online Providers (Mocked Fetch), Session Persistence & Router Edge Cases", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("handles CallsignLookupService QRZ XML auth, single-pass entity decoding, XXE guard, and Callook fallback", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    // 1. QRZ auth + lookup
    fetchMock
      .mockResolvedValueOnce(
        new Response("<QRZDatabase><Session><Key>abc123</Key></Session></QRZDatabase>", { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          "<QRZDatabase><Callsign><call>W5CDN</call><fname>Eden &amp; Friends</fname><name>Hare</name><addr2>Tyler</addr2><state>TX</state><grid>EM22</grid><lat>32.35</lat><lon>-95.30</lon><class>E</class></Callsign></QRZDatabase>",
          { status: 200 },
        ),
      );

    const svc = new CallsignLookupService("W5CDN", "pass123");
    const res = await svc.lookup("w5cdn");
    expect(res).not.toBeNull();
    expect(res!.callsign).toBe("W5CDN");
    expect(res!.name).toBe("Eden & Friends Hare");
    expect(res!.source).toBe("QRZ");

    // 2. XXE rejection returns null safely
    fetchMock.mockResolvedValueOnce(
      new Response('<!DOCTYPE foo [<!ENTITY xxe "bad">]><QRZDatabase><Session><Key>k</Key></Session></QRZDatabase>', {
        status: 200,
      }),
    );
    const xxeTest = await new CallsignLookupService("u", "p").testQrzLogin();
    expect(xxeTest.ok).toBe(false);
    expect(xxeTest.message).toContain("DOCTYPE");

    // 3. Callook fallback when no QRZ credentials
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: "VALID",
          current: { callsign: "W1AW", operClass: "CLUB" },
          name: "ARRL HQ",
          address: { line2: "Newington, CT 06111" },
          location: { latitude: "41.714", longitude: "-72.727", gridsquare: "FN31pr" },
        }),
        { status: 200 },
      ),
    );
    const callook = await new CallsignLookupService().lookup("W1AW");
    expect(callook).not.toBeNull();
    expect(callook!.source).toBe("Callook.info");
    expect(callook!.city).toBe("Newington");
    expect(callook!.state).toBe("CT");
  });

  it("handles NwsAlertsService online alerts, empty states, and offline mode", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          features: [
            {
              id: "nws-1",
              properties: {
                event: "Severe Thunderstorm Watch",
                severity: "Severe",
                headline: "Severe Thunderstorm Watch in effect",
                areaDesc: "Smith County, TX",
                effective: "2026-11-24T12:00:00Z",
                expires: "2026-11-24T20:00:00Z",
                description: "Damaging winds possible.",
                instruction: "Move indoors.",
              },
            },
          ],
        }),
        { status: 200 },
      ),
    );

    const nws = new NwsAlertsService(false);
    const active = await nws.getAlertsForStates(["tx", "TX"]);
    expect(active.online).toBe(true);
    expect(active.count).toBe(1);
    expect(active.alerts[0].event).toBe("Severe Thunderstorm Watch");
    expect(active.briefing_text).toContain("SEVERE");

    const empty = await nws.getAlertsForStates([]);
    expect(empty.count).toBe(0);

    const offline = await new NwsAlertsService(true).getAlertsForStates(["TX"]);
    expect(offline.online).toBe(false);
  });

  it("handles RadioIdProvider, GeocodingProvider online paths, and RepeaterBook disk cache", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    // RadioID lookup
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          results: [{ callsign: "W5CDN", id: 3148001, fname: "Eden", surname: "Hare", city: "Tyler", state: "TX", country: "US" }],
        }),
        { status: 200 },
      ),
    );
    const rid = await new RadioIdProvider(false).lookupCallsign("W5CDN");
    expect(rid?.dmrId).toBe("3148001");

    // Geocoding direct coords + Nominatim + reverse + IP
    const geo = new GeocodingProvider(false);
    expect(await geo.geocode("32.35, -95.30")).toEqual([32.35, -95.3]);

    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([{ lat: "30.2672", lon: "-97.7431" }]), { status: 200 }));
    expect(await geo.geocode("Obscure Hamlet, TX")).toEqual([30.2672, -97.7431]);

    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ address: { city: "Tyler", state: "Texas" } }), { status: 200 }),
    );
    expect(await geo.reverseGeocode(32.35, -95.3)).toBe("Tyler, Texas");

    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "success", city: "Tyler", region: "TX", lat: 32.35, lon: -95.3 }), {
        status: 200,
      }),
    );
    const ipLoc = await geo.geolocateByIp();
    expect(ipLoc?.label).toBe("Tyler, TX");

    // RepeaterBook live download -> cache write -> listCachedStateFiles
    const tmpCache = fs.mkdtempSync(path.join(os.tmpdir(), "rp_cache_"));
    try {
      fetchMock.mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            results: [
              {
                Frequency: "147.2000",
                "Input Freq": "147.8000",
                Callsign: "W5ETX",
                "Nearest City": "Tyler",
                State: "TX",
                Lat: "32.35",
                Long: "-95.30",
                PL: "136.5",
                Use: "OPEN",
              },
            ],
          }),
          { status: 200 },
        ),
      );
      const rb = new RepeaterBookProvider({ cacheDir: tmpCache, apiKey: "test-key", offlineOnly: false });
      expect(rb.hasApiKey()).toBe(true);
      const live = await rb.getRepeatersForStates(["TX"], { allowedUse: ["OPEN"], includeGmrs: false });
      expect(live.sources).toContain("live:TX");
      expect(live.channels.length).toBe(1);
      const cachedFiles = rb.listCachedStateFiles();
      expect(cachedFiles.length).toBe(1);
      expect(cachedFiles[0].state).toBe("TX");

      // Test RepeaterBook API key verification (empty key, valid key, 401 rejected key)
      expect((await rb.testApiKey("")).ok).toBe(false);
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ results: [{ Frequency: "146.9400", Callsign: "W3DEL" }] }), { status: 200 }),
      );
      const validKeyTest = await rb.testApiKey("valid-rb-token");
      expect(validKeyTest.ok).toBe(true);
      expect(validKeyTest.count).toBe(1);

      fetchMock.mockResolvedValueOnce(new Response("Unauthorized", { status: 401 }));
      const badKeyTest = await rb.testApiKey("invalid-rb-token");
      expect(badKeyTest.ok).toBe(false);
      expect(badKeyTest.message).toContain("401");
    } finally {
      fs.rmSync(tmpCache, { recursive: true, force: true });
    }
  });

  it("persists and reloads session.json and exercises all remaining ApiRouter endpoints", async () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "rp_full_"));
    try {
      const ws1 = new WebWorkspace({ baseDir: tmpDir, loadPersistedSession: false, offlineOnly: true });
      const router = new ApiRouter(ws1, "0.2.0");

      const call = async (method: string, pathname: string, body?: unknown, query?: Record<string, string>) => {
        const res = await router.handle({
          method,
          pathname,
          query: new URLSearchParams(query ?? {}),
          bodyText: body !== undefined ? JSON.stringify(body) : undefined,
        });
        return { status: res.status, data: JSON.parse(String(res.body)) as Record<string, unknown> };
      };

      // Generate plan (saves session.json)
      const gen = await call("POST", "/api/plan/generate", {
        mode: "ROUTE_CORRIDOR",
        waypoints: ["Tyler, TX", "Shreveport, LA"],
        radio_id: "btech_dmr6x2",
      });
      expect(gen.status).toBe(200);

      // Reload persisted session into a fresh WebWorkspace instance
      const ws2 = new WebWorkspace({ baseDir: tmpDir, loadPersistedSession: true, offlineOnly: true });
      expect(ws2.session.codeplug).not.toBeNull();
      expect(ws2.session.codeplug!.channels.length).toBeGreaterThan(0);

      // Naming previews for both Corridor and Aviation modes
      const prev1 = await call("GET", "/api/radios/baofeng_5rm/naming-previews", undefined, { mode: "ROUTE_CORRIDOR" });
      expect(prev1.status).toBe(200);
      const prev2 = await call("GET", "/api/radios/baofeng_5rm/naming-previews", undefined, { mode: "AVIATION_PLANNER" });
      expect(prev2.status).toBe(200);

      // Save & delete custom radio via form API
      const saveRad = await call("POST", "/api/radios", {
        id: "icom_id52",
        brand: "Icom",
        model: "ID-52A",
        maxChannels: 500,
        maxNameLength: 16,
        supportedBands: ["2m", "70cm", "Airband", "WX"],
        supportedModes: ["FM", "AM"],
      });
      expect(saveRad.status).toBe(200);
      expect((await call("DELETE", "/api/radios/icom_id52")).status).toBe(200);

      // Save, import CSV, import YAML, and delete custom template
      const saveTpl = await call("POST", "/api/templates", {
        id: "club_nets",
        name: "Club Nets",
        tagText: "CLUB",
        channels: [
          { name: "Club 2m", rxFreq: 147.2, offsetDir: "+", offset: 0.6, mode: "FM", power: "High", toneMode: "Tone", toneVal: "136.5" },
          { name: "Club DCS", rxFreq: 444.5, offsetDir: "+", offset: 5.0, mode: "FM", power: "Mid", toneMode: "DCS", toneVal: "023" },
        ],
      });
      expect(saveTpl.status).toBe(200);
      const impCsv = await call("POST", "/api/templates/import", {
        id: "csv_tpl",
        name: "CSV Imported",
        filename: "sample.csv",
        content: "Name,RX Frequency,TX Frequency,Mode,Power,Comment\nSimplex1,146.520,146.520,FM,High,Test\n",
      });
      expect(impCsv.status).toBe(200);
      expect((await call("DELETE", "/api/templates/calling_channels")).status).toBe(400);
      expect((await call("DELETE", "/api/templates/club_nets")).status).toBe(200);

      // Upload recipe YAML
      const upRec = await call("POST", "/api/recipes/upload", {
        filename: "uploaded.yaml",
        yaml_text: "mode: PROXIMITY_SEARCH\nname: Uploaded Dallas\nproximity:\n  center_location: Dallas, TX\n  radius_miles: 30\n",
      });
      expect(upRec.status).toBe(200);

      // Expand DMR, geolocate reverse, nws alerts, update check, client unload
      expect((await call("POST", "/api/codeplug/expand-dmr")).status).toBe(200);
      expect((await call("GET", "/api/geolocate", undefined, { lat: "32.35", lon: "-95.30" })).status).toBe(200);
      expect((await call("GET", "/api/nws/plan-alerts", undefined, { states: "TX" })).status).toBe(200);
      expect((await call("GET", "/api/update/check")).status).toBe(200);
      expect((await call("POST", "/api/client/unload")).status).toBe(200);
      expect((await call("GET", "/api/does-not-exist")).status).toBe(404);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it("verifies dual-mode self-updater asset selection, SHA-256 verification, pre-update backup, and /api/update/apply", async () => {
    expect(parseSemver("v0.2.1")).toEqual([0, 2, 1]);
    expect(isNewerVersion("v0.2.1", "0.2.0")).toBe(true);
    expect(isNewerVersion("v0.2.0", "0.2.0")).toBe(false);
    expect(() => validateDownloadUrl("https://evil.example.com/setup.exe")).toThrow();
    expect(validateDownloadUrl("https://github.com/edenhare/w5cdn-radio-planner/releases/download/v0.2.1/SHA256SUMS.txt")).toContain(
      "https://github.com/",
    );

    const sampleAssets = [
      {
        name: "W5CDN.RadioPlanner.Setup.0.2.1.exe",
        browser_download_url:
          "https://github.com/edenhare/w5cdn-radio-planner/releases/download/v0.2.1/W5CDN.RadioPlanner.Setup.0.2.1.exe",
      },
      {
        name: "W5CDN.RadioPlanner-0.2.1.AppImage",
        browser_download_url:
          "https://github.com/edenhare/w5cdn-radio-planner/releases/download/v0.2.1/W5CDN.RadioPlanner-0.2.1.AppImage",
      },
      {
        name: "SHA256SUMS.txt",
        browser_download_url:
          "https://github.com/edenhare/w5cdn-radio-planner/releases/download/v0.2.1/SHA256SUMS.txt",
      },
    ];

    const winSel = selectReleaseAsset(sampleAssets, "win32");
    expect(winSel.asset?.name).toBe("W5CDN.RadioPlanner.Setup.0.2.1.exe");
    expect(winSel.checksum?.name).toBe("SHA256SUMS.txt");

    const linSel = selectReleaseAsset(sampleAssets, "linux");
    expect(linSel.asset?.name).toBe("W5CDN.RadioPlanner-0.2.1.AppImage");

    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "rp-updater-"));
    try {
      const dummyPayload = Buffer.from("FAKE_INSTALLER_BINARY_PAYLOAD_0.2.1", "utf-8");
      const dummyHash = crypto.createHash("sha256").update(dummyPayload).digest("hex");
      const sumsText = [
        `${dummyHash}  W5CDN.RadioPlanner.Setup.0.2.1.exe`,
        `${dummyHash}  W5CDN.RadioPlanner-0.2.1.AppImage`,
      ].join("\n");
      const parsedSums = parseSha256Sums(sumsText);
      expect(parsedSums["W5CDN.RadioPlanner.Setup.0.2.1.exe"]).toBe(dummyHash);

      const ws = new WebWorkspace({ baseDir: tmpDir, loadPersistedSession: false, offlineOnly: false });
      const router = new ApiRouter(ws, "0.2.0");
      router.updateFetchFn = async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/releases/latest")) {
          return new Response(
            JSON.stringify({
              tag_name: "v0.2.1",
              name: "W5CDN RadioPlanner v0.2.1",
              html_url: "https://github.com/edenhare/w5cdn-radio-planner/releases/tag/v0.2.1",
              body: "### Changes\n- Self-updater & UI fixes",
              assets: sampleAssets,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.endsWith("SHA256SUMS.txt")) {
          return new Response(sumsText, { status: 200 });
        }
        return new Response(dummyPayload, { status: 200 });
      };

      const prevMode = process.env.RADIOPLANNER_INSTALL_MODE;
      process.env.RADIOPLANNER_INSTALL_MODE = "standalone";
      try {
        const chkRes = await router.handle({
          method: "GET",
          pathname: "/api/update/check",
          query: new URLSearchParams(),
        });
        expect(chkRes.status).toBe(200);
        const chkData = JSON.parse(String(chkRes.body)) as Record<string, unknown>;
        expect(chkData.update_available).toBe(true);
        expect(chkData.can_self_update).toBe(true);
        expect(chkData.latest_version).toBe("0.2.1");

        const applyRes = await router.handle({
          method: "POST",
          pathname: "/api/update/apply",
          query: new URLSearchParams(),
        });
        expect(applyRes.status).toBe(200);
        const applyData = JSON.parse(String(applyRes.body)) as Record<string, unknown>;
        expect(applyData.ok).toBe(true);
        expect(applyData.backup_created).toBe(true);
        expect(fs.existsSync(path.join(tmpDir, "radioplanner.pre_update.bak"))).toBe(true);
        const stagedInstaller = String(applyData.installer_path);
        expect(verifySha256(stagedInstaller, dummyHash)).toBe(true);
      } finally {
        if (prevMode === undefined) delete process.env.RADIOPLANNER_INSTALL_MODE;
        else process.env.RADIOPLANNER_INSTALL_MODE = prevMode;
      }
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});
