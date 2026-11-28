# W5CDN RadioPlanner

**Offline-first Travel Corridor, Radial Proximity & Local Aviation Radio Codeplug Studio** built with **Electron + TypeScript** as part of the **W5CDN Amateur Radio Desktop Suite** alongside [W5CDN Net Logger](https://github.com/edenhare/w5cdn-net-logger) and [W5CDN NTS Traffic Manager](https://github.com/edenhare/w5cdn-nts-traffic).

## Key Features

- **Three Planning Modes:**
  - **Highway Route Corridor** — multi-waypoint travel route with perpendicular corridor width filtering and along-track ordering.
  - **Radial Proximity Search** — concentric distance rings around any city, ZIP, or coordinates.
  - **Local Aviation Planner** — airband VHF AM frequencies (ATIS, AWOS, CTAF, Tower, Ground, Approach/Departure) for nearby airfields.
- **Live Hardware Targeting & LCD Condensation** — switch target radios live, preview LCD name condensation rules (`CITY_FREQ`, `CALLSIGN_FREQ`, `CALLSIGN`, `CITY`, `STANDARD`, plus aviation formats), and export **CHIRP (21-column)**, **RT Systems**, or **Generic CSV** codeplugs.
- **Hand-Editable YAML Configuration:**
  - Radio profiles (`radios/*.yaml`), channel templates (`templates/*.yaml`), saved recipes (`recipes/*.yaml`), and preferences (`preferences.yaml`) are stored as human-readable YAML files.
  - Export any radio profile, template, or recipe as `.yaml`, hand-edit it in your favorite editor, and re-import it with **strict YAML syntax & schema validation** (line/column and field-level diagnostics).
  - Open your config folder directly or reload modified YAML files from disk inside **Preferences → Backup & Updates**.
- **W5CDN Cockpit Studio UI:** 9 dark/light/high-contrast themes, precision UTC/Local clock, 5-zone dockable panels, offline Leaflet map, 20-step undo + session persistence, printable Pocket Reference Card, Net Logger JSON preset import/export, QRZ/Callook callsign lookup, NWS area weather alerts, and Zip-Slip hardened `.zip` backup/restore.

## Unified W5CDN Suite Directory Layout

- **Windows Install Directory:** `%LOCALAPPDATA%\Programs\W5CDN\RadioPlanner` (Start Menu group **W5CDN**)
- **User Data & Hand-Editable YAML Configs:**
  - Windows: `%APPDATA%\W5CDN\RadioPlanner` (plus shared suite settings in `%APPDATA%\W5CDN\shared\config.txt`)
  - Linux / macOS: `~/.config/W5CDN/RadioPlanner` (plus `~/.config/W5CDN/shared/config.txt`)
  - Legacy installations with `~/.config/radioplanner/preferences.yaml` are automatically preserved.
  - Override with `RADIOPLANNER_HOME` or `W5CDN_SUITE_DIR`.

## Running From Source

Requires **Node.js 22+ LTS**:

```bash
npm install
npm start
```

Or double-click `start.bat` (Windows) / run `./start.sh` (Linux/macOS).

## Development & Testing

```bash
npm run typecheck      # TypeScript strict type checking
npm run test           # Vitest unit & API tests
npm run test:cov       # Vitest with V8 coverage report
npm run smoke          # Live headless Electron GUI + API smoke test
npm run test:e2e       # Playwright Chromium end-to-end UI suite
npm run package:dir    # Unpacked Electron build (local smoke test)
npm run package:win    # Windows NSIS installer
npm run package:linux  # Linux AppImage
```
