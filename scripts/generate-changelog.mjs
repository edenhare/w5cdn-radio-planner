import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CONVENTIONAL_RE = /^(?<type>[a-z]+)(?:\((?<scope>[^)]+)\))?(?<breaking>!)?:\s*(?<desc>.+)$/;

const SECTION_ORDER = [
  ["breaking", "Breaking Changes"],
  ["feat", "Features"],
  ["fix", "Bug Fixes"],
  ["security", "Security & Hardening"],
  ["perf", "Performance & Refactoring"],
  ["docs", "Testing, CI & Documentation"],
  ["other", "Other Changes"],
];

const TYPE_TO_SECTION = {
  feat: "feat",
  fix: "fix",
  security: "security",
  sec: "security",
  perf: "perf",
  refactor: "perf",
  docs: "docs",
  test: "docs",
  ci: "docs",
  build: "docs",
  style: "perf",
  chore: "other",
};

function runGit(args, cwd) {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"] });
  } catch {
    return "";
  }
}

export function findPreviousTag(currentRef, cwd) {
  const out = runGit(["describe", "--tags", "--abbrev=0", "--match", "v*", `${currentRef}^`], cwd).trim();
  return out || null;
}

export function collectCommits(fromRef, toRef, cwd) {
  const revRange = fromRef ? `${fromRef}..${toRef}` : toRef;
  const raw = runGit(["log", "--no-merges", "--format=%h%x1f%s%x1f%b%x1e", revRange], cwd);
  const entries = [];
  for (const record of raw.split("\x1e")) {
    const rec = record.trim();
    if (!rec) continue;
    const [sha = "", subject = "", body = ""] = rec.split("\x1f");
    if (sha.trim() && subject.trim()) {
      entries.push({ sha: sha.trim(), subject: subject.trim(), body: body.trim() });
    }
  }
  return entries;
}

export function formatReleaseNotes({ version, commits, repo = "", releaseDate = null }) {
  const dateStr = releaseDate || new Date().toISOString().slice(0, 10);
  const buckets = Object.fromEntries(SECTION_ORDER.map(([k]) => [k, []]));

  for (const entry of commits) {
    const m = CONVENTIONAL_RE.exec(entry.subject);
    const shaLink = repo ? `[\`${entry.sha}\`](https://github.com/${repo}/commit/${entry.sha})` : `\`${entry.sha}\``;
    if (m?.groups) {
      const ctype = m.groups.type.toLowerCase();
      const scope = (m.groups.scope || "").trim();
      const breaking = Boolean(m.groups.breaking) || entry.body.includes("BREAKING CHANGE:");
      const desc = m.groups.desc.trim();
      const prefix = scope ? `**${scope}:** ` : "";
      const section = breaking ? "breaking" : TYPE_TO_SECTION[ctype] || "other";
      buckets[section].push(`- ${prefix}${desc} (${shaLink})`);
    } else {
      buckets.other.push(`- ${entry.subject} (${shaLink})`);
    }
  }

  const lines = [`## ${version} (${dateStr})`, ""];
  let anySection = false;
  for (const [key, title] of SECTION_ORDER) {
    if (buckets[key].length) {
      anySection = true;
      lines.push(`### ${title}`, "", ...buckets[key], "");
    }
  }
  if (!anySection) {
    lines.push("- Maintenance release.", "");
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

function main(argv) {
  const args = argv.slice(2);
  const getOpt = (flag, fallback = "") => {
    const i = args.indexOf(flag);
    return i !== -1 && args[i + 1] ? args[i + 1] : fallback;
  };
  const version = getOpt("--version", "Unreleased");
  const repo = getOpt("--repo", "");
  const toRef = getOpt("--to", "HEAD");
  const fromRef = getOpt("--from", "") || findPreviousTag(toRef, process.cwd());
  const output = getOpt("--output", "");

  const commits = collectCommits(fromRef, toRef, process.cwd());
  const notes = formatReleaseNotes({ version, commits, repo });
  if (output) {
    fs.writeFileSync(path.resolve(output), notes, "utf-8");
  } else {
    process.stdout.write(notes);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv);
}
