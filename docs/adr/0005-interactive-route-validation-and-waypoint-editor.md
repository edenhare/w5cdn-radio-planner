# 5. Interactive Route Validation and Waypoint Editor

Date: 2026-10-19

## Status
Accepted

## Context
In Route Corridor mode, users input sequential travel waypoints (e.g. `Tyler, TX; Shreveport, LA; Jackson, MS`). In previous versions, the route calculation ran after target radio selection. If a waypoint was misspelled, out of sequence, or missing, the error occurred late in the pipeline.

The user must validate the route *before* selecting hardware, with full capability to correct spelling, reorder stops, add intermediate waypoints, reverse travel direction, or remove stops.

## Decision
1. **Early Route Validation Step**:
   - Immediately upon entering waypoints, the system attempts geocoding and leg calculation for each stop.
   - A Rich table displays validation status for every waypoint: index, input query, resolved location/coordinates, and leg distance.
2. **Interactive Waypoint Editor**:
   - If any waypoint fails to resolve, or if the user requests changes, the CLI presents an interactive waypoint editor menu:
     - `[1]` Correct/Edit a waypoint spelling
     - `[2]` Add a new waypoint (specify position)
     - `[3]` Remove a waypoint
     - `[4]` Swap/Reorder waypoints
     - `[5]` Reverse entire route order
     - `[C]` Confirm & Proceed to Target Radio Selection (enabled when all stops resolve)
     - `[Q]` Cancel & Return to Main Menu
3. **Pre-condition Enforcement**:
   - The user cannot proceed to radio selection until at least 2 waypoints are successfully resolved.

## Consequences
- Prevents downstream calculation errors.
- Allows users to interactively plan, tweak, and reorder their road trips before committing to hardware export configurations.
