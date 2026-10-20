# 13. Target Radio Frequency Band Selection and Expanded Highway Corridor Dataset

## Status
Accepted

## Context
1. In Mode 1 (Highway Route Corridor), selecting a target radio previously defaulted to including all supported bands blindly, without allowing the operator to select which frequency bands they want active for that radio. Per Section 2.3 of `docs/route_planner_spec.md`, default bands should exclude Airband for highway corridor travel, and operators must be able to customize their active bands (e.g., 2m only, 2m+70cm, or including WX).
2. The initial offline sample repeater dataset only contained 8 repeaters along the 320-mile Tyler, TX -> Shreveport, LA -> Jackson, MS highway corridor. Adding Calling and NOAA Weather channels brought the total to only ~16 channels, which was inadequate for a realistic travel corridor codeplug.

## Decision
1. **Interactive Target Radio Band Selection (`band_selector.py`):**
   - After selecting target radio hardware, the CLI presents an interactive frequency band selection table showing:
     - Band name and frequency range descriptions.
     - Current toggle status (`[X]` vs `[ ]`).
     - Default exclusions according to Mode (e.g. Airband excluded by default for Route Corridor and Proximity, but active for Aviation).
   - Operators can toggle individual bands by number, select all (`A`), deselect all (`N`), or confirm (`C`).
   - The selected bands are saved in `RadioTargetConfig.bands` and passed to `SequenceOrganizer.assemble(allowed_bands=...)` and `filter_channels_for_radio(allowed_bands=...)`.
2. **Realistic Multi-State Corridor Dataset:**
   - Expanded `OFFLINE_REPEATERS` in `src/core/providers/repeaterbook.py` to 62 repeaters, including over 50 realistic VHF/UHF/DMR repeaters across Smith, Gregg, and Harrison Counties (TX); Caddo, Bossier, Webster, Bienville, Lincoln, Ouachita, Richland, and Madison Parishes (LA); and Warren, Hinds, Rankin, and Madison Counties (MS).
   - Route Corridor calculations along I-20 now generate 45-55+ travel repeaters plus calling and weather channels, yielding a comprehensive, authentic travel codeplug.
3. **Split Summary Realignment:**
   - Updated the Frequency Breakdown summary in `render_split_summary` to report the exact frequency band counts and total channel count of the final assembled codeplug.

## Consequences
- Operators have granular control over which frequency bands are programmed into their radio.
- Sample route planning along Interstate 20 produces a rich, realistic repeater codeplug.
- Strict adherence to hardware constraints and user preferences.
