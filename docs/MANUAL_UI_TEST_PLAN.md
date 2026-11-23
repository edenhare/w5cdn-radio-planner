# W5CDN RadioPlanner — Manual UI & Release QA Test Plan

Run this checklist before tagging a release (`v*`) or after major UI/desktop changes.

## 1. Launch Modes & Desktop Shell
- [ ] `start.bat` (Windows) opens native pywebview window with W5CDN RadioPlanner taskbar/titlebar icon.
- [ ] `start.sh` (Linux) opens chromeless `--app-window` cleanly with `w5cdn-radio-planner` WM class.
- [ ] `python -m web.desktop --browser` opens in default browser and exits cleanly when the tab closes.
- [ ] `python -m web.desktop --smoke-test --port 0` exits `0` with `SMOKE_TEST_OK`.
- [ ] `radioplanner --list-radios` and `radioplanner --validate tests/fixtures/configurations/route_corridor_tx_la_ms.yaml` exit `0`.

## 2. Offline Cockpit & Layout
- [ ] Disconnect from internet (or block external origins): app loads with zero console errors and zero broken CSS/JS assets (Leaflet is vendored locally).
- [ ] Default first-run layout docks **Plan Builder** (Left), **Codeplug Table** (Center), **Interactive Map & Summary** (Right).
- [ ] Toggle each panel (`Builder`, `Map`, `Summary`, `Templates`, `Radios`) via topbar pills; drag dock edges to resize; test Quick Layout Presets and `Reset Layout`; reload page and confirm layout persists.
- [ ] Slide-out **Saved Recipes** drawer opens from left rail, saves active plan as YAML, loads a recipe back into Plan Builder, and deletes a recipe cleanly.

## 3. Themes, Typography & Accessibility
- [ ] Switch through all 9 themes (`shack-dark`, `night-red`, `amber-crt`, `forest-eoc`, `daylight`, `paper-warm`, `eoc-light`, `sky-breeze`, `high-contrast`) in Preferences -> Appearance; verify readability and zero unstyled elements.
- [ ] Adjust UI Font, Mono Font, UI Font Size, and LCD Font Size sliders; verify live preview and persistence across reload.
- [ ] Keyboard navigation: Tab through modals, press `Escape` to close any open modal.

## 4. Plan Generation & Codeplug Workflows
- [ ] **Route Corridor**: Build Tyler, TX -> Shreveport, LA -> Jackson, MS; verify waypoints, corridor repeaters, map route polyline, and summary rows.
- [ ] **Proximity Search**: Build Dallas, TX (50 mi); verify concentric rings on map and summary.
- [ ] **Aviation Planner**: Build Tyler, TX (50 mi); verify airfields and AM Airband channels.
- [ ] Switch Target Radio (e.g., AnyTone AT-778UV -> Baofeng 5RM -> Baofeng UV-5G Plus (GMRS)); verify LCD names re-condense and bands update.
- [ ] **Inline Channel Editor**: Click edit on a channel row, modify LCD Name / Tone / Callsign, click `Lookup` to resolve trustee callsign, save, verify table updates.
- [ ] **Delete & Undo**: Select 2 channels, Delete, verify slots renumber; click **Undo**, verify deleted channels restore cleanly.
- [ ] **Pocket Reference Card**: Open Pocket Card modal, verify KPIs and monospace reference card, Copy Text, Download `.txt`, and Print preview.
- [ ] **CSV Export**: Export for RT Systems and CHIRP; verify native Save dialog in `pywebview` (or download in browser) and valid CSV output.
- [ ] **Persistent Session Restore**: Reload browser/restart app and verify the active codeplug restores automatically.

## 5. Ham-Suite & System Extensions
- [ ] **Area Weather (NWS)**: Click `Area Weather` in active plan header; verify alerts load for the plan's states (or graceful offline notice) and Copy Briefing works.
- [ ] **Callsign Lookup & QRZ**: In Preferences -> Operator, click `Lookup` to populate name; in API Keys, test QRZ login status banner.
- [ ] **W5CDN Net Logger Interop**: Click `Net Logger` action on a repeater row to copy a Net Logger repeater preset JSON; import a Net Logger `net_type_defaults` JSON via Templates -> Import.
- [ ] **Backup & Restore**: Download backup `.zip` (with and without tokens), modify a preference, restore the `.zip`, confirm preferences/recipes/templates/radios restore cleanly.
- [ ] **Self-Update**: Click `Check for Updates` in Preferences -> Backup & Updates; verify version/install mode display and graceful offline handling.
