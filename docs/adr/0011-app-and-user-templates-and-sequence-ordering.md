# 11. App and User Templates Architecture and Pre-Hardware Sequence Ordering

## Status
Accepted

## Context
Previously, "built-in" calling and NOAA weather templates were hardcoded in Python code within `TemplateManager`.
Furthermore, in Mode 1 (Highway Route Corridor), sequence order was hardcoded after radio selection, rather than allowing users to choose which templates to apply and interactively reorder the sequence blocks (e.g. placing calling frequencies before repeaters and weather channels after repeaters) before choosing target hardware.

## Decision
1. **Templates as File-Based Resources (`src/core/resources/templates/`):**
   - Eliminate hardcoded Python template definitions.
   - Store application-provided templates as JSON files in `src/core/resources/templates/` (`calling_channels.json`, `noaa_wx_channels.json`).
   - Store user custom templates and overrides in `~/.config/radioplanner/templates/`.
   - User templates completely take precedence over app-provided templates of the same ID.
   - When a user edits an app-provided template, it is copied into `~/.config/radioplanner/templates/<id>.json` and modified there.
2. **Mode 1 Post-Waypoint Banner & Corridor Width:**
   - Immediately upon confirming waypoints, clear the terminal screen.
   - Render the top-level application banner (`render_header`).
   - Display a Route Overview panel containing total waypoint count, calculated route distance in miles, and corridor path.
   - Prompt for corridor search width.
3. **Interactive Sequence & Template Organizer (`sequence_editor.py`):**
   - Before selecting a radio, allow the user to select templates from `TemplateManager`.
   - Provide an interactive ordering interface allowing users to view, add, remove, and reorder sequence blocks (`ROUTE_PLAN` and `TEMPLATE:<id>`).
   - Radio selection proceeds only after the sequence order is finalized.

## Consequences
- Clean separation between application default templates and persistent user template overrides.
- Operators can sequence codeplug blocks according to operational needs before hardware formatting.
- Consistent visual lifecycle with cleared screen and top-level header after waypoint confirmation.
