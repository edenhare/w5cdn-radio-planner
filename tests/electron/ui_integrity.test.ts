import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { describe, expect, it } from "vitest";
import { resolveStaticDir } from "../../src/electron/main/paths";

describe("UI Integrity & Offline Assets", () => {
  const staticDir = resolveStaticDir();

  it("contains index.html, styles.css, app.js, and vendored offline Leaflet", () => {
    expect(fs.existsSync(path.join(staticDir, "index.html"))).toBe(true);
    expect(fs.existsSync(path.join(staticDir, "styles.css"))).toBe(true);
    expect(fs.existsSync(path.join(staticDir, "app.js"))).toBe(true);
    expect(fs.existsSync(path.join(staticDir, "vendor", "leaflet", "leaflet.js"))).toBe(true);
    expect(fs.existsSync(path.join(staticDir, "vendor", "leaflet", "leaflet.css"))).toBe(true);
  });

  it("parses app.js cleanly with zero syntax errors and exposes hand-edit YAML hooks", () => {
    const js = fs.readFileSync(path.join(staticDir, "app.js"), "utf-8");
    expect(() => new vm.Script(js, { filename: "app.js" })).not.toThrow();

    expect(js).toContain("window.desktopApi");
    expect(js).toContain("/api/radios/import");
    expect(js).toContain("/api/workspace/reload");
  });

  it("includes all 9 W5CDN Suite cockpit themes and required hand-edit UI controls in index.html", () => {
    const html = fs.readFileSync(path.join(staticDir, "index.html"), "utf-8");
    const requiredIds = [
      "rpVersionPill",
      "btnImportRadioYaml",
      "radioImportYamlFile",
      "btnOpenConfigFolder",
      "btnReloadConfigs",
      "configDirPath",
      "plannerForm",
      "targetRadioSelect",
      "channelsTbody",
      "planLeafletMap",
    ];
    for (const id of requiredIds) {
      expect(html).toContain(`id="${id}"`);
    }

    const css = fs.readFileSync(path.join(staticDir, "styles.css"), "utf-8");
    for (const theme of [
      "shack-dark",
      "night-red",
      "amber-crt",
      "forest-eoc",
      "daylight",
      "paper-warm",
      "eoc-light",
      "sky-breeze",
      "high-contrast",
    ]) {
      expect(css).toContain(theme);
    }
  });
});
