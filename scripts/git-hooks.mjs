import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const BLOCKED_PATH_RE =
  /(^|\/)(\.env|tokens|session\.json|desktop_startup\.log|update\.log)$|\.(db|db-wal|db-shm|bak)$|(^|\/)(exports|scratch)\//i;
const PRIVATE_KEY_RE = /-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----/;
const MERGE_CONFLICT_RE = /^(<{7} |={7}$|>{7} )/m;
const LF_ONLY_RE = /^(start\.sh|scripts\/install_linux_desktop\.sh|\.github\/.*\.ya?ml|\.husky\/[^/]+)$/;
const CONVENTIONAL_RE =
  /^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: .+/;
const MAIN_CODE_RE =
  /^(src\/(electron|static)\/.*|tests\/electron\/.*|scripts\/.*\.mjs|package\.json|tsconfig\.json|vitest\.config\.mts)$/;
const MAX_FILE_BYTES = 1000 * 1024;

function runNpm(args, opts = {}) {
  const npmCli = path.join(path.dirname(process.execPath), "node_modules", "npm", "bin", "npm-cli.js");
  const cmd = process.platform === "win32" && fs.existsSync(npmCli) ? process.execPath : "npm";
  const finalArgs = cmd === process.execPath ? [npmCli, ...args] : args;
  runCmd(cmd, finalArgs, opts);
}

function runCmd(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, {
    stdio: "inherit",
    ...opts,
  });
  if (res.error) throw res.error;
  if (res.status !== 0) {
    process.exit(res.status ?? 1);
  }
}

export function validateCommitMessage(rawMessage) {
  const firstLine = String(rawMessage || "").split(/\r?\n/)[0].trim();
  if (CONVENTIONAL_RE.test(firstLine) || firstLine.startsWith("Merge ") || firstLine.startsWith("Revert ")) {
    return { ok: true, firstLine };
  }
  return {
    ok: false,
    firstLine,
    error: `Commit message must follow Conventional Commits (e.g. feat(ui): ... or fix: ...). Got: ${firstLine}`,
  };
}

export function validateStagedFiles(files, rootDir = process.cwd()) {
  const errors = [];
  for (const relRaw of files) {
    const rel = relRaw.replace(/\\/g, "/");
    if (BLOCKED_PATH_RE.test(rel)) {
      errors.push(`Blocked sensitive/runtime file: ${rel}`);
      continue;
    }
    const abs = path.resolve(rootDir, rel);
    if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) continue;

    const stat = fs.statSync(abs);
    if (stat.size > MAX_FILE_BYTES) {
      errors.push(`File exceeds 1000 KB limit (${Math.round(stat.size / 1024)} KB): ${rel}`);
    }

    const buf = fs.readFileSync(abs);
    if (buf.includes(0)) continue;
    const text = buf.toString("utf-8");

    if (rel !== "scripts/git-hooks.mjs" && PRIVATE_KEY_RE.test(text)) {
      errors.push(`Private key detected in staged file: ${rel}`);
    }
    if (rel !== "scripts/git-hooks.mjs" && MERGE_CONFLICT_RE.test(text)) {
      errors.push(`Merge conflict markers detected in: ${rel}`);
    }
    if (rel.endsWith(".json")) {
      try {
        JSON.parse(text);
      } catch (err) {
        errors.push(`Invalid JSON in ${rel}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
    if (LF_ONLY_RE.test(rel) && text.includes("\r\n")) {
      errors.push(`CRLF line endings not allowed in ${rel} (use LF)`);
    }
  }
  return errors;
}

function getStagedFiles() {
  const out = execFileSync("git", ["diff", "--cached", "--name-only", "--diff-filter=ACMR"], {
    encoding: "utf-8",
  });
  return out
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function runPreCommit() {
  const staged = getStagedFiles();
  const errors = validateStagedFiles(staged);
  if (errors.length > 0) {
    for (const err of errors) console.error(`[husky:pre-commit] ERROR: ${err}`);
    process.exit(1);
  }

  if (staged.some((f) => MAIN_CODE_RE.test(f)) && fs.existsSync("node_modules")) {
    runNpm(["run", "typecheck"]);
    runNpm(["test"]);
  }
}

function runCommitMsg(msgFile) {
  if (!msgFile || !fs.existsSync(msgFile)) {
    console.error("[husky:commit-msg] ERROR: Missing commit message file path");
    process.exit(1);
  }
  const raw = fs.readFileSync(msgFile, "utf-8");
  const check = validateCommitMessage(raw);
  if (!check.ok) {
    console.error(`[husky:commit-msg] ERROR: ${check.error}`);
    process.exit(1);
  }
}

function runPrePush() {
  runCmd(process.execPath, ["scripts/bump-version.mjs", "--check"]);
  runNpm(["run", "typecheck"]);
  runNpm(["run", "test:cov"]);
}

function main() {
  const hook = process.argv[2];
  if (hook === "pre-commit") {
    runPreCommit();
  } else if (hook === "commit-msg") {
    runCommitMsg(process.argv[3]);
  } else if (hook === "pre-push") {
    runPrePush();
  } else {
    console.error("Usage: node scripts/git-hooks.mjs <pre-commit|commit-msg|pre-push> [args]");
    process.exit(2);
  }
}

const isEntrypoint = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isEntrypoint) {
  main();
}
