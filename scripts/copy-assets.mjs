import fs from "node:fs";
import path from "node:path";

function copyDirRecursive(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDirRecursive(s, d);
    else if (entry.isFile()) fs.copyFileSync(s, d);
  }
}

const staticCandidates = [path.resolve("src", "static"), path.resolve("src", "web", "static")];
const staticSrc = staticCandidates.find((p) => fs.existsSync(p));
if (!staticSrc) throw new Error("Could not find static UI directory");
copyDirRecursive(staticSrc, path.resolve("dist", "static"));

const resSrc = path.resolve("src", "electron", "resources");
if (fs.existsSync(resSrc)) {
  copyDirRecursive(resSrc, path.resolve("dist", "resources"));
}
