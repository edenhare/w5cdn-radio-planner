import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const { startTestServer } = require("../../dist/main/testServer.js");

async function run() {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "rp_e2e_"));
  const srv = await startTestServer({ baseDir: tmpDir, offlineOnly: true });
  const browser = await chromium.launch({ headless: true });

  const consoleErrors = [];
  const pageErrors = [];

  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => pageErrors.push(err.message));

    await page.goto(srv.url, { waitUntil: "networkidle" });
    await page.waitForSelector("#rpVersionPill");

    const title = await page.title();
    assert.ok(title.includes("RadioPlanner"), `Unexpected title: ${title}`);

    // 1. Assemble Route Corridor plan via topbar button
    await page.click("#btnTopAssemble");
    await page.waitForSelector("#activePlanWorkspace:not(.hidden)", { timeout: 10000 });
    const rowCount = await page.locator("#channelsTbody tr").count();
    assert.ok(rowCount > 5, `Expected >5 channels assembled, got ${rowCount}`);

    // Verify WX station locations are plotted on the map alongside 2m and 70cm repeaters
    const mapBands = await page.evaluate(async () => {
      const res = await fetch("/api/plan/current");
      const plan = await res.json();
      const mapCh = plan?.map_data?.channels || [];
      const bands = Array.from(new Set(mapCh.map((c) => c.band)));
      const wxMarkers = mapCh.filter((c) => c.band === "WX" && typeof c.lat === "number" && typeof c.lon === "number");
      return { bands, wxMarkerCount: wxMarkers.length };
    });
    assert.ok(mapBands.bands.includes("2m"), `Expected 2m markers on map, got ${mapBands.bands.join(",")}`);
    assert.ok(mapBands.bands.includes("70cm"), `Expected 70cm markers on map, got ${mapBands.bands.join(",")}`);
    assert.ok(
      mapBands.wxMarkerCount >= 2,
      `Expected >=2 NOAA WX transmitter station markers on map, got ${mapBands.wxMarkerCount}`,
    );

    // Verify collapsible panes in Plan Builder and Active Route Corridor panel
    await page.click('#paneCorridorRoute > summary');
    assert.equal(await page.locator("#paneCorridorRoute").getAttribute("open"), null, "paneCorridorRoute should collapse");
    await page.click('#paneCorridorRoute > summary');
    assert.notEqual(await page.locator("#paneCorridorRoute").getAttribute("open"), null, "paneCorridorRoute should re-open");

    await page.click('[data-toggle-pane="targetBarBody"]');
    assert.ok(await page.locator("#targetBarBody").evaluate((el) => el.classList.contains("hidden")), "targetBarBody should collapse");
    await page.click('[data-toggle-pane="targetBarBody"]');
    assert.ok(!(await page.locator("#targetBarBody").evaluate((el) => el.classList.contains("hidden"))), "targetBarBody should expand");

    // 2. Switch target radio live
    await page.selectOption("#targetRadioSelect", "btech_dmr6x2");
    await page.waitForTimeout(400);

    // 3. Open Pocket Card / Report modal
    await page.click("#btnPlanReport");
    await page.waitForSelector("#planReportBackdrop:not(.hidden)");
    const reportText = await page.locator("#planReportText").inputValue();
    assert.ok(reportText.includes("RADIOPLANNER CODEPLUG REFERENCE CARD"), "Pocket report missing header");
    await page.click('#planReportBackdrop [data-close-modal="planReportBackdrop"]');

    // 4. Open Radios panel and verify Export YAML & Import YAML controls
    await page.click("#btnToggleRadios");
    await page.waitForSelector("#panelRadios:not(.hidden)");
    assert.ok(await page.locator("#btnImportRadioYaml").isVisible(), "Import YAML button missing");
    assert.ok((await page.locator('#radiosList [data-radio-action="export"]').count()) >= 8, "Radio YAML export buttons missing");

    // 5. Switch theme via Preferences modal, test RepeaterBook API Key button & verify hand-edit config section
    await page.click("#btnOpenPrefs");
    await page.waitForSelector("#prefsModalBackdrop:not(.hidden)");
    await page.click('[data-theme-pick="amber-crt"]');
    await page.click('[data-pref-tab="api"]');
    await page.waitForSelector("#btnTestRbKey");
    await page.fill("#prefRbKey", "test-repeaterbook-token");
    await page.click("#btnTestRbKey");
    await page.waitForSelector("#rbTestBanner.ok");
    await page.click('[data-pref-tab="system"]');
    await page.waitForSelector("#btnReloadConfigs");
    await page.click('#prefsForm button[type="submit"]');
    await page.waitForSelector("#prefsModalBackdrop", { state: "hidden" });

    const activeTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    assert.equal(activeTheme, "amber-crt", "Theme did not persist to amber-crt");

    // 6. Validate Sample LCD and panel objects stay inside panels across font sizes (11px..22px UI, 12px..26px LCD)
    for (const [uiSize, lcdSize] of [
      [11, 12],
      [14, 15],
      [18, 22],
      [22, 26],
    ]) {
      const layoutCheck = await page.evaluate(
        ([uSize, lSize]) => {
          const root = document.documentElement;
          root.style.setProperty("--font-size", `${uSize}px`);
          root.style.setProperty("--callsign-size", `${lSize}px`);

          const targetBar = document.getElementById("targetBar").getBoundingClientRect();
          const sampleLcd = document.getElementById("targetNamingSample").getBoundingClientRect();
          const mainPanel = document.querySelector("main.main").getBoundingClientRect();
          const builderPanel = document.getElementById("panelBuilder").getBoundingClientRect();
          const builderModeSeg = document
            .querySelector('#panelBuilder [aria-label="Operating Mode"]')
            .getBoundingClientRect();
          const accessGrid = document.querySelector("#builderAccessSection .access-grid").getBoundingClientRect();
          const summaryPanel = document.getElementById("panelSummary").getBoundingClientRect();
          const summaryBands = document.getElementById("summaryBandBreakdown").getBoundingClientRect();

          return {
            uSize,
            lSize,
            sampleFitsTargetBar:
              sampleLcd.right <= targetBar.right + 1 && sampleLcd.left >= targetBar.left - 1,
            targetBarFitsMain:
              targetBar.right <= mainPanel.right + 1 && targetBar.left >= mainPanel.left - 1,
            modeFitsBuilder:
              builderModeSeg.right <= builderPanel.right + 1 &&
              builderModeSeg.left >= builderPanel.left - 1,
            accessFitsBuilder:
              accessGrid.right <= builderPanel.right + 1 && accessGrid.left >= builderPanel.left - 1,
            bandsFitSummary:
              summaryBands.right <= summaryPanel.right + 1 &&
              summaryBands.left >= summaryPanel.left - 1,
          };
        },
        [uiSize, lcdSize],
      );

      assert.ok(
        layoutCheck.sampleFitsTargetBar,
        `Sample LCD overflowed targetBar at font=${uiSize}px lcd=${lcdSize}px: ${JSON.stringify(layoutCheck)}`,
      );
      assert.ok(
        layoutCheck.targetBarFitsMain,
        `targetBar overflowed main panel at font=${uiSize}px lcd=${lcdSize}px: ${JSON.stringify(layoutCheck)}`,
      );
      assert.ok(
        layoutCheck.modeFitsBuilder,
        `Operating mode buttons overflowed Plan Builder at font=${uiSize}px: ${JSON.stringify(layoutCheck)}`,
      );
      assert.ok(
        layoutCheck.accessFitsBuilder,
        `Access filter checkboxes overflowed Plan Builder at font=${uiSize}px: ${JSON.stringify(layoutCheck)}`,
      );
      assert.ok(
        layoutCheck.bandsFitSummary,
        `Band breakdown cards overflowed Plan Summary at font=${uiSize}px: ${JSON.stringify(layoutCheck)}`,
      );
    }

    assert.equal(pageErrors.length, 0, `Page errors detected: ${pageErrors.join("; ")}`);
    assert.equal(consoleErrors.length, 0, `Console errors detected: ${consoleErrors.join("; ")}`);

    // 7. Verify strict YAML validation rejects malformed radio YAML over HTTP API
    const badHttp = await fetch(`${srv.url}/api/radios/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: "bad.yaml", yaml_text: "id: bad slug!\nmaxChannels: -1\n" }),
    });
    const badBody = await badHttp.json();
    assert.equal(badHttp.status, 400);
    assert.ok(String(badBody.detail).includes("schema validation"));

    console.log(`PLAYWRIGHT_E2E_OK rows=${rowCount} theme=${activeTheme}`);
  } finally {
    await browser.close();
    await srv.close();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

run().catch((err) => {
  console.error("PLAYWRIGHT_E2E_FAILED:", err);
  process.exit(1);
});
