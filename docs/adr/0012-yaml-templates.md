# 12. YAML Format for App and User Codeplug Templates

## Status
Accepted

## Context
Initial implementations explored embedding CSV string blobs inside JSON files for preset and custom channel templates. However:
1. Embedding multi-line CSV within JSON strings introduces escaping overhead and reduces human readability.
2. RadioPlanner recipes and hardware specifications are already standardized on YAML format across `~/.config/radioplanner/` (`preferences.yaml`, `radios/<id>.yaml`, `recipes/<name>.yaml`).
3. Operators editing templates directly with text editors require clean syntax, comment preservation, and clear field separation without needing CSV column index memorization or JSON syntax quotation rigidity.

## Decision
1. **YAML File Format for Templates:**
   - All codeplug templates—both application-provided templates in `src/core/resources/templates/` and user-custom templates in `~/.config/radioplanner/templates/`—must be YAML files (`.yaml` or `.yml`).
   - Neither JSON nor raw CSV template files are used as the primary storage format.
2. **Structured Channel Schema in YAML:**
   - Templates define metadata (`id`, `name`, `description`, `tagText`, `tagColorHex`) and a structured list of channels (`channels:`):
     ```yaml
     id: calling_channels
     name: National Calling Frequencies
     description: Standard simplex FM calling frequencies across amateur bands
     tagText: CALLING
     tagColorHex: "#00BCD4"
     channels:
       - name: 2m CALL
         rxFreq: 146.52000
         txFreq: 146.52000
         mode: FM
         power: High
         comment: 2m VHF National Simplex Calling Frequency
     ```
3. **Template Model & Manager:**
   - `PresetTemplateFile` contains `channels: list[TemplateChannelItem]`.
   - `TemplateManager` scans and loads `*.yaml` / `*.yml` files from the app resources and user config directories, saving user customizations as `<id>.yaml`.
   - The CLI Template Manager allows importing YAML templates directly, or converting legacy CSV files into structured YAML templates.

## Consequences
- Clean, consistent configuration ecosystem across RadioPlanner (YAML used for recipes, preferences, hardware specs, and templates).
- Highly readable, easily auditable template definitions with structured field typing and comments.
- Seamless compatibility with the Common Internal Representation (CIR) pipeline.
