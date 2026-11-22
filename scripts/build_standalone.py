"""Build a portable standalone bundle (.zip) of W5CDN RadioPlanner using PyInstaller.

Run on Windows to produce the Windows standalone package, or on Linux to produce
the Linux standalone package (suitable for local builds and GitHub Actions CI).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
WEB_DIR = SRC_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
RESOURCES_DIR = SRC_DIR / "core" / "resources"
APP_NAME = "W5CDN-RadioPlanner"


def _platform_tag() -> str:
    arch = platform.machine().lower() or "x64"
    if sys.platform == "win32":
        return f"windows-{arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def build_bundle() -> Path:
    dist_dir = ROOT_DIR / "dist"
    build_dir = ROOT_DIR / "build"
    target_dir = dist_dir / APP_NAME
    if target_dir.exists():
        shutil.rmtree(target_dir)

    data_sep = ";" if sys.platform == "win32" else ":"
    static_arg = f"{STATIC_DIR}{data_sep}static"
    radios_arg = f"{RESOURCES_DIR / 'radios'}{data_sep}core/resources/radios"
    templates_arg = f"{RESOURCES_DIR / 'templates'}{data_sep}core/resources/templates"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        APP_NAME,
        "--paths",
        str(SRC_DIR),
        "--add-data",
        static_arg,
        "--add-data",
        radios_arg,
        "--add-data",
        templates_arg,
        "--hidden-import",
        "web.app",
        "--hidden-import",
        "web.state",
        "--hidden-import",
        "web.security",
        "--hidden-import",
        "core.updater",
        "--hidden-import",
        "core.providers.callsign_lookup",
        "--hidden-import",
        "core.providers.nws",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(build_dir),
    ]

    if sys.platform == "win32":
        cmd.append("--windowed")
        ico = STATIC_DIR / "icon.ico"
        if ico.is_file():
            cmd.extend(["--icon", str(ico)])

    cmd.append(str(WEB_DIR / "desktop.py"))
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(ROOT_DIR))  # nosec B603

    for companion in ("README.md", "LICENSE"):
        src = ROOT_DIR / companion
        if src.is_file():
            shutil.copy2(src, target_dir / companion)

    if sys.platform.startswith("linux"):
        launcher = target_dir / "run-w5cdn-radio-planner.sh"
        launcher.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
            'cd "$SCRIPT_DIR"\n'
            "if [[ $# -eq 0 ]]; then\n"
            f'  exec "$SCRIPT_DIR/{APP_NAME}" --app-window\n'
            "else\n"
            f'  exec "$SCRIPT_DIR/{APP_NAME}" "$@"\n'
            "fi\n",
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(launcher, 0o755)  # nosec B103

    release_dir = ROOT_DIR / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    zip_path = release_dir / f"{APP_NAME}-{_platform_tag()}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(target_dir.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(dist_dir)
                zf.write(file_path, arcname=str(rel))

    print(f"Standalone bundle created: {zip_path}")
    return zip_path


if __name__ == "__main__":
    build_bundle()
