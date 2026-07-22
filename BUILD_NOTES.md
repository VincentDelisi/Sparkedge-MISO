# Sparkedge MISO — Build Notes

Cloned the proven Sparkedge **ERCOT (Texas)** package into a standalone
Sparkedge **MISO (Midcontinent)** app. Same architecture (Streamlit +
gridstatus + SQLite; implied heat rate / spark spread / duck curve / alerts),
retargeted from 4 ERCOT trading hubs to 8 MISO trading hubs, and rebuilt per
`/home/user/workspace/MISO_BUILD_SPEC.md`.

Source (reference, not modified): `/home/user/workspace/ercot-deploy/`.
Destination (this package): `/home/user/workspace/miso-deploy/`.

## Changes

### Package rename
- `sparkedge_ercot/` → `sparkedge_miso/`; every `sparkedge_ercot` reference
  updated across `__init__.py`, `__main__.py`, `cli.py`, `app.py`'s
  `streamlit run` fallback absolute-import path, `start.sh`, `pyproject.toml`,
  `.env.example`.
- `assets/ercot_logo.png` → `assets/sparkedge_logo.png` (same generic
  Sparkedge "S" mark — the image was never ERCOT-specific artwork, so the
  visual theme is unchanged; only the filename was made ISO-neutral).

### config.py
- `HUBS` replaced with the **8 MISO trading hubs**: `ILLINOIS.HUB`,
  `INDIANA.HUB`, `MICHIGAN.HUB`, `MINN.HUB` (North group) and `ARKANSAS.HUB`,
  `LOUISIANA.HUB`, `MS.HUB`, `TEXAS.HUB` (South group), each with a friendly
  label (Illinois, Indiana, Michigan, Minnesota, Arkansas, Louisiana,
  Mississippi, Texas).
- New `Hub.region` field (`"North"|"South"`) plus module-level `HUBS_NORTH` /
  `HUBS_SOUTH` lists for the money-strip grouping.
- Gas mapping: **South hubs** → `gas_region="HENRY_HUB"`,
  `gas_label="Henry Hub (EIA)"` (direct — Gulf-adjacent, Henry Hub is the
  right marginal gas). **North hubs** → same `gas_region="HENRY_HUB"` but
  `gas_label="Henry Hub (EIA) — proxy (Chicago Citygate not sourced)"`
  (labeled proxy — Chicago Citygate isn't in the free EIA daily API). All 8
  hubs use `gas_source="eia"`; no OilPriceAPI/Waha wiring for MISO (the
  `oilpriceapi` branch in `_gas_for_hub` is simply never triggered — kept
  intact, harmless).
- Added `Settings.display_tz: str = "EST"` — MISO does not observe DST
  (unlike ERCOT's `US/Central`), so a plain IANA zone would be wrong for half
  the year; pandas accepts the literal `"EST"` as a fixed offset.
- DB / `SPARKEDGE_HOME` defaults → `.sparkedge_miso` / `sparkedge_miso.db`.
- Kept the `insecure_ssl_caiso` and `oasis_sleep_seconds` field names
  (functional, referenced elsewhere) but they now govern MISO pulls.

### data.py
- Uses `gridstatus.MISO()` (was `Ercot()`); handle method renamed `_miso`.
- **LMP** via `get_lmp(date, end, market=..., locations=[8 hub node
  strings])` — NOT `get_spp` (that's ERCOT-only). Market strings:
  `DAY_AHEAD_HOURLY`, `REAL_TIME_5_MIN` (MISO RT is 5-minute, not 15).
- MISO's `get_lmp` returns `Energy`/`Congestion`/`Loss` columns alongside
  `LMP` — these are now populated in `upsert_lmp` rows (ERCOT's `get_spp` has
  no such breakdown, so the ERCOT version passed `None` for all three).
- `fetch_load` / `fetch_load_forecast` / `fetch_fuel_mix` each wrapped in
  their own `try/except`, logging a warning and returning 0 rows on failure,
  since MISO's gridstatus method shapes are less battle-tested than ERCOT's —
  this is graceful degradation, not a crash.
- **Removed** the OilPriceAPI/Waha fetcher (`fetch_gas_waha`) entirely — MISO
  doesn't need it (spec: "No OilPriceAPI needed"). `refresh_today` /
  `backfill` no longer call it or track a `gas_waha` total.
- `refresh_today` / `backfill` retargeted: RT uses `REAL_TIME_5_MIN`; both use
  `settings.display_tz` instead of a hardcoded `"US/Central"`.

### compute.py
- **No logic changes** other than timezone, per spec. Every hardcoded
  `"US/Central"` (5 occurrences: `_gas_series`, `heat_rate_series`,
  `_add_rolling_stats`, `net_load_today`, `evening_ramp`) replaced with
  `self.settings.display_tz` (or the module-level `SETTINGS.display_tz` in
  the one `@staticmethod`, `evening_ramp`, which has no `self`).
- The **hod_min_samples band/alert fix** (hour-of-day-conditioned, log-scale
  rolling ±2σ band with a sample-count floor instead of a fraction-of-window
  floor) and the **per-hub gas machinery** (`_gas_for_hub`'s Waha-basis
  fallback structure) are preserved exactly, unchanged in logic — only
  comments were lightly reworded to describe the MISO context accurately.

### app.py
- Title/subtitle → "Sparkedge MISO" / "Implied heat rates & spark spreads
  across 8 MISO hubs — North: Minnesota · Michigan · Illinois · Indiana —
  South: Arkansas · Louisiana · Mississippi · Texas"; logo
  `sparkedge_logo.png`; `page_title` and sidebar title updated.
- Market radio: "Day-Ahead" → `DAY_AHEAD_HOURLY`, **"Real-Time 5-min"** (was
  "Real-Time 15-min") → `REAL_TIME_5_MIN`.
- `HUB_COLORS` rekeyed to the 8 hub labels — cool blues/greens for North,
  warm oranges/reds for South, reinforcing the North/South story visually.
- **Money strip is the key layout change.** `panel_money_strip` no longer
  does `st.columns(len(snap))` (which would squeeze 8 cards into one
  unreadable row). It now:
  1. Builds a `hub label -> snapshot row` lookup.
  2. Renders a **"MISO North"** subheader + `st.columns(4)` for Minnesota,
     Michigan, Illinois, Indiana.
  3. Renders a **"MISO South"** subheader + `st.columns(4)` for Arkansas,
     Louisiana, Mississippi, Texas.
  4. A shared `_hub_card()` helper (factored out of the old inline loop body)
     renders each card identically in either group — same metric, gas-label
     caption, ITM lights, and dislocation warning as before.
- All `US/Central` → `SETTINGS.display_tz`; "CT" labels → "EST" (money-strip
  timestamp, duck-curve x-axis title and ramp-window annotation, alerts table
  column header).
- Green/red ITM legend in `panel_money_strip` kept as required.

### ssl_compat.py
- Scoped-TLS host list now targets `misoenergy.org` (was `ercot.com`; kept
  `caiso.com` harmlessly, matching the ERCOT package's pattern of retaining
  the original CAISO host).
- Docstring/log messages reworded from CAISO/ERCOT to MISO.

### storage.py
- Schema comments updated (RT market `REAL_TIME_5_MIN`, MISO hub labels).
  Schema itself unchanged — the same tables work for MISO (energy/congestion/
  loss columns already existed in the `lmp` table; MISO simply populates them
  where ERCOT left them `NULL`).

### Deploy config
- `start.sh`, `pyproject.toml` (name `sparkedge-miso`, package, script),
  `README.md`, `.env.example` all retargeted to `sparkedge_miso`.
- `Procfile` / `railway.json` reference `start.sh` (unchanged).
- `runtime.txt` stays `python-3.12` (gridstatus needs <3.13) per spec.

## Validation

- **AST parse**: every `.py` file under `sparkedge_miso/` parses cleanly
  (`ast.parse` on `__init__.py`, `__main__.py`, `app.py`, `cli.py`,
  `compute.py`, `config.py`, `data.py`, `ssl_compat.py`, `storage.py`).
- **Dry import**: `cd miso-deploy && python -c "from sparkedge_miso import
  compute, config"` succeeds on the sandbox's Python 3.14 (gridstatus is not
  installed / cannot install on 3.14 — expected and fine, because the
  `gridstatus` import lives entirely inside `DataService._miso()`, i.e. it is
  lazy, exactly like the ERCOT package's `_ercot()`). `data.py` itself also
  imports cleanly on its own since it has no top-level `gridstatus` import.
- **Seeded-data smoke test** (`smoke_test.py`, left in place per spec): seeds
  the SQLite storage with 40 days of synthetic Henry Hub gas plus synthetic
  day-ahead hourly LMP for all 8 MISO hubs (keyed by `hub.label`, matching the
  storage `hub` column), then runs `Analytics.heat_rate_series` and
  `Analytics.latest_snapshot` and prints `implied_hr` + `gas_label` per hub.
  See the run output captured in the parent agent's task report; all 8 hubs
  produced a non-null `implied_hr` and a populated `gas_label`.

## gridstatus methods guarded for MISO

`get_load`, `get_load_forecast`, and `get_fuel_mix` are each wrapped in their
own `try/except` in `data.py` (ERCOT's equivalents were not individually
guarded). This was a deliberate MISO-specific hardening per the spec's
"gracefully degrade rather than crash" instruction — MISO's gridstatus surface
for these three methods is less exercised than ERCOT's in practice, so a
signature drift or upstream failure now logs a warning and returns 0 rows
instead of raising.
