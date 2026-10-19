# RadioPlanner Technical Specification & System Guidelines

## 1. System Overview

**RadioPlanner** is a cross-platform system designed for amateur radio operators, aviation enthusiasts, and GMRS radio users. It calculates travel corridor repeater sequences along highway routes, performs radial proximity searches, processes local airport communication frequencies, and manages pre-configured codeplug templates, formatting hardware-constrained exports for target radios (Baofeng DM-32UV, UV-5R, 5RM, UV-980P, Alinco, AnyTone, BTECH, Icom, Kenwood, Radioddity, Wouxun, CHIRP CSV, RT Systems, Vendor CPS, Generic CSV, etc.).

---

## 2. Operating Modes & Navigation Architecture

The application features a modular navigation architecture supporting seven primary functional areas:

```
+-----------------------------------------------------------------------------------+
|                            APPLICATION OPERATING MODES                            |
+---------------------+---------------------+---------------------+-----------------+
| 1. Route Planner    | 2. Proximity Ring   | 3. Preset Templates | 4. Radios 📻    |
|    Corridor Mode    |    Search Mode      |    Manager          |    Manager      |
+---------------------+---------------------+---------------------+-----------------+
| 5. Review Table     | 6. Preferences      | 7. Logs 📑          |
+---------------------+---------------------+---------------------+
```

1. **Route Planner (Corridor Mode):** Accepts sequential highway travel waypoints (e.g., *Tyler, TX -> Shreveport, LA -> Jackson, MS*), calculates lateral cross-track perpendicular distance to highway segments, and sequences active repeaters chronologically along the traveler's route.
2. **Proximity Ring Search Mode:** Accepts a central location and search radius (e.g., 50 miles / 80 km around *Dallas, TX*), gathering, deduplicating, and sorting local repeaters across 5 concentric proximity distance bands (Ring 1 to Ring 5).
3. **Preset / Pre-Configured Codeplug Templates (Template Management Component):** Ingests, edits, and manages pre-configured CSV/JSON templates stored in application data, featuring custom **Tag Badge Labels & Color Palette Swatches** and interactive spreadsheet editing with a dedicated **Comment Column**.
4. **Aviation Planner Mode:** Focuses on a specific city/location (e.g. *Tyler, TX* or *Dallas, TX*), querying local airport communication frequencies (CTAF, Tower, Ground, ATIS/AWOS, Approach/Departure) and merging them with user-selected channel templates (such as Packet Radio frequencies, National Calling, or custom templates) into designated codeplug memory blocks.
5. **Radios & Programmer Configurations Manager (Radio Configuration Component):** Manages target radio hardware specifications (Max Channels, Max Name Length, Allowed Symbols, Allowed Special Characters, Supported Bands, Supported Modes) and interactive CSV column header exporter rules per programmer format.
6. **Review Table (Channel Review Component):** Displays generated codeplug channels with color-coded frequency band badges, tone details, DMR digital Talkgroup channel duplication, and deletion capabilities.
7. **Preferences (System Settings Component):** Manages operator identity (`W5CDN`), RadioID.net DMR ID verification (`3224901`), third-party API credentials (RepeaterBook API Key, RadioID.net Call Sign & API Key), distance units (Miles vs Kilometers), and language selection (`English`, `Spanish`, `French`, `German`).
8. **Logs Viewer (Diagnostic Logging Component):** Interactive diagnostic log viewer for network queries, RadioID.net lookups, CSV parsing, and synthesis operations.

---

### 2.1 Desktop Navigation MenuBar Architecture

For desktop environments, the application features a native top MenuBar offering standard system keyboard shortcuts, quick planner mode switching, diagnostic tools, and help resources:

```
+-----------------------------------------------------------------------------------+
|  File               Planner Mode             Tools            Help                |
+------------------+  +---------------------+  +-------------+  +-------------------+
| New Corridor...  |  | 1. Route Corridor   |  | OpenStreetMap|  | RepeaterBook API  |
| Open CSV/JSON... |  | 2. Proximity Rings  |  | RadioID...  |  | Documentation     |
| Export CSV...    |  | 3. Aviation Planner |  | Log Viewer  |  | About RadioPlanner|
| Preferences...   |  | 4. Preset Templates |  +-------------+  +-------------------+
| Exit             |  | 5. Radios Manager   |
+------------------+  | 6. Review Codeplug  |
                      +---------------------+
```

- **File Menu:**
  - `New Corridor Route` (`Ctrl+N` / `Cmd+N`) — Resets corridor waypoints to start fresh.
  - `Open Codeplug / Template CSV...` (`Ctrl+O` / `Cmd+O`) — Opens file picker to ingest local CSV/JSON templates.
  - `Export Active Codeplug CSV...` (`Ctrl+S` / `Cmd+S`) — Triggers hardware-constrained CSV export dialog.
  - `Preferences...` (`Ctrl+,` / `Cmd+,`) — Navigates directly to System Settings.
  - `Exit` (`Alt+F4` / `Cmd+Q`) — Quits the desktop application.

- **Planner Mode Menu:**
  - `1. Route Corridor Planner` (`Ctrl+1`) — Switches to Highway Corridor Mode.
  - `2. Radial Proximity Search` (`Ctrl+2`) — Switches to Proximity Ring Search Mode.
  - `3. Local Aviation & Template Planner` (`Ctrl+3`) — Switches to Aviation Planner Mode.
  - `4. Preset Templates Manager` (`Ctrl+4`) — Switches to Templates Manager.
  - `5. Radios & Hardware Manager` (`Ctrl+5`) — Switches to Radios & Programmer Manager.
  - `6. Review & Edit Codeplug` (`Ctrl+6`) — Switches to Review & Edit Table.

- **Tools Menu:**
  - `View OpenStreetMap...` (`Ctrl+M` / `Cmd+M`) — Launches the interactive OpenStreetMap canvas view.
  - `RadioID.net DMR ID Verification...` — Launches DMR Radio ID lookup tool.
  - `System Diagnostic Log Viewer` (`Ctrl+L` / `Cmd+L`) — Navigates to system logs.

- **Help Menu:**
  - `RepeaterBook API Status` — Displays connection and key status.
  - `Technical Specifications` — Opens system specification documentation.
  - `About RadioPlanner` — Displays application version, operator callsign (`W5CDN`), DMR ID (`3224901`), and multiplatform build details.

---

### 2.2 Mode-Specific UI & Data Flow Pipelines

Every operating mode follows a dedicated, predictable multi-step UI screen and data flow pipeline:

```
+----------------------------------------------------------------------------------------------------+
|                                 1. HIGHWAY ROUTE CORRIDOR FLOW                                     |
+----------------------------------------------------------------------------------------------------+
| Step 1: [RoutePlannerScreen]      -> Input route waypoints (e.g. Tyler -> Shreveport -> Jackson)   |
| Step 2: [RadioTargetConfigScreen] -> Select Target Radio, Programmer, and Sequence Position Rows   |
| Step 3: [RouteSummarySplitScreen] -> Review Corridor Cities list & Frequency Breakdown Summary     |
| Step 4: [ReviewTableScreen]       -> Review, edit DMR talkgroups, and export codeplug CSV          |
+----------------------------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------------------------+
|                                 2. RADIAL PROXIMITY SEARCH FLOW                                    |
+----------------------------------------------------------------------------------------------------+
| Step 1: [ProximityScreen]         -> Input City (e.g. Dallas, TX), click Validate, set radius      |
| Step 2: [RadioTargetConfigScreen] -> Select Target Radio, Programmer, and Sequence Position Rows   |
| Step 3: [ProximitySummarySplitScreen]-> Review 5 Concentric Distance Rings & Channel Breakdown     |
| Step 4: [ReviewTableScreen]       -> Review, edit DMR talkgroups, and export codeplug CSV          |
+----------------------------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------------------------+
|                                 3. LOCAL AVIATION PLANNER FLOW                                     |
+----------------------------------------------------------------------------------------------------+
| Step 1: [AviationScreen]          -> Input City (e.g. Tyler, TX), click Validate, set radius       |
| Step 2: [RadioTargetConfigScreen] -> Select Target Radio, Programmer, and Sequence Position Rows   |
| Step 3: [AviationSummarySplitScreen] -> Review Matched Airports list & Airband Channel Breakdown   |
| Step 4: [ReviewTableScreen]       -> Review, edit DMR talkgroups, and export codeplug CSV          |
+----------------------------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------------------------+
|                                 4. PRESET TEMPLATES MANAGER FLOW                                   |
+----------------------------------------------------------------------------------------------------+
| Step 1: [TemplateScreen]          -> View, upload, or edit preset CSV/JSON channel templates       |
| Step 2: [ReviewTableScreen]       -> Review, edit DMR talkgroups, and export codeplug CSV          |
+----------------------------------------------------------------------------------------------------+
```

---

### 2.3 Mode & Step Behavioral Matrix

| Operating Mode | Default Bands Selected | Default Modes Selected | Simplex Checkbox Default | Default Sequence Items | Summary Screen Used | Default Export CSV File Name Format |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **1. Route Corridor** | All supported bands **EXCEPT Airband** | All supported modes (`FM Analog`, etc.) | Checked (`true`) | `National Calling`, `Route Corridor Repeaters`, `NOAA Weather` | `RouteSummarySplitScreen` | `Start_City-End_City-route-radio-MMDDYY.csv` |
| **2. Proximity Search** | All supported bands **EXCEPT Airband** | All supported modes (`FM Analog`, etc.) | Checked (`true`) | `National Calling`, `Proximity Radial Repeaters`, `NOAA Weather` | `ProximitySummarySplitScreen` | `City_State-proximity-radio-MMDDYY.csv` |
| **3. Aviation Planner** | `Airband AM (108-137 MHz)` **ONLY** | `AM` **ONLY** (`FM Analog` disabled) | Unchecked (`false`) | `Local Airport Aviation Channels` **ONLY** (no auto-injected WX/Calling) | `AviationSummarySplitScreen` | `City_State-aviation-radio-MMDDYY.csv` |
| **4. Preset Templates** | All supported bands | All supported modes | N/A | Preset template channels | `ReviewTableScreen` | `Template_Name-radio-MMDDYY.csv` |

---

## 3. Core Functional Pillars & System Algorithms

### 3.1 Pure Template-Driven Sequence Ordering
- **Position-Based Selection Rows:** Sequence positions (`Position 1 (Top of Codeplug)`, `Position 2`, `Position 3`...) are managed as position-indexed blocks with interactive selection indicators.
- **Conflict Indication & Location Display:** When an option is currently assigned to another row, `📍 Currently placed at Position X` is displayed.
- **Position Swapping:** Selecting an option assigned elsewhere swaps memory block positions automatically.
- **Pure Template Keys:** Sequence keys use template identifiers (`TEMPLATE:builtin_calling_channels`, `TEMPLATE:builtin_noaa_wx_channels`, `ROUTE_PLAN`, `AVIATION_BLOCK`, `AVIATION_INTERLEAVED`, and custom `TEMPLATE:<id>`).

### 3.2 Standard Default Templates & Intelligent Name Condensation
- **National Calling Frequencies Template:** Built-in template (`builtin_calling_channels`) containing 10m HF, 6m (52.525 MHz), 2m (146.520 MHz), 1.25m (223.500 MHz), 70cm (446.000 MHz), and GMRS (462.675 MHz) calling frequencies.
- **NOAA Weather Radio Channels Template:** Built-in template (`builtin_noaa_wx_channels`) containing standard 7 NOAA Weather WX 1–7 channels (162.400–162.550 MHz).
- **Target Radio Supported Band & Mode Filtering:** When any template (built-in or user-uploaded) is processed, channels are filtered against the configured supported bands and modes of the selected target radio.
- **Intelligent Name Condensation Algorithm:** Intelligently condenses long channel names (e.g., `TYLER REPEATER NORTH`) using space/word boundaries and common radio abbreviations (`REPEATER` -> `RPT`, `NORTH` -> `N`, `EMERGENCY` -> `EMG`, `WEATHER` -> `WX`, `SIMPLEX` -> `SMP`) to fit target radio LCD character limits cleanly.

### 3.3 Route Resolution & Codeplug Summary Split View
When route planning completes, the system presents a dual-column summary:
- **Left Column (Route Information):** **Travel Corridor Cities & Cumulative Mileage** (numbered list of cities along the travel route with cumulative mileage from start), corridor width radius, total resolved travel mileage, highway polyline legs, and live RepeaterBook API status.
- **Right Column (Selected Channel Summary):** Total channels generated banner, frequency band breakdown (`10m`, `6m`, `2m`, `1.25m`, `70cm`, `GMRS`, `Airband`), special/template counts (`Calling`, `NOAA WX`, `Aviation CTAF`, `Preset Templates`, `Simplex`). Weather template channels are classified as `WX`, NOT `2m`.
- **Navigation Controls:** `← Back to Radio Selection` and `Review Codeplug Channels →`.

### 3.4 Dynamic Channel Tagging & DMR Talkgroup Duplication
- **Dynamic Channel Badge Tag Structure:**
  Each channel row displays dynamic badge chips to provide visual context:
  1. **Frequency Band Tag:** Categorizes the channel by frequency band (`10m`, `6m`, `2m`, `1.25m`, `70cm`, `GMRS`, `AIR`, `WX`) using frequency range matching (161.0–163.0 MHz is strictly reserved for `WX`).
  2. **Digital Mode Tag:** Appends a `DMR` badge for digital channels (DMR, C4FM/Fusion, D-STAR).
  3. **Group / Template Tag:** Displays template or special group badges (`CALL`, `SKYWARN`, `ARES`, `Preset`, or custom user template tag name).
  4. **Simplex Tag:** Appends a `Simplex` badge for non-repeater channels (`rxFreq == txFreq`).
- **DMR Talkgroup & TimeSlot Channel Duplicator:**
  - Clicking **"✏️ DMR TG"** next to a digital channel opens the DMR Talkgroup Editor Dialog.
  - **Auto-Fetch RadioID.net TGs**: Directly queries RadioID.net (`/api/repeaters/dmr`) for the repeater's official Color Code, TimeSlots, and Talkgroup list.
  - **Custom Individual Channel Naming**: Allows configuring a custom **Individual Channel Name** per Talkgroup entry, Base Channel Name, Color Code (0–15), Talkgroup ID, and TimeSlot (TS1 or TS2).
  - **Apply & Duplicate**: Replaces the single digital repeater channel in the codeplug with individual duplicated channel entries for each configured Talkgroup entry.

### 3.5 Radios & Programmer Configurations Manager
- **Brand & Model Selection:** Brand and Model dropdown selection.
- **"Add New Radio"**: Dialog to add new radio models or create new brands.
- **Unlock / Edit Hardware Specs Toggle**: Explicit toggle switch to unlock and edit active radio hardware parameters (Max Channels, Max Name Length, Allowed Symbols, Allowed Special Characters, Supported Bands, Supported Modes).
- **Programmer Tabs & Column Cell List Editor:**
  - Tabs per programmer type (`CHIRP`, `RT_SYSTEMS`, `VENDOR_CPS`, `GENERIC_CSV`).
  - Checkbox: `☑ Use Default Columns for [Programmer Name]`.
  - Cell List Editor with Header Name, **Cell Data Type** (`TEXT`, `NUMBER`, `CHECKBOX`, `DROPDOWN`), **Default Value**, **Edit**, **Move Up**, **Move Down**, **Delete**, and **Add Column Header** buttons.
  - **Save Radio Configuration** button persists all custom specs and column exporter definitions in user preferences.

### 3.6 Interactive OpenStreetMap Component
- **Dual-Mode Map Viewer:** Launched via the **View OpenStreetMap** action in both Route Corridor Mode and Proximity Ring Search Mode.
- **Proximity Ring Mode Visualization:** Renders 5 concentric distance ring circles (Ring 1 to Ring 5 with color-coded distance swatches), user center location marker, and repeater location pins.
- **Route Corridor Mode Visualization:** Renders origin, destination, and intermediate waypoint pins, highway polyline travel corridor path, and repeater pins along the corridor.

### 3.7 Radio-Specific Exporter Header Specifications
The Exporter Component formats hardware-constrained CSV codeplugs according to radio model specifications:
- **CHIRP (21 Columns):** `Location`, `Name`, `Frequency`, `Duplex`, `Offset`, `Mode`, `Tone`, `rToneFreq`, `cToneFreq`, `DtcsCode`, `DtcsPolarity`, `RxDtcsCode`, `CrossMode`, `Mode2`, `Power`, `Skip`, `Comment`, `URCALL`, `RPT1CALL`, `RPT2CALL`, `Digital Code`.
- **RT Systems BTECH DMR-6X2 (51 Columns):** 5-decimal frequencies (`146.52000`), `Receive Frequency` ... `APRS Channel`, `Comment`.
- **RT Systems Wouxun KG-UV980P & KG-1000G (18 Columns):** `Receive Frequency` ... `Tx Power`, `Scan Add`, `Compander`, `Scrambler`, `Comment`.
- **RT Systems Baofeng 5RM / UV-21R (19 Columns):** `Receive Frequency` ... `Scan Add`, `Busy Lock`, `Scrambler`, `Comment`, `Signal Code`, `PTTID`.
- **RT Systems Baofeng UV-5G Plus GMRS (19 Columns):** `Receive Frequency` ... `Scan Add`, `Busy Lock`, `FHSS`, `Signal Code`, `PTTID`, `Comment`.
- **RT Systems Alinco DR-735T (31 Columns):** `Receive Frequency` ... `Standby Color`, `Rx Color`, `Tx Color`, `Bank 1`–`10`, `Comment`.

---

## 4. User Preferences & Third-Party API Integration

- **Operator Identity:** Callsign (`W5CDN`), Operator Name (`W5CDN Operator`), DMR Radio ID (`3224901`).
- **RadioID.net Integration:**
  - **/api/users?callsign={callsign}:** Resolves operator Callsigns directly to official 7-digit DMR Radio IDs.
  - **/api/repeaters/dmr:** Queries DMR repeaters and auto-populates Color Codes, TimeSlots, and Talkgroups.
- **API Credentials:**
  - **RepeaterBook:** Single API Key (`apiKey`).
  - **RadioID.net:** Call Sign / Username (`username`) and API Key / Token (`apiKey`).
- **Graceful Feature Degradation & Offline Self-Healing:** If API credentials are missing or network calls time out, web-dependent features degrade gracefully to local sample data and cached coordinate files without crashing.

---

## 5. Engineering Guidelines for Performance, Security, Code Coverage, & Maintainability

To ensure RadioPlanner maintains high performance, security, high code coverage, and code maintainability across implementations:

### 5.1 Performance Guidelines
1. **Lazy Stream Processing:**
   - Use lazy collection/stream operations (`map`, `filter`, `distinct`) for processing large repeater datasets (e.g. >1,000 repeaters) to avoid temporary heap allocations.
2. **Spatial Geometry Pre-Filtering:**
   - Always perform Bounding Box coordinate pre-filtering before calculating Haversine or Cross-Track perpendicular distances to ensure $O(N)$ corridor matching efficiency.
3. **API Response Caching:**
   - Store state queries in local memory/disk caches to prevent redundant network requests when re-planning corridors across identical states.
4. **UI View Render Hygiene:**
   - Use memoization and immutable state objects for UI view state to avoid unnecessary re-render loops.

### 5.2 Security Guidelines
1. **Secrets & Credentials Isolation:**
   - Never hardcode user secrets, passwords, or personal tokens in source code files. Default fallback API keys must be isolated in dedicated resolver modules.
2. **Strict Input Sanitization:**
   - All user text inputs, imported CSV cells, and external API responses must pass through a sanitizer utility to strip control characters, sanitize HTML/SQL characters, and validate coordinate/frequency bounds.
3. **Path Traversal Protection:**
   - Validate file paths before performing file I/O operations to prevent directory traversal attacks.
4. **Exported Component Security:**
   - Restrict application component exports and validate all incoming/outgoing inter-process messages.

### 5.3 Code Coverage & Unit Testing Standards
1. **Tri-State Unit Test Requirement:**
   - Every domain engine module (Route Planner Engine, Airband Engine, Preset Template Processor, Codeplug Exporter, CSV Parser, Geocoding Engine, RadioID Client, Special Channels) must maintain automated unit tests evaluating:
     - **Good Data:** Standard valid inputs, frequencies, and coordinates.
     - **Bad Data:** Out-of-bounds frequencies, corrupted CSVs, missing coordinates.
     - **Missing Data:** Empty lists, null fields, offline timeouts.
2. **100% Core Logic Coverage:**
   - All frequency band filtering, channel name formatting, sequence ordering, and CSV exporter header generation must have dedicated unit test assertions.

### 5.4 Maintainability & Layer Separation Standards
1. **Strict Core Layer Separation:**
   - Business logic, domain models, synthesizers, and parsers must remain strictly inside the shared core domain layer.
   - UI views must contain only presentation logic and state binding.
2. **Immutable State Updates:**
   - Domain objects (`UserPreferences`, `Codeplug`, `RadioChannel`, `TargetRadioSpec`) are immutable data classes. Updates must return new sanitized instances.
3. **Explicit Interface Contracts:**
   - Public domain functions and cross-module boundaries must declare explicit type signatures.

---

## 6. Internal Data Representations & File Structure Schemas

### 6.1 Common Internal Representation (CIR) Architecture

RadioPlanner relies on a single, normalized **Common Internal Representation (CIR)** in memory:

```
+----------------------------------------------------------------------------------------------------+
|                                    CIR INGESTION PIPELINE                                          |
+----------------------------------------------------------------------------------------------------+
| Data Ingestion Sources:                                                                            |
| • RepeaterBook REST API JSON -> RepeaterRawDto -> ParsedRepeater                                   |
| • OurAirports Aviation CSV  -> AirfieldRecord -> AviationFrequency                                 |
| • RadioID.net API JSON      -> RadioIdRepeaterResult / RadioIdTalkgroupItem                        |
| • Imported Hardware CSVs    -> CsvParser                                                           |
| • Preset Templates JSON     -> PresetTemplateFile                                                  |
+----------------------------------------------------------------------------------------------------+
                                                │
                                                ▼
+----------------------------------------------------------------------------------------------------+
|                         COMMON INTERNAL REPRESENTATION (CIR) IN MEMORY                             |
|                                                                                                    |
| • Codeplug(name, channels: List<RadioChannel>, totalChannels)                                      |
| • RadioChannel(name, rxFreq, txFreq, offset, mode, power, ctcss, rxCtcss, dcs, lat, lon...)       |
+----------------------------------------------------------------------------------------------------+
                                                │
                                                ▼
+----------------------------------------------------------------------------------------------------+
|                        UNIFIED SYNTHESIS & PROCESSING ENGINES                                      |
|                                                                                                    |
| • RoutePlannerEngine (Cross-track geometry, proximity ring sorting, sequence position ordering)     |
| • DataSanitizer (Clamping, ASCII sanitization, LCD character length condensation)                   |
| • SpecialChannels (Built-in National Calling & NOAA Weather channel injection)                      |
+----------------------------------------------------------------------------------------------------+
                                                │
                                                ▼
+----------------------------------------------------------------------------------------------------+
|                        HARDWARE EXPORTER COMPONENT                                                 |
|                                                                                                    |
| Transforms CIR Codeplug into hardware-constrained CSVs according to TargetRadioSpec:              |
| • CHIRP CSV (21 cols)         • RT Systems BTECH DMR-6X2 (51 cols)   • Wouxun (18 cols)           |
| • Baofeng 5RM (19 cols)       • Baofeng UV-5G Plus (19 cols)          • Alinco DR-735T (31 cols)   |
+----------------------------------------------------------------------------------------------------+
```

Regardless of where channel data originates—whether fetched from RepeaterBook REST APIs, OurAirports CSV datasets, RadioID.net DMR lookups, imported CHIRP/RT Systems CSVs, or JSON Preset Templates—it is immediately parsed and converted into normalized CIR objects (`Codeplug` containing `RadioChannel` items). All synthesis engines (corridor geometry, proximity sorting, template merging, deduplication, and LCD name condensation) operate exclusively on CIR objects. When exporting, the Exporter Component transforms the CIR `Codeplug` into the hardware-constrained export format specified by `TargetRadioSpec`.

#### 1. `RadioChannel` (CIR Channel Model)
Represents an individual radio frequency channel entry in CIR memory:
- **`number`**: Integer channel slot index.
- **`name`**: Alphanumeric memory display tag (truncated to radio LCD limits).
- **`callsign`**: Optional repeater callsign or airfield identifier (e.g. `W5ETX`, `KTYR`).
- **`rxFreq`**: Float receive frequency in MHz (e.g. `146.94000`).
- **`txFreq`**: Float transmit frequency in MHz (e.g. `146.34000`).
- **`offset`**: Float frequency shift magnitude in MHz (e.g. `0.60000`).
- **`offsetDir`**: String direction (`"+"`, `"-"`, or `"off"`).
- **`mode`**: Channel operating mode (`ANALOG` or `DIGITAL`).
- **`power`**: Transmit power level (`HIGH`, `MID`, `LOW`).
- **`toneMode`**: Tone squelch configuration (`NONE`, `TONE`, `TSQL`, `DCS`).
- **`ctcss`**: String transmit CTCSS tone in Hz or `"None"` (e.g. `"88.5"`).
- **`rxCtcss`**: String receive CTCSS tone in Hz or `"None"`.
- **`dcs`**: String DCS digital code or `"None"` (e.g. `"023"`).
- **`rxDcs`**: String receive DCS code or `"None"`.
- **`dcsPolarity`**: DCS polarity (`"NN"`, `"NR"`, `"RN"`, `"RR"`).
- **`bandwidth`**: String bandwidth (`"25KHz"` or `"12.5KHz"`).
- **`city`**: Optional city or municipality location string (e.g. `"Tyler"`).
- **`state`**: Optional 2-letter state code (e.g. `"TX"`).
- **`lat` / `lon`**: Optional latitude and longitude coordinates.
- **`specialType`**: Channel classification (`CALLING`, `WX`, `AVIATION`, `GMRS`, `CUSTOM`).
- **`colorCode`**: Optional DMR Color Code integer (0–15).
- **`timeSlot`**: Optional DMR TimeSlot integer (1 or 2).
- **`dmrId`**: Optional 7-digit DMR Radio ID string.
- **`contact`**: Optional DMR talkgroup contact label.
- **`comment`**: Full explanatory comment string.

#### 2. `Codeplug`
Represents a synthesized hardware codeplug containing an ordered channel list:
- **`name`**: Title string (e.g. `"Tyler_TX-Jackson_MS-route-DM32UV"`).
- **`channels`**: Ordered list of `RadioChannel` entries.
- **`totalChannels`**: Total channel count integer.

#### 3. `TargetRadioSpec`
Defines the hardware constraints and CSV exporter rules for a target radio model:
- **`id`**: Unique string identifier (e.g. `"baofeng_5rm"`).
- **`description`**: Human-readable model description.
- **`maxChannels`**: Maximum channel memory capacity (e.g. `128`, `1000`, `4000`).
- **`maxNameLength`**: LCD display character limit (e.g. `6`, `7`, `8`, `12`, `16`).
- **`allowDots` / `allowSpaces`**: Boolean LCD display character rules.
- **`programmerType`**: Default programmer software (`CHIRP`, `RT_SYSTEMS`, `VENDOR_CPS`, `GENERIC_CSV`).
- **`columns`**: Ordered list of CSV header column strings.

#### 4. `UserPreferences`
Maintains persistent operator configuration and third-party API credentials:
- **`callsign`**: Operator callsign (e.g. `"W5CDN"`).
- **`operatorName`**: Operator name string.
- **`primaryDmrId`**: 7-digit DMR Radio ID string (e.g. `"3224901"`).
- **`repeaterBookCredentials`**: `ApiCredentials` object (API Key).
- **`radioIdCredentials`**: `ApiCredentials` object (Callsign & Key).
- **`timeFormat`**: `TWELVE_HOUR` or `TWENTY_FOUR_HOUR`.
- **`distanceUnit`**: `MILES` or `KILOMETERS`.
- **`language`**: Application language (`ENGLISH`, `SPANISH`, `FRENCH`, `GERMAN`).
- **`uploadedTemplates`**: List of user-uploaded `PresetTemplateFile` objects.

#### 5. `AirfieldRecord` & `AviationFrequency`
Represents OurAirports aeronautical database records:
- **`ident`**: ICAO/IATA airfield identifier (e.g. `"KTYR"`).
- **`name`**: Airfield title string (e.g. `"Tyler Pounds Regional Airport"`).
- **`latitude` / `longitude`**: Airfield GPS coordinates.
- **`municipality`**: City/Municipality name string.
- **`frequencies`**: List of `AviationFrequency` items (`type`: CTAF/TWR/GND/ATIS, `description`, `frequencyMhz`).

---

### 6.2 File Structure & Export Schemas

#### 1. CHIRP CSV File Schema (21 Columns)
```csv
Location,Name,Frequency,Duplex,Offset,Mode,Tone,rToneFreq,cToneFreq,DtcsCode,DtcsPolarity,RxDtcsCode,CrossMode,Mode2,Power,Skip,Comment,URCALL,RPT1CALL,RPT2CALL,Digital Code
1,TYLER146.94,146.94000,-,0.60000,FM,Tone,88.5,88.5,023,NN,023,None,,High,,Tyler TX Repeater,,,,0
```

#### 2. RT Systems CSV Schemas
- **BTECH DMR-6X2 (51 Columns):** 5-decimal frequency representation (`146.52000`), `Receive Frequency` through `APRS Channel`, `Comment`.
- **Wouxun KG-UV980P & KG-1000G (18 Columns):** `Receive Frequency`, `Transmit Frequency`, `Offset Frequency`, `Offset direction`, `Operating Mode`, `Show Name`, `Name`, `Tone Mode`, `CTCSS`, `Rx CTCSS`, `DCS`, `Rx DCS`, `DCS Polarity`, `Tx Power`, `Scan Add`, `Compander`, `Scrambler`, `Comment`.
- **Baofeng 5RM / UV-21R (19 Columns):** `Receive Frequency` ... `Scan Add`, `Busy Lock`, `Scrambler`, `Comment`, `Signal Code`, `PTTID`.
- **Baofeng UV-5G Plus GMRS (19 Columns):** `Receive Frequency` ... `Scan Add`, `Busy Lock`, `FHSS`, `Signal Code`, `PTTID`, `Comment`.
- **Alinco DR-735T (31 Columns):** `Receive Frequency` ... `Standby Color`, `Rx Color`, `Tx Color`, `Bank 1`–`10`, `Comment`.

#### 3. Preset Template JSON File Schema
```json
{
  "id": "builtin_calling_channels",
  "name": "National Calling Frequencies",
  "description": "Standard VHF, UHF, 1.25m, 6m, and GMRS national calling frequencies",
  "tagText": "CALLING",
  "tagColorHex": "#FFC107",
  "fileName": "calling_channels.csv",
  "rawCsvContent": "Channel Name,RX Frequency,TX Frequency,Mode,Power\n2m CALL,146.520,146.520,FM,High\n70cm CALL,446.000,446.000,FM,High"
}
```
