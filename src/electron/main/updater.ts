/**
 * Dual-Mode Application Self-Update Engine for W5CDN RadioPlanner.
 *
 * Supports:
 * 1. Standalone packaged Electron builds (Windows NSIS .exe, Linux .AppImage, or .zip bundles)
 *    with strict GitHub host allowlisting, SHA256SUMS.txt cryptographic verification,
 *    automatic pre-update configuration backup (`radioplanner.pre_update.bak`), and detached
 *    installer launch & swap on exit.
 * 2. Git source checkouts (`git fetch origin --tags && git pull --ff-only origin main`).
 */

import { spawn, spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { sanitizeHttpUrl } from "../shared/sanitize";
import { createConfigBackupZipBytes } from "./backup";
import { WebWorkspace } from "./workspace";

export const DEFAULT_UPDATE_REPO = "edenhare/w5cdn-radio-planner";

const REPO_SLUG_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const SEMVER_RE = /^v?(\d+)\.(\d+)\.(\d+)/i;
const SHA256_HEX_RE = /^[0-9a-f]{64}$/i;

export const ALLOWED_DOWNLOAD_HOSTS = new Set([
  "github.com",
  "objects.githubusercontent.com",
  "release-assets.githubusercontent.com",
  "codeload.github.com",
]);

export const MAX_UPDATE_ARCHIVE_BYTES = 250 * 1024 * 1024;

export type InstallMode = "standalone" | "git" | "source";

export const UPDATE_ERROR_MESSAGES: Record<string, string> = {
  untrusted_url: "Update download URL is not on an allowed GitHub host.",
  git_missing: "Git is not installed or not on PATH; cannot apply source update automatically.",
  git_branch_unknown: "Could not determine the active Git branch.",
  git_non_main: "Self-update only updates the 'main' or 'master' branch. Switch to main first.",
  git_status_failed: "Could not check Git working tree status.",
  git_dirty: "Local uncommitted changes detected. Commit or stash your changes before updating.",
  git_fetch_failed: "Could not fetch updates from origin. Check network connectivity.",
  git_pull_failed: "Could not fast-forward local branch from origin.",
  archive_invalid_name: "Invalid standalone update package filename.",
  checksum_missing: "Matching SHA-256 checksum was not found in SHA256SUMS.txt.",
  download_too_large: "Update package exceeds maximum allowed download size (250 MB).",
  download_failed: "Failed to download update package from GitHub Releases.",
  checksum_mismatch: "Update package failed SHA-256 integrity verification and was discarded.",
};

export class UpdateError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(UPDATE_ERROR_MESSAGES[code] ?? "Application update failed.");
    this.name = "UpdateError";
    this.code = code;
  }
}

export function safeUpdateErrorMessage(err: unknown): string {
  if (err instanceof UpdateError) {
    return UPDATE_ERROR_MESSAGES[err.code] ?? "Application update failed.";
  }
  return err instanceof Error ? err.message : "Application update failed.";
}

export function getUpdateRepo(): string {
  const configured = (process.env.RADIOPLANNER_UPDATE_REPO || "").trim();
  if (configured && REPO_SLUG_RE.test(configured)) {
    return configured;
  }
  return DEFAULT_UPDATE_REPO;
}

export function detectInstallMode(projectDir: string = process.cwd()): InstallMode {
  const override = (process.env.RADIOPLANNER_INSTALL_MODE || "").trim().toLowerCase();
  if (override === "standalone" || override === "git" || override === "source") {
    return override;
  }
  const execBase = path.basename(process.execPath || "").toLowerCase();
  const isElectronDevBinary = execBase === "electron" || execBase === "electron.exe" || execBase === "node" || execBase === "node.exe";
  if (
    Boolean(process.env.APPIMAGE) ||
    (!isElectronDevBinary && !(process as NodeJS.Process & { defaultApp?: boolean }).defaultApp)
  ) {
    return "standalone";
  }
  if (fs.existsSync(path.join(projectDir, ".git"))) {
    return "git";
  }
  return "source";
}

export function parseSemver(raw: string): [number, number, number] {
  const m = SEMVER_RE.exec(String(raw || "").trim());
  if (!m) return [0, 0, 0];
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

export function isNewerVersion(latest: string, current: string): boolean {
  const [lMaj, lMin, lPat] = parseSemver(latest);
  const [cMaj, cMin, cPat] = parseSemver(current);
  if (lMaj === 0 && lMin === 0 && lPat === 0) return false;
  if (lMaj !== cMaj) return lMaj > cMaj;
  if (lMin !== cMin) return lMin > cMin;
  return lPat > cPat;
}

export function validateDownloadUrl(rawUrl: string): string {
  const cleaned = String(rawUrl || "").trim();
  let parsed: URL;
  try {
    parsed = new URL(cleaned);
  } catch {
    throw new UpdateError("untrusted_url");
  }
  const host = (parsed.hostname || "").toLowerCase();
  if (parsed.protocol !== "https:" || !ALLOWED_DOWNLOAD_HOSTS.has(host)) {
    throw new UpdateError("untrusted_url");
  }
  return cleaned;
}

export interface ReleaseAssetItem {
  name?: string;
  browser_download_url?: string;
  size?: number;
}

export function selectReleaseAsset(
  assets: ReleaseAssetItem[],
  platformName: string = process.platform,
): { asset: ReleaseAssetItem | null; checksum: ReleaseAssetItem | null } {
  const plat = (platformName || process.platform).toLowerCase();
  let checksum: ReleaseAssetItem | null = null;
  let installerMatch: ReleaseAssetItem | null = null;
  let zipFallback: ReleaseAssetItem | null = null;

  for (const item of assets) {
    if (!item || typeof item !== "object") continue;
    const name = String(item.name || "").trim();
    const low = name.toLowerCase();
    if (low === "sha256sums.txt") {
      checksum = item;
      continue;
    }
    if (plat === "win32") {
      if (low.endsWith(".exe")) {
        installerMatch = item;
      } else if (low.endsWith(".zip") && (low.includes("win") || low.includes("windows"))) {
        zipFallback = item;
      }
    } else if (plat === "linux") {
      if (low.endsWith(".appimage")) {
        installerMatch = item;
      } else if (low.endsWith(".zip") && low.includes("linux")) {
        zipFallback = item;
      }
    } else if (plat === "darwin") {
      if (low.endsWith(".dmg")) {
        installerMatch = item;
      } else if (low.endsWith(".zip") && (low.includes("mac") || low.includes("darwin"))) {
        zipFallback = item;
      }
    }
  }

  return {
    asset: installerMatch ?? zipFallback,
    checksum,
  };
}

export function parseSha256Sums(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of String(text || "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const m = /^([0-9a-fA-F]{64})\s+\*?(.+)$/.exec(line);
    if (!m) continue;
    const digest = m[1].toLowerCase();
    const filePart = m[2].trim().replace(/\\/g, "/");
    const baseName = path.posix.basename(filePart);
    if (SHA256_HEX_RE.test(digest) && baseName) {
      out[baseName] = digest;
    }
  }
  return out;
}

export function verifySha256(filePath: string, expectedHex: string): boolean {
  const expected = String(expectedHex || "").trim().toLowerCase();
  if (!SHA256_HEX_RE.test(expected) || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return false;
  }
  const hasher = crypto.createHash("sha256");
  const buf = fs.readFileSync(filePath);
  hasher.update(buf);
  return hasher.digest("hex").toLowerCase() === expected;
}

export async function createPreUpdateBackup(workspace: WebWorkspace, appVersion: string): Promise<string | null> {
  try {
    fs.mkdirSync(workspace.baseDir, { recursive: true });
    const zipBytes = await createConfigBackupZipBytes(workspace, {
      includeTokens: true,
      appVersion,
    });
    const backupPath = path.join(workspace.baseDir, "radioplanner.pre_update.bak");
    fs.writeFileSync(backupPath, zipBytes);
    return backupPath;
  } catch {
    return null;
  }
}

export interface UpdateCheckResult {
  online: boolean;
  repo: string;
  install_mode: InstallMode;
  current_version: string;
  latest_version: string;
  update_available: boolean;
  can_self_update: boolean;
  release_name: string;
  release_url: string;
  published_at: string;
  release_notes: string;
  asset_name: string;
  asset_url: string;
  checksum_url: string;
  message: string;
}

export async function checkForUpdate(opts: {
  currentVersion: string;
  projectDir?: string;
  offlineOnly?: boolean;
  repo?: string;
  platformName?: string;
  fetchFn?: typeof fetch;
}): Promise<UpdateCheckResult> {
  const targetRepo = opts.repo && REPO_SLUG_RE.test(opts.repo) ? opts.repo : getUpdateRepo();
  const installMode = detectInstallMode(opts.projectDir);
  const releasesUrl = `https://github.com/${targetRepo}/releases`;
  const apiUrl = `https://api.github.com/repos/${targetRepo}/releases/latest`;

  const baseResp: UpdateCheckResult = {
    online: false,
    repo: targetRepo,
    install_mode: installMode,
    current_version: opts.currentVersion,
    latest_version: opts.currentVersion,
    update_available: false,
    can_self_update: false,
    release_name: "",
    release_url: releasesUrl,
    published_at: "",
    release_notes: "",
    asset_name: "",
    asset_url: "",
    checksum_url: "",
    message: "",
  };

  if (opts.offlineOnly) {
    baseResp.message = "Offline mode — update check skipped.";
    return baseResp;
  }

  const doFetch = opts.fetchFn ?? fetch;
  let data: Record<string, unknown>;
  try {
    const res = await doFetch(apiUrl, {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": `W5CDN-RadioPlanner/${opts.currentVersion}`,
      },
      signal: AbortSignal.timeout(6000),
    });
    if (res.status === 404) {
      baseResp.online = true;
      baseResp.message = "Connected to GitHub, but no formal release tags (v*) have been published yet.";
      return baseResp;
    }
    if (!res.ok) {
      baseResp.message = `Release check returned HTTP ${res.status}.`;
      return baseResp;
    }
    data = (await res.json()) as Record<string, unknown>;
  } catch {
    baseResp.message = "Could not reach GitHub Releases (offline or rate-limited).";
    return baseResp;
  }

  const tag = String(data.tag_name ?? "").trim();
  const latestClean = tag.replace(/^[vV]/, "") || opts.currentVersion;
  const rawHtmlUrl = sanitizeHttpUrl(data.html_url) ?? releasesUrl;
  const releaseUrl = rawHtmlUrl.startsWith("https://github.com/") ? rawHtmlUrl : releasesUrl;

  const assets = Array.isArray(data.assets) ? (data.assets as ReleaseAssetItem[]) : [];
  const { asset, checksum } = selectReleaseAsset(assets, opts.platformName);
  const assetName = String(asset?.name ?? "").trim();
  const assetUrl = String(asset?.browser_download_url ?? "").trim();
  const checksumUrl = String(checksum?.browser_download_url ?? "").trim();

  const updateAvail = isNewerVersion(tag, opts.currentVersion);
  const hasVerifiedAsset = Boolean(assetUrl && checksumUrl);
  const canSelfUpdate = hasVerifiedAsset || installMode === "git";

  const msg = updateAvail
    ? `Version v${latestClean} is available (currently running v${opts.currentVersion}).`
    : `W5CDN RadioPlanner v${opts.currentVersion} is up to date.`;

  return {
    online: true,
    repo: targetRepo,
    install_mode: installMode,
    current_version: opts.currentVersion,
    latest_version: latestClean,
    update_available: updateAvail,
    can_self_update: canSelfUpdate,
    release_name: String(data.name || tag || latestClean).slice(0, 120),
    release_url: releaseUrl,
    published_at: String(data.published_at || "").slice(0, 40),
    release_notes: String(data.body || "").trim().slice(0, 4000),
    asset_name: assetName,
    asset_url: assetUrl,
    checksum_url: checksumUrl,
    message: msg,
  };
}

function writeStandaloneHelperScript(opts: {
  stagingRoot: string;
  installerPath: string;
  pid: number;
  platformName?: string;
}): string {
  const plat = (opts.platformName || process.platform).toLowerCase();
  if (plat === "win32") {
    const scriptPath = path.join(opts.stagingRoot, "_apply_update.bat");
    const scriptText = [
      "@echo off",
      "setlocal",
      `set "TARGET_PID=${opts.pid}"`,
      `set "INSTALLER_PATH=${opts.installerPath}"`,
      ":wait_exit",
      'tasklist /FI "PID eq %TARGET_PID%" 2>NUL | find /I "%TARGET_PID%" >NUL',
      "if not errorlevel 1 (",
      "  timeout /t 1 /nobreak >NUL",
      "  goto wait_exit",
      ")",
      'start "" "%INSTALLER_PATH%"',
      "endlocal",
      "",
    ].join("\r\n");
    fs.writeFileSync(scriptPath, scriptText, "utf-8");
    return scriptPath;
  }

  const scriptPath = path.join(opts.stagingRoot, "_apply_update.sh");
  const currentAppImage = (process.env.APPIMAGE || "").trim();
  const scriptLines = [
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    `TARGET_PID=${opts.pid}`,
    `NEW_PKG="${opts.installerPath}"`,
    'while kill -0 "$TARGET_PID" 2>/dev/null; do sleep 0.5; done',
    'chmod +x "$NEW_PKG" 2>/dev/null || true',
  ];
  if (currentAppImage) {
    scriptLines.push(
      `cp -f "$NEW_PKG" "${currentAppImage}"`,
      `chmod +x "${currentAppImage}"`,
      `nohup "${currentAppImage}" >/dev/null 2>&1 &`,
    );
  } else {
    scriptLines.push('nohup "$NEW_PKG" >/dev/null 2>&1 &');
  }
  scriptLines.push("");
  fs.writeFileSync(scriptPath, scriptLines.join("\n"), { encoding: "utf-8", mode: 0o700 });
  return scriptPath;
}

export async function applyStandaloneUpdate(opts: {
  workspace: WebWorkspace;
  currentVersion: string;
  assetName: string;
  assetUrl: string;
  checksumUrl: string;
  platformName?: string;
  fetchFn?: typeof fetch;
  spawnHelper?: boolean;
  onRestartRequested?: () => void;
}): Promise<Record<string, unknown>> {
  const safeAssetUrl = validateDownloadUrl(opts.assetUrl);
  const safeChecksumUrl = validateDownloadUrl(opts.checksumUrl);
  const cleanAssetName = path.basename(String(opts.assetName || "").trim());
  const lowName = cleanAssetName.toLowerCase();

  if (
    !cleanAssetName ||
    !(lowName.endsWith(".exe") || lowName.endsWith(".appimage") || lowName.endsWith(".zip") || lowName.endsWith(".dmg")) ||
    cleanAssetName.includes("/") ||
    cleanAssetName.includes("\\") ||
    cleanAssetName.includes("..")
  ) {
    throw new UpdateError("archive_invalid_name");
  }

  const stagingRoot = path.join(opts.workspace.baseDir, "_update_staging");
  fs.mkdirSync(stagingRoot, { recursive: true });
  const stagingAbs = path.resolve(stagingRoot);
  const archivePath = path.resolve(stagingAbs, cleanAssetName);
  if (!archivePath.startsWith(stagingAbs + path.sep)) {
    throw new UpdateError("archive_invalid_name");
  }

  const doFetch = opts.fetchFn ?? fetch;

  // 1. Download and parse SHA256SUMS.txt
  let checksumText: string;
  try {
    const sumResp = await doFetch(safeChecksumUrl, {
      headers: { "User-Agent": `W5CDN-RadioPlanner/${opts.currentVersion}` },
      signal: AbortSignal.timeout(20000),
    });
    if (!sumResp.ok) throw new Error(`HTTP ${sumResp.status}`);
    checksumText = await sumResp.text();
  } catch {
    throw new UpdateError("download_failed");
  }

  const checksums = parseSha256Sums(checksumText);
  const expectedHash = checksums[cleanAssetName];
  if (!expectedHash) {
    throw new UpdateError("checksum_missing");
  }

  // 2. Download release installer/package with strict size cap
  try {
    const pkgResp = await doFetch(safeAssetUrl, {
      headers: { "User-Agent": `W5CDN-RadioPlanner/${opts.currentVersion}` },
      signal: AbortSignal.timeout(180000),
    });
    if (!pkgResp.ok) throw new Error(`HTTP ${pkgResp.status}`);
    const arrBuf = await pkgResp.arrayBuffer();
    if (arrBuf.byteLength > MAX_UPDATE_ARCHIVE_BYTES) {
      throw new UpdateError("download_too_large");
    }
    fs.writeFileSync(archivePath, Buffer.from(arrBuf));
  } catch (err) {
    if (err instanceof UpdateError) throw err;
    throw new UpdateError("download_failed");
  }

  // 3. Verify SHA-256 integrity before creating backup or launching installer
  if (!verifySha256(archivePath, expectedHash)) {
    try {
      fs.unlinkSync(archivePath);
    } catch {
      // ignore
    }
    throw new UpdateError("checksum_mismatch");
  }

  // 4. Create pre-update configuration snapshot (`radioplanner.pre_update.bak`)
  const backupPath = await createPreUpdateBackup(opts.workspace, opts.currentVersion);

  // 5. Write & launch detached OS installer helper script
  const helperScript = writeStandaloneHelperScript({
    stagingRoot: stagingAbs,
    installerPath: archivePath,
    pid: process.pid,
    platformName: opts.platformName,
  });

  if (opts.spawnHelper !== false) {
    const plat = (opts.platformName || process.platform).toLowerCase();
    if (plat === "win32") {
      const child = spawn("cmd.exe", ["/c", helperScript], {
        detached: true,
        stdio: "ignore",
        windowsHide: true,
      });
      child.unref();
    } else {
      const child = spawn("/bin/bash", [helperScript], {
        detached: true,
        stdio: "ignore",
      });
      child.unref();
    }
    if (opts.onRestartRequested) {
      setTimeout(() => opts.onRestartRequested?.(), 400);
    }
  }

  return {
    ok: true,
    mode: "standalone",
    restart_required: true,
    backup_created: backupPath !== null,
    installer_path: archivePath,
    helper_script: helperScript,
    message:
      "Update verified (SHA-256 OK) and staged. W5CDN RadioPlanner is closing to launch the update installer.",
  };
}

function runGitCmd(args: string[], cwd: string): { status: number; stdout: string; stderr: string } {
  const res = spawnSync("git", args, {
    cwd,
    encoding: "utf-8",
    timeout: 60000,
    windowsHide: true,
  });
  if (res.error) {
    return { status: -1, stdout: "", stderr: res.error.message };
  }
  return {
    status: res.status ?? 1,
    stdout: String(res.stdout || ""),
    stderr: String(res.stderr || ""),
  };
}

export async function applyGitUpdate(opts: {
  workspace: WebWorkspace;
  currentVersion: string;
  projectDir?: string;
}): Promise<Record<string, unknown>> {
  const cwd = opts.projectDir || process.cwd();
  const verCheck = runGitCmd(["--version"], cwd);
  if (verCheck.status !== 0) {
    throw new UpdateError("git_missing");
  }

  const branchProc = runGitCmd(["rev-parse", "--abbrev-ref", "HEAD"], cwd);
  if (branchProc.status !== 0) {
    throw new UpdateError("git_branch_unknown");
  }
  const branch = branchProc.stdout.trim();
  if (branch !== "main" && branch !== "master") {
    throw new UpdateError("git_non_main");
  }

  const statusProc = runGitCmd(["status", "--porcelain"], cwd);
  if (statusProc.status !== 0) {
    throw new UpdateError("git_status_failed");
  }
  if (statusProc.stdout.trim().length > 0) {
    throw new UpdateError("git_dirty");
  }

  const backupPath = await createPreUpdateBackup(opts.workspace, opts.currentVersion);

  const fetchProc = runGitCmd(["fetch", "origin", "--tags"], cwd);
  if (fetchProc.status !== 0) {
    throw new UpdateError("git_fetch_failed");
  }

  const pullProc = runGitCmd(["pull", "--ff-only", "origin", branch], cwd);
  if (pullProc.status !== 0) {
    throw new UpdateError("git_pull_failed");
  }

  return {
    ok: true,
    mode: "git",
    branch,
    restart_required: true,
    backup_created: backupPath !== null,
    message: `Updated Git branch '${branch}' from origin. Restart W5CDN RadioPlanner to load the new version.`,
  };
}
