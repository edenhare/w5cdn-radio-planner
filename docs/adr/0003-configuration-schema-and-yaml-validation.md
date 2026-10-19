# 3. YAML Parsing with Line-Level Diagnostics and Configuration Schema

Date: 2026-10-19

## Status
Accepted

## Context
Users interact with RadioPlanner either through the interactive Rich CLI wizard or by writing/editing YAML configuration recipes. If a configuration file contains syntax errors (bad indentation, unclosed quotes, malformed keys) or schema violations, standard parsers often provide cryptic stack traces. The system must pinpoint exact line numbers, column positions, and a contextual code snippet with clear remediation suggestions.

## Decision
1. **YAML Engine**:
   - Use `ruamel.yaml` as the core parsing engine for precise line and column introspection, or PyYAML with custom mark extraction.
   - Implement a dedicated `YamlConfigLoader` in `src/core/config/yaml_loader.py` that intercepts syntax errors (`MarkedYAMLError`), extracts line numbers, column numbers, surrounding lines, and formats a human-friendly visual diagnostic.
   - Integrate Pydantic v2 validation models (`ValidationError`) with custom field-level error mapping to identify schema mismatches (e.g., missing required fields, invalid band names).

2. **Error Presentation**:
   - Provide clean programmatic error models (`ConfigParseError`) in the core library.
   - The CLI renders these errors using `rich.panel.Panel` and syntax-highlighted code excerpts pointing directly with an arrow to the problematic character.

3. **Replay Recipe Schema**:
   - Versioned recipes (`version: "1.0"`) supporting `ROUTE_CORRIDOR`, `PROXIMITY_SEARCH`, and `AVIATION_PLANNER` modes.

## Consequences
- Immediate, friendly user feedback on syntax and schema errors without Python stack dumps.
- Decoupled parser core with Rich presentation in the CLI layer.
