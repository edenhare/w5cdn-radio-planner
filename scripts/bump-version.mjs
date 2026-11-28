import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT_DIR = path.resolve(__dirname, "..");

const SEMVER_RE = /^(\d+)\.(\d+)\.(\d+)$/;
const PKG_VER_RE = /^(\s*"version"\s*:\s*")(\d+\.\d+\.\d+)(")/m;
const INDEX_TOP_PILL_RE = /(<span[^>]*id="rpVersionPill"[^>]*>v)(\d+\.\d+\.\d+)(<\/span>)/;
const INDEX_UPD_PILL_RE = /(<span[^>]*id="updateVersionPill"[^>]*>v)(\d+\.\d+\.\d+)(<\/span>)/;
const APP_JS_FALLBACK_RE = /(state\.appVersion\s*=\s*cfg\.version\s*\|\|\s*")(\d+\.\d+\.\d+)(")/;

export function parseSemver(raw) {
  const cleaned = String(raw || "").trim().replace(/^[vV]/, "");
  const m = SEMVER_RE.exec(cleaned);
  if (!m) throw new Error(`Invalid semantic version ${JSON.stringify(raw)}; expected X.Y.Z`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

export function computeNextVersion(current, bump) {
  const [maj, min, pat] = parseSemver(current);
  if (bump === "major") return `${maj + 1}.0.0`;
  if (bump === "minor") return `${maj}.${min + 1}.0`;
  if (bump === "patch") return `${maj}.${min}.${pat + 1}`;
  throw new Error(`Unsupported bump kind: ${bump}`);
}

function versionTargets(rootDir) {
  return [
    { file: path.join(rootDir, "package.json"), rules: [["package.json version", PKG_VER_RE]] },
    {
      file: path.join(rootDir, "src", "static", "index.html"),
      rules: [
        ["index.html rpVersionPill", INDEX_TOP_PILL_RE],
        ["index.html updateVersionPill", INDEX_UPD_PILL_RE],
      ],
    },
    {
      file: path.join(rootDir, "src", "static", "app.js"),
      rules: [["app.js fallback version", APP_JS_FALLBACK_RE]],
    },
  ];
}

export function readVersions(rootDir = ROOT_DIR) {
  const found = {};
  for (const target of versionTargets(rootDir)) {
    const text = fs.readFileSync(target.file, "utf-8");
    for (const [label, regex] of target.rules) {
      const m = regex.exec(text);
      if (!m) throw new Error(`Could not find ${label} in ${target.file}`);
      found[label] = m[2];
    }
  }
  const lockPath = path.join(rootDir, "package-lock.json");
  if (fs.existsSync(lockPath)) {
    const lock = JSON.parse(fs.readFileSync(lockPath, "utf-8"));
    if (lock.version) found["package-lock.json version"] = lock.version;
    if (lock.packages?.[""]?.version) found["package-lock.json packages[''].version"] = lock.packages[""].version;
  }
  return found;
}

export function checkVersionsConsistent(rootDir = ROOT_DIR) {
  const versions = readVersions(rootDir);
  const unique = new Set(Object.values(versions));
  if (unique.size !== 1) {
    const details = Object.entries(versions)
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    throw new Error(`Version mismatch across project files: ${details}`);
  }
  return [...unique][0];
}

export function applyVersion(newVersion, rootDir = ROOT_DIR, { dryRun = false } = {}) {
  const [maj, min, pat] = parseSemver(newVersion);
  const canonical = `${maj}.${min}.${pat}`;
  const updated = [];

  for (const target of versionTargets(rootDir)) {
    const original = fs.readFileSync(target.file, "utf-8");
    let content = original;
    for (const [label, regex] of target.rules) {
      let count = 0;
      content = content.replace(regex, (_full, g1, _g2, g3) => {
        count += 1;
        return `${g1}${canonical}${g3}`;
      });
      if (count !== 1) throw new Error(`Failed to update ${label} in ${target.file}`);
    }
    if (content !== original) {
      if (!dryRun) fs.writeFileSync(target.file, content, "utf-8");
      updated.push(target.file);
    }
  }

  const lockPath = path.join(rootDir, "package-lock.json");
  if (fs.existsSync(lockPath)) {
    const lock = JSON.parse(fs.readFileSync(lockPath, "utf-8"));
    let changed = false;
    if (lock.version !== canonical) {
      lock.version = canonical;
      changed = true;
    }
    if (lock.packages?.[""] && lock.packages[""].version !== canonical) {
      lock.packages[""].version = canonical;
      changed = true;
    }
    if (changed) {
      if (!dryRun) fs.writeFileSync(lockPath, `${JSON.stringify(lock, null, 2)}\n`, "utf-8");
      updated.push(lockPath);
    }
  }
  return updated;
}

function main(argv) {
  const args = argv.slice(2);
  const dryRun = args.includes("--dry-run");
  if (args.includes("--print-current") || args.includes("--check")) {
    console.log(checkVersionsConsistent(ROOT_DIR));
    return;
  }
  const bumpIdx = args.indexOf("--bump");
  const verIdx = args.indexOf("--version");
  const current = checkVersionsConsistent(ROOT_DIR);
  let target = "";
  if (verIdx !== -1 && args[verIdx + 1]) {
    const [a, b, c] = parseSemver(args[verIdx + 1]);
    target = `${a}.${b}.${c}`;
  } else if (bumpIdx !== -1 && args[bumpIdx + 1]) {
    target = computeNextVersion(current, args[bumpIdx + 1]);
  } else {
    throw new Error("Usage: node scripts/bump-version.mjs [--check | --print-current | --bump patch|minor|major | --version X.Y.Z]");
  }
  applyVersion(target, ROOT_DIR, { dryRun });
  console.log(target);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main(process.argv);
  } catch (err) {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
}
