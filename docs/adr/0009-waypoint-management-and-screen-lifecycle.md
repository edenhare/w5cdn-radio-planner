# 9. In-CLI Interactive Waypoint Management and Screen Lifecycle

## Status
Accepted

## Context
When launching the application or switching operating modes, terminal output could previously accumulate below prior shell sessions, cluttering the view.
Furthermore, in Mode 1 (Highway Route Corridor), presenting waypoints as a single semicolon-delimited string prompt (`"Tyler, TX; Shreveport, LA; Jackson, MS"`) was ambiguous: users could not easily see what happened when typing, had no intuitive mechanism to wipe or kill existing waypoints to start fresh, and could not easily edit individual stops without relying on external system text editors (like nano or vim).

## Decision
1. **Screen Clearing Lifecycle:**
   - Execute `console.clear()` upon application startup so the initial header and menu appear cleanly at the top of the terminal.
   - Execute `console.clear()` upon transitioning into operating modes to provide a focused, uncluttered workspace.
2. **Interactive Waypoint Manager (`waypoint_editor.py`):**
   - Provide a full in-terminal waypoint management interface without external dependencies.
   - Present current stops in a structured table with leg distances and geocoding validation status.
   - Provide clear, explicit actions:
     - `[C] Continue / Confirm Route`
     - `[N] New Route from Scratch` (guided step-by-step entry of start, destination, and intermediate stops)
     - `[A] Add / Insert Waypoint`
     - `[E] Edit Waypoint` (select stop by number and provide new spelling/location)
     - `[D] Delete Waypoint`
     - `[K] Kill / Clear all Waypoints`
     - `[R] Reorder / Swap Waypoint Positions`
     - `[V] Reverse Route Direction`
     - `[B] Back to Main Menu`
3. **Color Themes in User Preferences:**
   - Add `colorTheme` setting to `UserPreferences` (`DARK`, `LIGHT`, `HIGH_CONTRAST`).
   - Persist theme in `~/.config/radioplanner/preferences.yaml`.

## Consequences
- Eliminates dependency on external text editors.
- Provides immediate visual feedback on waypoints, route order, and spelling resolution.
- Clean terminal presentation on startup and mode transitions.
