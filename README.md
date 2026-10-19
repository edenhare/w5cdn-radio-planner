# RadioPlanner 📻

**RadioPlanner** is a cross-platform Python CLI and domain library for amateur radio operators, aviation enthusiasts, and GMRS radio users. It synthesizes travel corridor repeater sequences along highway routes, performs 5-ring radial proximity searches, gathers local airport communication frequencies, and formats hardware-constrained exports for target radios (CHIRP CSV, RT Systems, BTECH, Baofeng, Wouxun, Alinco, Generic CSV).

---

## Features

- **Interactive Rich CLI Wizard**: Step-by-step guidance through operating modes with real-time configuration inspection and visual split summaries.
- **Highway Route Corridor Mode**: Calculates lateral cross-track perpendicular distance along sequential highway waypoints (e.g. *Tyler, TX -> Shreveport, LA -> Jackson, MS*) and sequences repeaters chronologically.
- **Radial Proximity Ring Search**: Sorts local repeaters across 5 concentric distance bands (Ring 1 to Ring 5).
- **Local Aviation Planner**: Resolves airport communication frequencies (CTAF, Tower, Ground, ATIS, Approach).
- **Target Radio Hardware Constraints**: LCD name condensation (abbreviation replacements like `REPEATER -> RPT`, `NORTH -> N`), maximum channel capacity limits, and custom column exporters.
- **Replayable Configuration Recipes (YAML)**: Save interactive runs to versioned `.yaml` files in `~/.config/radioplanner/recipes/` to re-run plans anytime.
- **Intelligent YAML Diagnostic Parser**: Intercepts YAML syntax and schema errors, pointing with line numbers, column numbers, caret pointers, and actionable fix suggestions.
- **Tri-State Testing**: Comprehensive test coverage across Good Data, Bad Data, and Missing/Offline Data.

---

## Directory Architecture

```
rp/
├── src/
│   ├── core/                      # Reusable domain library (zero CLI dependencies)
│   │   ├── config/                # YAML loader, schema validation, path resolvers
│   │   ├── engines/               # Route corridor, proximity rings, aviation engines
│   │   ├── exporters/             # CHIRP, RT Systems, Generic CSV exporters
│   │   ├── managers/              # Radio hardware specs and user preferences managers
│   │   ├── models/                # CIR (Common Internal Representation) data models
│   │   ├── providers/             # RepeaterBook, OurAirports, RadioID, Geocoding
│   │   ├── resources/radios/      # Bundled target radio hardware specifications (YAML)
│   │   ├── sanitizers/            # DataSanitizer, LCD NameCondenser
│   │   ├── special_channels/      # National Calling & NOAA Weather frequencies
│   │   └── runner.py              # Headless recipe execution engine
│   │
│   └── cli/                       # Rich Terminal User Interface
│       ├── main.py                # CLI entrypoint (--config, --validate, --list-radios)
│       ├── ui/                    # Rich theme, badges, split view summaries, panels
│       └── wizard/                # Interactive step-by-step wizard
│
├── tests/
│   ├── core/                      # Domain unit and integration tests
│   ├── cli/                       # CLI rendering, flag, and wizard tests
│   └── fixtures/
│       └── configurations/        # Test configuration recipes (YAML)
│
├── docs/
│   ├── route_planner_spec.md      # Full technical specification
│   └── adr/                       # Architecture Decision Records
│
├── Justfile                       # Just task runner definitions
├── Makefile                       # POSIX Makefile
└── pyproject.toml                 # Dependencies, hatch build, and poethepoet tasks
```

---

## User Configuration Storage

User configurations and credentials are stored cleanly in the user's home directory:
- `~/.config/radioplanner/preferences.yaml`: Callsign, DMR ID, default distance units.
- `~/.config/radioplanner/tokens`: Sensitive third-party API credentials (chmod 0600 on POSIX).
- `~/.config/radioplanner/radios/`: Custom user-defined target radio specification YAML files.
- `~/.config/radioplanner/recipes/`: Saved replayable configuration recipes.

*(Can be overridden across environments via the `RADIOPLANNER_HOME` environment variable).*

---

## Quickstart

### 1. Installation
Using `uv`:
```bash
uv sync
```

### 2. Launch Interactive Wizard
```bash
uv run radioplanner
# or:
uv run poe run
```

### 3. Replay a Saved Recipe Directly
```bash
uv run radioplanner --config tests/fixtures/configurations/route_corridor_tx_la_ms.yaml
```

### 4. Validate a Configuration File Syntax & Schema
```bash
uv run radioplanner --validate tests/fixtures/configurations/route_corridor_tx_la_ms.yaml
```

### 5. List Supported Radio Hardware Specs
```bash
uv run radioplanner --list-radios
```

---

## Development & Testing

Tasks can be run via `poethepoet` (built into Python/uv), `just`, or `make`:

```bash
# Run tests
uv run poe test
# or: just test / make test

# Run tests with coverage report
uv run poe test-cov
# or: just test-cov / make test-cov

# Run linter
uv run poe lint
# or: just lint / make lint

# Format code
uv run poe format
# or: just format / make format

# Run full quality gate (lint + test)
uv run poe check
# or: just check / make check
```
