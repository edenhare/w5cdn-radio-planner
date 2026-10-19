# 7. Preset Template Manager Architecture

Date: 2026-10-19

## Status
Accepted

## Context
Sections 2.2 (Mode 4) and 3.1–3.2 of the technical specification mandate a dedicated Preset / Pre-Configured Codeplug Templates Manager. Users need to view standard built-in templates (National Calling frequencies, NOAA Weather Radio), import custom CSV/JSON channel templates with custom badge tags (e.g. SKYWARN, ARES, SAR, GMRS), inspect channels, and export them into radio-constrained codeplugs.

## Decision
1. **Menu Integration**:
   - Provide a dedicated **Preset Templates Manager** operating mode directly accessible from the main menu.
2. **Storage Location**:
   - Store user-created or imported custom template files in `~/.config/radioplanner/templates/` (JSON or CSV format as per Spec 6.2.3).
3. **Capabilities**:
   - List all available templates (built-in calling, built-in weather, custom).
   - Inspect channel details with badge previews.
   - Import/Add new custom templates from CSV/JSON.
   - Synthesize and export a template directly into a target radio codeplug.

## Consequences
- Full compliance with Spec Mode 4.
- Clean separation of built-in factory templates and persistent user-imported templates.
