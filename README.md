# W5CDN RadioPlanner 📻

**W5CDN RadioPlanner** is an offline-first desktop studio, local web cockpit, and Python CLI for amateur radio operators, aviation enthusiasts, and GMRS users. It builds highway travel corridor repeater sequences, 5-ring radial proximity plans, and local aviation airband codeplugs, exporting hardware-constrained CSVs for **CHIRP**, **RT Systems**, and **Generic CSV** programmers.

---

## Key Features

### Offline Cockpit Studio & Desktop Shell
- **Native Desktop & Chromeless App Modes**: Runs as a native `pywebview` window on Windows/macOS, a chromeless `--app-window` on Linux/Windows, or in any local browser (`start.bat`, `start.sh`, `w5cdn-radio-planner`).
- **100% Offline-Ready UI**: Local vendored Leaflet maps, zero external CDN dependencies, and persistent session restore across restarts.
- **9 Shack-Ready Themes & 5-Zone Dockable Layout**: `shack-dark`, `night-red`, `amber-crt`, `forest-eoc`, `daylight`, `paper-warm`, `eoc-light`, `sky-breeze`, and `high-contrast`, with resizable dock zones, layout presets, and configurable UI/LCD typography.
- **Inline Codeplug Editor & Pocket Reference Card**: Edit channel LCD names/tones/callsigns in place, delete with multi-step **Undo**, expand DMR talkgroups, and generate printable/downloadable monospace Pocket Reference Cards.

### Planning Engines & Hardware Constraints
- **Highway Route Corridor Mode**: Calculates cross-track perpendicular distance and along-track sequencing across multi-state highway waypoints (e.g. *Tyler, TX → Shreveport, LA → Jackson, MS*).
- **Radial Proximity Ring Search**: Organizes nearby repeaters into 5 concentric distance rings around a target city or GPS coordinates.
- **Local Aviation Planner**: Builds AM Airband channel plans (ATIS/AWOS, CTAF, Tower, Ground, Approach) with aviation naming formats.
- **Hardware-Constrained Exporters**: Target radio LCD condensation (`REPEATER → RPT`, `NORTH → N`, city-frequency & callsign formats), band/mode filtering, channel capacity clamping, and spreadsheet-safe CSV exports for **CHIRP (21-column)**, **RT Systems**, and **Generic CSV**.
- **Bundled Radio Profiles**: Alinco DR-735T, AnyTone AT-778UV, Baofeng 5RM, Baofeng UV-21R, Baofeng UV-5G Plus (GMRS), BTECH DMR-6X2, Wouxun KG-1000G, and Wouxun KG-UV980P — plus custom user radio specs.

### Ham-Suite & Operational Extensions
- **Date-Versioned RepeaterBook Offline Cache**: On-demand US/Canadian state file downloads (`rb_<STATE>_<DATE>.json`) with freshness checks and OPEN/CLOSED/PRIVATE access filtering.
- **Area Weather Briefings (NWS)**: Fetches active National Weather Service alerts (`api.weather.gov`) for the states covered by your active plan with one-click copyable briefings.
- **Callsign Lookup (QRZ XML + Callook)**: Resolve operator or repeater trustee callsigns via QRZ.com XML (optional credentials) with automatic Callook.info fallback.
- **W5CDN Net Logger Interop**: Export any repeater channel as a Net Logger preset JSON, or import Net Logger `net_type_defaults` JSON into a reusable preset template.
- **Backup/Restore & Verified Self-Updater**: Download/restore configuration `.zip` backups and self-update via Git fast-forward or SHA-256 verified GitHub Release standalone bundles.

---

## Directory Architecture

```text
rp/
├── src/
│   ├── core/                      # Reusable domain library (zero UI dependencies)
│   │   ├── config/                # YAML loader, recipe schema, path resolvers
│   │   ├── engines/               # Route corridor, proximity rings, aviation, sequence
│   │   ├── exporters/             # CHIRP, RT Systems, Generic CSV exporters
│   │   ├── managers/              # Radio specs, templates, user preferences
│   │   ├── models/                # Common Internal Representation (CIR) models
│   │   ├── providers/             # RepeaterBook, Airports, RadioID, Geocoding, NWS, QRZ/Callook
│   │   ├── resources/             # Bundled radio hardware specs & YAML channel templates
│   │   ├── sanitizers/            # DataSanitizer & LCD NameCondenser
│   │   ├── special_channels/      # National Calling & NOAA Weather frequencies
│   │   ├── runner.py              # Headless YAML recipe execution engine
│   │   ├── updater.py             # Git & SHA-256 standalone self-updater
│   │   └── version.py             # Single source of truth for application version
│   │
│   ├── web/                       # FastAPI REST API, Desktop Shell & Offline Cockpit SPA
│   │   ├── app.py                 # Localhost JSON API + SPA serving
│   │   ├── desktop.py             # pywebview / chromeless browser launcher & --smoke-test
│   │   ├── security.py            # Host allowlist, CSRF Origin check, headers, path guards
│   │   ├── state.py               # Lazy workspace & persistent session state
│   │   └── static/                # index.html, styles.css, app.js, icons, vendored Leaflet
│   │
│   └── cli/                       # CLI entrypoint (--config, --validate, --list-radios)
│
├── scripts/                       # PyInstaller standalone builder, changelog, Linux desktop installer
├── tests/                         # Core, CLI, Web API, Security, UI Integrity & Playwright E2E/WCAG
├── docs/                          # Technical spec, ADRs, Manual UI QA Test Plan
├── start.bat / start.sh           # One-click Windows / Linux desktop launchers
├── Install-Windows.bat / .ps1     # Windows PATH shim & Desktop shortcut installer
└── pyproject.toml                 # Dependencies, hatch build, Ruff & Poe tasks
```

---

## User Configuration Storage

User configuration, templates, recipes, caches, and credentials are stored under `~/.config/radioplanner/` (overridable via `RADIOPLANNER_HOME`):

- `preferences.yaml`: Callsign, operator name, DMR ID, theme, fonts, 5-zone dock layout, and defaults.
- `tokens`: API credentials (`chmod 0600` on POSIX) for RepeaterBook, RadioID, and QRZ.
- `radios/`: Custom user-defined target radio specification YAML files.
- `templates/`: Custom and overridden user channel template YAML files.
- `recipes/`: Saved replayable YAML plan recipes.
- `data/`: Date-versioned offline RepeaterBook state cache files.
- `exports/`: Archived CSV exports written by the Cockpit Studio.
- `session.json`: Last active codeplug session for automatic restore on launch.

---

## Quickstart

### 1. Install Dependencies
Using [`uv`](https://docs.astral.sh/uv/):
```bash
uv sync
```

### 2. Launch Cockpit Studio (Desktop Window)
- **Windows**: Double-click `start.bat` (or run `Install-Windows.bat` to add a Desktop shortcut and global `radioplanner` command).
- **Linux**: Run `./start.sh` (or `./scripts/install_linux_desktop.sh` to add an application menu entry).
- **From CLI**:
  ```bash
  uv run w5cdn-radio-planner          # Native pywebview window (or chromeless fallback)
  uv run w5cdn-radio-planner --browser # Open in default tabbed browser
  uv run radioplanner                  # Launch Cockpit Studio with single-instance detection
  ```

### 3. Headless CLI Recipe Execution & Validation
```bash
# List bundled + custom radio hardware profiles
uv run radioplanner --list-radios

# Validate a YAML recipe (syntax + schema diagnostics)
uv run radioplanner --validate tests/fixtures/configurations/route_corridor_tx_la_ms.yaml

# Replay a saved YAML recipe directly to CSV
uv run radioplanner --config tests/fixtures/configurations/route_corridor_tx_la_ms.yaml
```

---

## Development, Testing & Packaging

Tasks can be run via `poethepoet` (`uv run poe ...`), `just`, or `make`:

```bash
# Run linter (Ruff)
uv run poe lint

# Format code
uv run poe format

# Run unit, API, security & UI integrity tests
uv run poe test

# Run tests with coverage report
uv run poe test-cov

# Run full quality gate (lint + test)
uv run poe check

# Run Playwright real-browser E2E & axe-core WCAG 2.1 AA suite (all 9 themes)
uv sync --group dev --group ui
uv run --group dev --group ui playwright install chromium
uv run --group dev --group ui poe ui-test

# Build portable standalone bundle (.zip) in release/
uv sync --group packaging
uv run --group packaging poe build

# Smoke-test the desktop server without opening a window
uv run python -m web.desktop --smoke-test --port 0
```

See [docs/MANUAL_UI_TEST_PLAN.md](docs/MANUAL_UI_TEST_PLAN.md) for the pre-release manual QA checklist.

---

## Contributing & License

- **License**: Copyright © 2026 **Eden Hare (W5CDN)**. Licensed under the **GNU General Public License v3.0 (GPL-3.0)** — see [LICENSE](LICENSE).
- **Contributing**: Pull requests are welcome! Please review [CONTRIBUTING.md](CONTRIBUTING.md) and our [Contributor License Agreement (CLA.md)](CLA.md) before submitting a PR.
