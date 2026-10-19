# 2. Package Structure and User Configuration Storage

Date: 2026-10-19

## Status
Accepted

## Context
RadioPlanner needs a modular, decoupled codebase where the core domain logic is reusable as a standalone library without any terminal/CLI dependencies. Additionally, persistent configuration, radio definitions, replayable runs, and credentials must be stored cleanly in a cross-platform location without polluting working directories.

## Decision
1. **Source Package Layout**:
   - `src/core/`: Common/shared domain library containing Common Internal Representation (CIR), synthesis engines, data sanitizers, exporters, providers, and config loaders.
   - `src/cli/`: Rich terminal interactive wizard, step controllers, visual tables/panels, and headless runner.
   - Avoid embedding the application name inside package directories (`src/core`, `src/cli`).

2. **User Configuration Storage Path**:
   - Stored in the user's home directory across all platforms: `~/.config/radioplanner/` (can be overridden by `RADIOPLANNER_HOME`).
   - Structure:
     - `~/.config/radioplanner/preferences.yaml`: General user settings (callsign, DMR ID, default distance units).
     - `~/.config/radioplanner/tokens`: Sensitive third-party API credentials (RepeaterBook, RadioID) stored separately with restricted permissions.
     - `~/.config/radioplanner/radios/`: User-added or overridden target radio hardware specification YAML files.
     - `~/.config/radioplanner/recipes/`: Saved replayable workflow configurations (YAML) for Route Corridor, Proximity, and Aviation runs.

3. **Bundled Radio Definitions**:
   - Base factory radio specifications (Baofeng, BTECH, Wouxun, Alinco, Generic) are shipped in separate YAML files under `src/core/resources/radios/*.yaml`.
   - The radio manager dynamically loads factory radios first and layers user modifications from `~/.config/radioplanner/radios/`.

## Consequences
- The domain core can be imported and tested completely independently of terminal rendering.
- User files, tokens, recipes, and custom radio profiles are cleanly separated.
- Storing replayable files in `~/.config/radioplanner/recipes/` provides a memorable standard for saving and re-running plans.
