# 8. Radios and Hardware Specifications Manager Architecture

## Status
Accepted

## Context
Section 3.5 of the technical specification mandates a Radios & Hardware Manager component capable of inspecting radio hardware parameters (Max Channels, Max Name Length, Allowed Symbols, Allowed Special Characters, Supported Bands, Supported Modes) and CSV column exporter rules per programmer format.
Users must be able to view all configured hardware models, inspect technical parameters, add new custom target radio specifications, override/edit existing radio specs, and delete custom models.

## Decision
1. Enhance `RadioManager` with detection of factory versus user-defined radios, along with deletion and override persistence to `~/.config/radioplanner/radios/<id>.yaml`.
2. Implement a dedicated, interactive `_flow_radios_manager` within the CLI wizard:
   - Displays a rich multi-column summary table of all loaded hardware models with badges for programmer format and factory/user status.
   - Provides an **Inspect Radio Specification** subview showing complete technical limits and exporter column schemas.
   - Provides an **Add New Custom Radio Model** wizard prompting for brand, model, unique ID, channel limits, LCD condensation constraints, bands, modes, and programmer format.
   - Provides an **Edit / Override Radio Specification** tool that allows modifying any radio model and writing the customized YAML to the user's config directory.
   - Provides a **Delete User Radio** action to remove custom user models.

## Consequences
- Operator can add new or niche radios without modifying core repository files.
- Clear provenance tracking between immutable factory definitions and mutable user overrides.
- Full compliance with Section 3.5 and 6.1.3 of the specification.
