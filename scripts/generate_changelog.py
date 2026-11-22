"""Generate categorized Markdown release notes and CHANGELOG.md from Conventional Commits."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<desc>.+)$"
)

SECTION_ORDER: list[tuple[str, str]] = [
    ("breaking", "Breaking Changes"),
    ("feat", "Features"),
    ("fix", "Bug Fixes"),
    ("security", "Security & Hardening"),
    ("perf", "Performance & Refactoring"),
    ("docs", "Testing, CI & Documentation"),
    ("other", "Other Changes"),
]

TYPE_TO_SECTION: dict[str, str] = {
    "feat": "feat",
    "fix": "fix",
    "security": "security",
    "sec": "security",
    "perf": "perf",
    "refactor": "perf",
    "docs": "docs",
    "test": "docs",
    "ci": "docs",
    "build": "docs",
    "style": "perf",
    "chore": "other",
}


@dataclass(frozen=True)
class CommitEntry:
    sha: str
    subject: str
    body: str = ""


def _run_git(args: list[str], cwd: Path) -> str:
    git_bin = shutil.which("git")
    if not git_bin:
        raise RuntimeError("git is not installed or not on PATH.")
    proc = subprocess.run(  # nosec B603
        [git_bin, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def find_previous_tag(current_ref: str, cwd: Path) -> str | None:
    """Return the most recent v* tag reachable before current_ref, or None."""
    out = _run_git(
        ["describe", "--tags", "--abbrev=0", "--match", "v*", f"{current_ref}^"],
        cwd=cwd,
    ).strip()
    return out or None


def collect_commits(from_ref: str | None, to_ref: str, cwd: Path) -> list[CommitEntry]:
    """Collect non-merge commits in (from_ref..to_ref] (or all commits up to to_ref)."""
    rev_range = f"{from_ref}..{to_ref}" if from_ref else to_ref
    raw = _run_git(
        ["log", "--no-merges", "--format=%h%x1f%s%x1f%b%x1e", rev_range],
        cwd=cwd,
    )
    entries: list[CommitEntry] = []
    for record in raw.split("\x1e"):
        rec = record.strip()
        if not rec:
            continue
        parts = rec.split("\x1f")
        sha = parts[0].strip()
        subject = parts[1].strip() if len(parts) > 1 else ""
        body = parts[2].strip() if len(parts) > 2 else ""
        if sha and subject:
            entries.append(CommitEntry(sha=sha, subject=subject, body=body))
    return entries


def format_release_notes(
    *,
    version: str,
    commits: list[CommitEntry],
    repo: str = "",
    release_date: str | None = None,
) -> str:
    """Render categorized Markdown release notes from a list of CommitEntry objects."""
    date_str = release_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    buckets: dict[str, list[str]] = {key: [] for key, _ in SECTION_ORDER}

    for entry in commits:
        m = CONVENTIONAL_RE.match(entry.subject)
        sha_link = (
            f"[`{entry.sha}`](https://github.com/{repo}/commit/{entry.sha})"
            if repo
            else f"`{entry.sha}`"
        )
        if m:
            ctype = m.group("type").lower()
            scope = (m.group("scope") or "").strip()
            breaking = bool(m.group("breaking")) or ("BREAKING CHANGE:" in entry.body)
            desc = m.group("desc").strip()
            prefix = f"**{scope}:** " if scope else ""
            bullet = f"- {prefix}{desc} ({sha_link})"
            section = "breaking" if breaking else TYPE_TO_SECTION.get(ctype, "other")
        else:
            bullet = f"- {entry.subject} ({sha_link})"
            section = "other"
        buckets[section].append(bullet)

    lines = [f"## {version} ({date_str})", ""]
    has_items = False
    for key, title in SECTION_ORDER:
        items = buckets[key]
        if not items:
            continue
        has_items = True
        lines.append(f"### {title}")
        lines.extend(items)
        lines.append("")

    if not has_items:
        lines.append("- Maintenance release with no user-facing commit changes.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate release changelog from Conventional Commits.")
    parser.add_argument("--version", required=True, help="Release tag or version label (e.g. v0.2.0)")
    parser.add_argument("--to-ref", default="HEAD", help="Git ref to end changelog at (default: HEAD)")
    parser.add_argument("--from-ref", default="", help="Optional starting Git ref (auto-detects previous v* tag)")
    parser.add_argument("--repo", default="", help="Optional owner/repo slug for commit links")
    parser.add_argument("--output", default="", help="Optional path to write generated Markdown")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    prev_tag = args.from_ref.strip() or find_previous_tag(args.to_ref, repo_root)
    commits = collect_commits(prev_tag, args.to_ref, repo_root)
    markdown = format_release_notes(version=args.version, commits=commits, repo=args.repo.strip())

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8", newline="\n")
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
