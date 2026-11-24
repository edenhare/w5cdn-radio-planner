/**
 * Unified W5CDN Desktop Suite & RadioPlanner Path Resolver.
 *
 * Mirrors the W5CDN Suite layout shared across Net-Logger, NTS, and RadioPlanner:
 * - Windows: %APPDATA%\W5CDN\RadioPlanner  +  %APPDATA%\W5CDN\shared
 * - Linux/macOS: ~/.config/W5CDN/RadioPlanner  +  ~/.config/W5CDN/shared
 * - Explicit overrides: RADIOPLANNER_HOME, W5CDN_SUITE_DIR
 * - Legacy fallback: preserves ~/.config/radioplanner if it already has preferences.yaml
 *   and the unified W5CDN/RadioPlanner directory has not yet been initialized.
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function getW5cdnSuiteRoot(): string {
  const override = process.env.W5CDN_SUITE_DIR?.trim();
  if (override) {
    return path.resolve(override);
  }
  if (process.platform === "win32") {
    const appData = process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming");
    return path.join(appData, "W5CDN");
  }
  const xdgConfig = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
  return path.join(xdgConfig, "W5CDN");
}

export function getSharedSuiteDir(): string {
  return path.join(getW5cdnSuiteRoot(), "shared");
}

export function getSharedConfigFile(): string {
  return path.join(getSharedSuiteDir(), "config.txt");
}

export function getConfigDir(): string {
  const override = process.env.RADIOPLANNER_HOME?.trim();
  if (override) {
    return path.resolve(override);
  }
  const suiteOverride = process.env.W5CDN_SUITE_DIR?.trim();
  const unified = path.join(getW5cdnSuiteRoot(), "RadioPlanner");
  if (suiteOverride) {
    return unified;
  }
  const legacy = path.join(os.homedir(), ".config", "radioplanner");
  if (!fs.existsSync(path.join(unified, "preferences.yaml")) && fs.existsSync(path.join(legacy, "preferences.yaml"))) {
    return legacy;
  }
  return unified;
}

export function getPreferencesFile(baseDir = getConfigDir()): string {
  return path.join(baseDir, "preferences.yaml");
}

export function getTokensFile(baseDir = getConfigDir()): string {
  return path.join(baseDir, "tokens");
}

export function getUserRadiosDir(baseDir = getConfigDir()): string {
  return path.join(baseDir, "radios");
}

export function getUserTemplatesDir(baseDir = getConfigDir()): string {
  return path.join(baseDir, "templates");
}

export function getUserRecipesDir(baseDir = getConfigDir()): string {
  return path.join(baseDir, "recipes");
}

export function getCacheDir(baseDir = getConfigDir()): string {
  return path.join(baseDir, "cache");
}

export function getSessionFile(baseDir = getConfigDir()): string {
  return path.join(baseDir, "session.json");
}

export function getExportsDir(): string {
  return path.join(process.cwd(), "exports");
}

export function ensureConfigDirectories(baseDir = getConfigDir()): string {
  const dirs = [
    baseDir,
    getUserRadiosDir(baseDir),
    getUserTemplatesDir(baseDir),
    getUserRecipesDir(baseDir),
    getCacheDir(baseDir),
  ];
  for (const d of dirs) {
    fs.mkdirSync(d, { recursive: true });
  }
  if (!process.env.RADIOPLANNER_HOME) {
    const shared = getSharedSuiteDir();
    fs.mkdirSync(shared, { recursive: true });
  }
  return baseDir;
}

/**
 * Resolve bundled read-only resources directory (works in dev tsx/vitest, compiled dist/, and packaged ASAR).
 */
export function resolveResourcesDir(): string {
  const candidates = [
    path.resolve(__dirname, "..", "resources"),
    path.resolve(__dirname, "..", "..", "resources"),
    path.resolve(process.cwd(), "dist", "resources"),
    path.resolve(process.cwd(), "src", "electron", "resources"),
  ];
  for (const cand of candidates) {
    if (fs.existsSync(cand)) {
      return cand;
    }
  }
  return candidates[candidates.length - 1];
}

/**
 * Resolve bundled static UI directory (supports both PR 1 src/web/static and PR 2 src/static + dist/static).
 */
export function resolveStaticDir(): string {
  const candidates = [
    path.resolve(__dirname, "..", "static"),
    path.resolve(__dirname, "..", "..", "static"),
    path.resolve(process.cwd(), "dist", "static"),
    path.resolve(process.cwd(), "src", "static"),
    path.resolve(process.cwd(), "src", "web", "static"),
  ];
  for (const cand of candidates) {
    if (fs.existsSync(path.join(cand, "index.html"))) {
      return cand;
    }
  }
  return candidates[0];
}

/**
 * Read simple KEY=VALUE entries from W5CDN\shared\config.txt (shared with Net-Logger & NTS).
 */
export function readSharedSuiteConfig(): Record<string, string> {
  const filePath = getSharedConfigFile();
  const out: Record<string, string> = {};
  if (!fs.existsSync(filePath)) return out;
  try {
    const lines = fs.readFileSync(filePath, "utf-8").split(/\r?\n/);
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq <= 0) continue;
      const key = line.slice(0, eq).trim();
      const val = line.slice(eq + 1).trim();
      if (key) out[key] = val;
    }
  } catch {
    // Ignore unreadable shared config
  }
  return out;
}
