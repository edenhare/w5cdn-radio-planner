# 14. RepeaterBook Integration, Multi-Tier Fallback, and Date-Versioned Offline State Caching

## Status
Accepted

## Context
Highway corridor and proximity codeplug generation relies on accurate, up-to-date repeater directories. However:
1. **API Authentication and Rate Limits:** The RepeaterBook REST API requires specific authentication headers (`X-RB-App-Token`) and an exact application `User-Agent` (e.g., `RepeaterBook Python Client/0.6.0 (+micael@jarniac.dev)` for App #114). Generic requests or missing tokens trigger HTTP 403 `ua_mismatch` errors. Furthermore, Cloudflare and RepeaterBook apply strict rate limiting (HTTP 429) to repeated queries.
2. **Offline Field Reliability:** Operators frequently plan trips and program radios in the field without dependable Internet connectivity. RadioPlanner must not fail or halt when offline.
3. **Data Freshness and State Caching:** Operators need downloaded repeater data saved locally in `~/.config/radioplanner/data/repeaterbook/` organized by geographic state and timestamped by date (`rb_STATE_DATE.json`). This enables operators to audit coverage freshness, refresh individual states on demand, and automatically self-heal from local disk cache when offline.

## Decision
1. **Authenticated REST Client (`RepeaterBookProvider`):**
   - Outbound requests to `https://www.repeaterbook.com/api/export.php` use `X-RB-App-Token: <token>` and `User-Agent: RepeaterBook Python Client/0.6.0 (+micael@jarniac.dev)`.
   - API tokens are discovered hierarchically: explicit constructor argument -> User Preferences (`~/.config/radioplanner/preferences.json`) -> `REPEATERBOOK_API_KEY` environment variable -> local credential file.
2. **Multi-Tier Retrieval Hierarchy:**
   - **Tier 1 (In-Memory Cache):** Instant coordinate lookup for identical calls within the active process session.
   - **Tier 2 (Live REST API):** Live queries executed when network and token are available.
   - **Tier 3 (Date-Versioned Disk Cache):** When offline, missing a token, or encountering an HTTP error (403/429/timeout), the provider automatically scans `~/.config/radioplanner/data/repeaterbook/` for `rb_{STATE}_{DATE}.json` files, selecting the newest date file for each state.
   - **Tier 4 (Built-in Fallback Dataset):** If no disk cache exists, falls back gracefully to embedded `OFFLINE_REPEATERS` with a clear diagnostic notice.
3. **Date-Stamped File Architecture (`rb_STATE_DATE.json`):**
   - Every live export partitions received records by state and saves them as `rb_{STATE}_{DATE}.json` (e.g., `rb_TX_2026-10-20.json`), where `DATE` is formatted as `YYYY-MM-DD`.
   - Full regional exports are simultaneously recorded as `rb_ALL_{DATE}.json`.
   - States and Canadian provinces are normalized to standard two-letter postal abbreviations or uppercase names using `resolve_state_code()`.
   - The provider exposes `list_cached_state_files()` to return state codes, dates, channel counts, and paths for auditing and refresh management.
4. **UI Diagnostic Banners:**
   - When running against preloaded or cached data due to API fallback, the CLI wizard displays a distinct warning notice directly above the route split summary rather than failing silently.

## Consequences
- **Resilient Offline Operation:** RadioPlanner operates seamlessly in disconnected environments, utilizing the most recently downloaded state data.
- **Rate Limit Protection:** Local caching prevents redundant hits to the RepeaterBook API and avoids Cloudflare 429 bans.
- **Transparent Auditing:** Operators can inspect the age and size of cached state files and refresh them intentionally.
- **Full Test Coverage:** Validated by unit tests in `tests/core/test_repeaterbook.py` and `tests/cli/test_wizard.py`.
