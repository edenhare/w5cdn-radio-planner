import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const electronPkgDir = path.resolve("node_modules", "electron");
const distDir = path.join(electronPkgDir, "dist");
const pathTxt = path.join(electronPkgDir, "path.txt");
const expectedExe = process.platform === "win32" ? "electron.exe" : "electron";

function isReady() {
  return fs.existsSync(pathTxt) && fs.existsSync(path.join(distDir, expectedExe));
}

if (!isReady()) {
  const pkg = JSON.parse(fs.readFileSync(path.join(electronPkgDir, "package.json"), "utf-8"));
  const version = pkg.version;
  const plat = process.platform;
  const arch = process.arch;
  const zipName = `electron-v${version}-${plat}-${arch}.zip`;
  const cacheCandidates = [
    path.join(process.env.LOCALAPPDATA || "", "electron", "Cache"),
    path.join(process.env.HOME || process.env.USERPROFILE || "", ".cache", "electron"),
  ];
  let cachedZip = null;
  for (const base of cacheCandidates) {
    if (!base || !fs.existsSync(base)) continue;
    for (const entry of fs.readdirSync(base, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        const candidate = path.join(base, entry.name, zipName);
        if (fs.existsSync(candidate)) {
          cachedZip = candidate;
          break;
        }
      }
    }
    if (cachedZip) break;
  }

  if (cachedZip && process.platform === "win32") {
    fs.mkdirSync(distDir, { recursive: true });
    execFileSync("powershell.exe", [
      "-NoProfile",
      "-Command",
      `Expand-Archive -Path '${cachedZip}' -DestinationPath '${distDir}' -Force`,
    ], { stdio: "inherit" });
    fs.writeFileSync(pathTxt, expectedExe, "utf-8");
  } else {
    execFileSync(process.execPath, [path.join(electronPkgDir, "install.js")], { stdio: "inherit" });
    if (!fs.existsSync(pathTxt) && fs.existsSync(path.join(distDir, expectedExe))) {
      fs.writeFileSync(pathTxt, expectedExe, "utf-8");
    }
  }
  if (!isReady()) {
    throw new Error(`Electron binary not available at ${path.join(distDir, expectedExe)}`);
  }
}
