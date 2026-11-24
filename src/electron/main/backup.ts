/**
 * Configuration Backup & Restore Archive Manager (ZIP with Zip-Slip, size, and YAML validation).
 */

import fs from "node:fs";
import path from "node:path";
import JSZip from "jszip";
import { utcNowIso } from "../shared/sanitize";
import { ApiError } from "../shared/types";
import { parseYamlText } from "../shared/yamlDiagnostics";
import {
  getPreferencesFile,
  getTokensFile,
  getUserRadiosDir,
  getUserRecipesDir,
  getUserTemplatesDir,
} from "./paths";
import { WebWorkspace } from "./workspace";

export const MAX_BACKUP_UPLOAD_BYTES = 50 * 1024 * 1024;
export const MAX_BACKUP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024;
export const MAX_BACKUP_FILES = 5000;
const WINDOWS_ABS_RE = /^[A-Za-z]:[\\/]|^\\\\/;

export async function createConfigBackupZipBytes(
  workspace: WebWorkspace,
  opts?: { includeTokens?: boolean; appVersion?: string },
): Promise<Buffer> {
  const includeTokens = Boolean(opts?.includeTokens);
  const zip = new JSZip();

  const manifest = {
    app: "W5CDN RadioPlanner",
    version: opts?.appVersion ?? "0.2.0",
    exported_at: utcNowIso(),
    include_tokens: includeTokens,
  };
  zip.file("manifest.json", `${JSON.stringify(manifest, null, 2)}\n`);

  const prefsFile = getPreferencesFile(workspace.baseDir);
  if (fs.existsSync(prefsFile)) {
    zip.file("preferences.yaml", fs.readFileSync(prefsFile));
  }

  if (includeTokens) {
    const tokensFile = getTokensFile(workspace.baseDir);
    if (fs.existsSync(tokensFile)) {
      zip.file("tokens", fs.readFileSync(tokensFile));
    }
  }

  const folders: Array<[string, string]> = [
    ["recipes", getUserRecipesDir(workspace.baseDir)],
    ["radios", getUserRadiosDir(workspace.baseDir)],
    ["templates", getUserTemplatesDir(workspace.baseDir)],
  ];

  for (const [folderName, folderPath] of folders) {
    if (!fs.existsSync(folderPath)) continue;
    const files = fs
      .readdirSync(folderPath)
      .filter((f) => f.toLowerCase().endsWith(".yaml") || f.toLowerCase().endsWith(".yml"))
      .sort();
    for (const file of files) {
      const fullPath = path.join(folderPath, file);
      if (fs.statSync(fullPath).isFile()) {
        zip.file(`${folderName}/${file}`, fs.readFileSync(fullPath));
      }
    }
  }

  return zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}

export async function restoreConfigBackupZipBytes(
  workspace: WebWorkspace,
  rawBytes: Buffer,
): Promise<{
  restored: boolean;
  count: number;
  files: string[];
  backup_saved: string;
  message: string;
}> {
  if (!rawBytes || rawBytes.length === 0) {
    throw new ApiError(400, "Empty backup upload.");
  }
  if (rawBytes.length > MAX_BACKUP_UPLOAD_BYTES) {
    throw new ApiError(413, "Backup archive exceeds 50 MB upload limit.");
  }

  let zip: JSZip;
  try {
    zip = await JSZip.loadAsync(rawBytes);
  } catch {
    throw new ApiError(400, "Uploaded file is not a valid ZIP archive.");
  }

  const entries = Object.values(zip.files);
  if (entries.length > MAX_BACKUP_FILES) {
    throw new ApiError(400, "Backup archive contains too many files.");
  }

  const allowedSubdirs = new Set(["recipes", "radios", "templates"]);
  const validatedFiles: Array<{ relNorm: string; content: Buffer }> = [];
  let totalUncompressed = 0;

  for (const entry of entries) {
    const name = entry.name;
    if (
      name.startsWith("/") ||
      name.startsWith("\\") ||
      name.split(/[\\/]+/).includes("..") ||
      WINDOWS_ABS_RE.test(name)
    ) {
      throw new ApiError(400, "Backup archive contains an unsafe path.");
    }
    if (entry.dir) continue;

    const norm = name.replace(/\\/g, "/");
    if (norm === "manifest.json") continue;

    const parts = norm.split("/");
    const isRootYaml = norm === "preferences.yaml" || norm === "tokens";
    const isSubdirYaml =
      parts.length === 2 &&
      allowedSubdirs.has(parts[0]) &&
      (parts[1].toLowerCase().endsWith(".yaml") || parts[1].toLowerCase().endsWith(".yml"));

    if (!isRootYaml && !isSubdirYaml) continue;

    const content = await entry.async("nodebuffer");
    totalUncompressed += content.length;
    if (totalUncompressed > MAX_BACKUP_UNCOMPRESSED_BYTES) {
      throw new ApiError(400, "Backup archive exceeds 100 MB uncompressed limit.");
    }

    try {
      parseYamlText(content.toString("utf-8"), norm);
    } catch (err) {
      throw new ApiError(400, `Invalid YAML in ${norm}: ${err instanceof Error ? err.message : String(err)}`);
    }
    validatedFiles.push({ relNorm: norm, content });
  }

  if (validatedFiles.length === 0) {
    throw new ApiError(400, "Backup archive contained no restorable RadioPlanner files.");
  }

  fs.mkdirSync(workspace.baseDir, { recursive: true });
  const preRestoreName = "radioplanner.pre_restore.bak";
  const preRestorePath = path.join(workspace.baseDir, preRestoreName);
  const preRestoreBuf = await createConfigBackupZipBytes(workspace, { includeTokens: false });
  fs.writeFileSync(preRestorePath, preRestoreBuf);

  const homeAbs = path.resolve(workspace.baseDir);
  const restoredNames: string[] = [];

  for (const { relNorm, content } of validatedFiles) {
    const destAbs = path.resolve(homeAbs, relNorm);
    if (!destAbs.startsWith(homeAbs + path.sep)) {
      throw new ApiError(400, "Backup archive entry escapes configuration directory.");
    }
    fs.mkdirSync(path.dirname(destAbs), { recursive: true });
    fs.writeFileSync(destAbs, content);
    if (relNorm === "tokens" && process.platform !== "win32") {
      try {
        fs.chmodSync(destAbs, 0o600);
      } catch {
        // Best effort
      }
    }
    restoredNames.push(relNorm);
  }

  workspace.reloadAll();
  return {
    restored: true,
    count: restoredNames.length,
    files: restoredNames,
    backup_saved: preRestoreName,
    message: `Restored ${restoredNames.length} configuration file(s). Pre-restore snapshot saved to ${preRestoreName}.`,
  };
}
