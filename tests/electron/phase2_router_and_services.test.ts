import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import JSZip from "jszip";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ApiRouter } from "../../src/electron/main/router";
import { startTestServer } from "../../src/electron/main/testServer";
import { WebWorkspace } from "../../src/electron/main/workspace";

describe("Phase 2: ApiRouter Full Parity, Hand-Edit YAML & Backup/Restore", () => {
  let tmpDir: string;
  let workspace: WebWorkspace;
  let router: ApiRouter;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "rp_router_test_"));
    workspace = new WebWorkspace({ baseDir: tmpDir, loadPersistedSession: false, offlineOnly: true });
    router = new ApiRouter(workspace, "0.2.0");
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  async function apiJson(
    method: string,
    pathname: string,
    body?: unknown,
    query?: Record<string, string>,
  ): Promise<{ status: number; data: Record<string, unknown> }> {
    const qs = new URLSearchParams(query ?? {});
    const res = await router.handle({
      method,
      pathname,
      query: qs,
      bodyText: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return { status: res.status, data: JSON.parse(String(res.body)) as Record<string, unknown> };
  }

  it("bootstraps /api/config and updates /api/preferences + tokens", async () => {
    const cfg = await apiJson("GET", "/api/config");
    expect(cfg.status).toBe(200);
    expect(cfg.data.app_title).toBe("W5CDN RadioPlanner");
    expect(Array.isArray(cfg.data.radios)).toBe(true);
    expect((cfg.data.radios as unknown[]).length).toBeGreaterThanOrEqual(8);
    expect((cfg.data.templates as unknown[]).length).toBeGreaterThanOrEqual(4);

    const upd = await apiJson("PUT", "/api/preferences", {
      callsign: "w5cdn",
      operatorName: "Eden",
      colorTheme: "amber-crt",
      uiFontSize: 16,
      repeaterBookApiKey: "secret-rb-token",
      qrzUsername: "W5CDN",
      qrzPassword: "qrz-secret-password",
    });
    expect(upd.status).toBe(200);
    const prefs = upd.data.preferences as Record<string, unknown>;
    expect(prefs.callsign).toBe("W5CDN");
    expect(prefs.theme).toBe("amber-crt");
    expect(prefs.repeaterBookApiKeySet).toBe(true);
    expect(prefs.qrzConfigured).toBe(true);
    expect(fs.existsSync(path.join(tmpDir, "preferences.yaml"))).toBe(true);
    expect(fs.existsSync(path.join(tmpDir, "tokens"))).toBe(true);
  });

  it("generates Route Corridor, Proximity, and Aviation plans + edits, deletes, undoes, reports & exports CSV", async () => {
    // 1. Route Corridor
    const route = await apiJson("POST", "/api/plan/generate", {
      mode: "ROUTE_CORRIDOR",
      waypoints: ["Tyler, TX", "Shreveport, LA"],
      corridor_width: 25,
      radio_id: "baofeng_5rm",
    });
    expect(route.status).toBe(200);
    expect(route.data.active).toBe(true);
    const cp = route.data.codeplug as { total_channels: number; channels: Array<{ number: number; name: string }> };
    expect(cp.total_channels).toBeGreaterThan(5);
    const routeMapChannels = (route.data.map_data as { channels: Array<{ band: string; lat: number; lon: number }> })
      .channels;
    expect(routeMapChannels.some((mc) => mc.band === "2m")).toBe(true);
    expect(routeMapChannels.some((mc) => mc.band === "70cm")).toBe(true);
    expect(routeMapChannels.some((mc) => mc.band === "WX" && mc.lat !== null && mc.lon !== null)).toBe(true);

    // Retarget radio live
    const retarget = await apiJson("POST", "/api/codeplug/update", {
      radio_id: "btech_dmr6x2",
      naming_format: "CALLSIGN_FREQ",
      radio_changed: true,
    });
    expect(retarget.status).toBe(200);

    // Inline channel edit
    const editRes = await apiJson("PATCH", "/api/codeplug/channels/1", {
      name: "CUSTOM1",
      rxFreq: 146.52,
      offsetDir: "off",
      toneMode: "Tone",
      ctcss: "100.0",
    });
    expect(editRes.status).toBe(200);
    const editedCh = (editRes.data.codeplug as { channels: Array<{ name: string }> }).channels[0];
    expect(editedCh.name).toBe("CUSTOM1");

    // Net Logger preset JSON for slot 1
    const presetRes = await apiJson("GET", "/api/codeplug/channels/1/net-logger-preset");
    expect(presetRes.status).toBe(200);
    expect((presetRes.data.preset as { frequency: string }).frequency).toBe("146.5200 MHz");

    // Delete channel & undo
    const countBefore = (editRes.data.codeplug as { total_channels: number }).total_channels;
    const delRes = await apiJson("POST", "/api/codeplug/delete-channels", { slots: [1] });
    expect(delRes.status).toBe(200);
    expect((delRes.data.codeplug as { total_channels: number }).total_channels).toBe(countBefore - 1);

    const undoRes = await apiJson("POST", "/api/codeplug/undo-delete");
    expect(undoRes.status).toBe(200);
    expect((undoRes.data.codeplug as { total_channels: number }).total_channels).toBe(countBefore);

    // Pocket report & CSV export
    const report = await apiJson("GET", "/api/codeplug/report");
    expect(report.status).toBe(200);
    expect(String(report.data.text)).toContain("RADIOPLANNER CODEPLUG REFERENCE CARD");

    const csvRes = await router.handle({
      method: "POST",
      pathname: "/api/codeplug/export",
      query: new URLSearchParams(),
      bodyText: JSON.stringify({ programmer_type: "CHIRP", filename: "test_route.csv" }),
    });
    expect(csvRes.status).toBe(200);
    expect(String(csvRes.body)).toContain("Location,Name,Frequency");

    // 2. Proximity Search
    const prox = await apiJson("POST", "/api/plan/generate", {
      mode: "PROXIMITY_SEARCH",
      center_location: "Dallas, TX",
      radius_miles: 50,
      radio_id: "baofeng_5rm",
    });
    expect(prox.status).toBe(200);
    expect(Array.isArray((prox.data.map_data as { rings: unknown[] }).rings)).toBe(true);

    // 3. Aviation Planner
    const air = await apiJson("POST", "/api/plan/generate", {
      mode: "AVIATION_PLANNER",
      center_location: "Tyler, TX",
      radius_miles: 50,
      radio_id: "baofeng_5rm",
    });
    expect(air.status).toBe(200);
    expect((air.data.codeplug as { total_channels: number }).total_channels).toBeGreaterThan(0);
  });

  it("supports hand-editable YAML Export & Strictly Validated Import for Radios, Templates, and Recipes", async () => {
    // 1. Export radio YAML, hand-edit it, and re-import it
    const expRadio = await router.handle({
      method: "GET",
      pathname: "/api/radios/baofeng_5rm/export",
      query: new URLSearchParams(),
    });
    expect(expRadio.status).toBe(200);
    const radioYaml = String(expRadio.body);
    expect(radioYaml).toContain("id: baofeng_5rm");

    const handEditedRadioYaml = radioYaml
      .replace("id: baofeng_5rm", "id: custom_ft60r")
      .replace("brand: Baofeng", "brand: Yaesu")
      .replace("model: 5RM", "model: FT-60R");

    const impRadio = await apiJson("POST", "/api/radios/import", {
      filename: "custom_ft60r.yaml",
      yaml_text: handEditedRadioYaml,
    });
    expect(impRadio.status).toBe(200);
    expect(impRadio.data.imported).toBe(true);
    expect(workspace.radioMgr.hasRadio("custom_ft60r")).toBe(true);

    // Invalid hand-edited radio YAML is rejected with clear 400 diagnostic
    const badRadio = await apiJson("POST", "/api/radios/import", {
      filename: "bad_radio.yaml",
      yaml_text: "id: bad slug!\nbrand: ''\nmaxChannels: -5\n",
    });
    expect(badRadio.status).toBe(400);
    expect(String(badRadio.data.detail)).toContain("schema validation");

    // 2. Export template YAML & import custom template (YAML + Net Logger JSON)
    const expTpl = await router.handle({
      method: "GET",
      pathname: "/api/templates/calling_channels/export",
      query: new URLSearchParams(),
    });
    expect(expTpl.status).toBe(200);
    expect(String(expTpl.body)).toContain("id: calling_channels");

    const impNetLog = await apiJson("POST", "/api/templates/import-net-logger", {
      id: "w5cdn_nets",
      name: "W5CDN Nets",
      tagText: "NETLOG",
      json_text: JSON.stringify({
        net_type_defaults: {
          "East TX ARES": { frequency: "147.200 MHz", tone_offset: "+0.600 MHz / PL 136.5", mode: "FM" },
        },
      }),
    });
    expect(impNetLog.status).toBe(200);
    expect(workspace.templateMgr.hasTemplate("w5cdn_nets")).toBe(true);

    // 3. Save, Export, Re-Upload, and Delete Recipe YAML
    await apiJson("POST", "/api/plan/generate", {
      mode: "ROUTE_CORRIDOR",
      waypoints: ["Tyler, TX", "Shreveport, LA"],
      radio_id: "baofeng_5rm",
    });
    const savedRec = await apiJson("POST", "/api/recipes/save", {
      name: "I20_EastTX_Trip",
      description: "Test corridor recipe",
    });
    expect(savedRec.status).toBe(200);
    const fname = String(savedRec.data.filename);

    const expRec = await router.handle({
      method: "GET",
      pathname: `/api/recipes/${encodeURIComponent(fname)}/export`,
      query: new URLSearchParams(),
    });
    expect(expRec.status).toBe(200);
    expect(String(expRec.body)).toContain("mode: ROUTE_CORRIDOR");

    const reloadRes = await apiJson("POST", "/api/workspace/reload");
    expect(reloadRes.status).toBe(200);
    expect(reloadRes.data.reloaded).toBe(true);

    const delRec = await apiJson("DELETE", `/api/recipes/${encodeURIComponent(fname)}`);
    expect(delRec.status).toBe(200);
  });

  it("creates and restores ZIP backups safely while rejecting Zip-Slip attacks", async () => {
    await apiJson("PUT", "/api/preferences", { callsign: "K5TEST" });

    const exp = await router.handle({
      method: "GET",
      pathname: "/api/backup/export",
      query: new URLSearchParams({ include_tokens: "false" }),
    });
    expect(exp.status).toBe(200);
    expect(Buffer.isBuffer(exp.body)).toBe(true);

    // Mutate preferences, then restore from ZIP
    await apiJson("PUT", "/api/preferences", { callsign: "N0TEMP" });
    const restoreRes = await router.handle({
      method: "POST",
      pathname: "/api/backup/restore",
      query: new URLSearchParams(),
      bodyBuffer: exp.body as Buffer,
    });
    expect(restoreRes.status).toBe(200);
    expect(workspace.prefsMgr.preferences.callsign).toBe("K5TEST");
    expect(fs.existsSync(path.join(tmpDir, "radioplanner.pre_restore.bak"))).toBe(true);

    // Zip-Slip rejection
    const evilZip = new JSZip();
    evilZip.file("../evil.yaml", "pwned: true\n");
    const evilBuf = await evilZip.generateAsync({ type: "nodebuffer" });
    const evilRes = await router.handle({
      method: "POST",
      pathname: "/api/backup/restore",
      query: new URLSearchParams(),
      bodyBuffer: evilBuf,
    });
    expect(evilRes.status).toBe(400);
    expect(String(evilRes.body)).toContain("unsafe path");
  });

  it("serves static UI and API over ephemeral localhost testServer", async () => {
    const srv = await startTestServer({ baseDir: tmpDir, offlineOnly: true });
    try {
      const idx = await fetch(`${srv.url}/`);
      expect(idx.status).toBe(200);
      expect(await idx.text()).toContain("W5CDN RadioPlanner");

      const cfg = await fetch(`${srv.url}/api/config`);
      expect(cfg.status).toBe(200);
      const data = (await cfg.json()) as { app_title: string };
      expect(data.app_title).toBe("W5CDN RadioPlanner");
    } finally {
      await srv.close();
    }
  });
});
