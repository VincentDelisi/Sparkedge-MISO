# ⚡ Sparkedge MISO

Implied **heat rate** and **spark spread** monitor for the MISO (Midcontinent)
power market.

Sparkedge MISO pulls MISO prices, load, and fuel mix plus natural-gas prices,
caches everything to SQLite, computes implied market heat rates and spark
spreads for three representative generating-unit classes, flags statistical
dislocations, and renders it all in a Streamlit dashboard — split cleanly into
**MISO North** and **MISO South** so the North/South congestion story is front
and center.

---

## What it does

**Data layer** (`gridstatus` + EIA)
- MISO **day-ahead hourly** and **5-minute real-time** LMP for 8 trading hubs:
  **Illinois, Indiana, Michigan, Minnesota** (North) and **Arkansas,
  Louisiana, Mississippi, Texas** (South).
- MISO **load**, **load forecast**, and **fuel mix** (guarded — see below).
- Natural gas from **EIA Henry Hub daily spot** (`RNGWHHD`). MISO has no free
  per-hub daily gas feed, so Henry Hub is the reference gas for every hub —
  South hubs use it directly, North hubs use it as a clearly labeled proxy
  (Chicago Citygate, the more natural North reference, isn't in the free EIA
  daily API).
- Everything cached to **SQLite** (idempotent upserts) so APIs aren't re-hit.
- Sleeps between calls + retry/backoff so a flaky pull never aborts a run.

**Compute layer**
- **Implied market heat rate** = power price ÷ gas price (MMBtu/MWh).
- **Spark spread** = power price − (unit heat rate × gas price) − VOM, for:
  - **6.8 HR** combined-cycle, **7.5 HR** combined-cycle, **10.5 HR** peaker.
- **Rolling 30-day, hour-of-day-conditioned mean & std** of the implied HR per
  hub (on log scale, to handle the fat right tail from scarcity pricing).
- **Flags** any interval where the current implied HR is more than **±2σ**
  from its same-hour trailing mean.

**Display layer** (Streamlit)
1. **Live money strip** — 8 hub cards grouped **"MISO North"** (Minnesota,
   Michigan, Illinois, Indiana) and **"MISO South"** (Arkansas, Louisiana,
   Mississippi, Texas), two rows of 4, showing which unit classes are
   currently in the money at each hub.
2. Implied-heat-rate time-series per hub with the **±2σ band** overlaid.
3. **Duck-curve** net-load chart for today with the **evening ramp
   highlighted**.
4. **Alerts panel** listing current heat-rate dislocations.

Every panel **degrades instead of crashing** — a down source just shows a
notice.

---

## Install

Requires Python 3.10–3.13 (gridstatus needs <3.13 for some deploy targets;
`runtime.txt` pins `python-3.12`).

```bash
cd miso-deploy
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# or install as a package (gives the `sparkedge-miso` console script):
pip install -e .
```

### EIA key (required for heat rates)

Henry Hub gas needs a free EIA API key. Without it, gas is unavailable and
implied heat rates / spark spreads show as n/a (prices, load, fuel mix, and
the duck curve still work).

```bash
cp .env.example .env      # then edit and set EIA_API_KEY=...
export EIA_API_KEY=your_key_here
```

Get a free key at [eia.gov/opendata](https://www.eia.gov/opendata/register.php).

---

## Usage

```bash
# 1) Seed the cache (~45 days -> enough to fill the 30-day rolling window)
python -m sparkedge_miso --backfill
python -m sparkedge_miso --backfill --days 60     # custom horizon

# 2) Live refresh of today's data
python -m sparkedge_miso --refresh

# 3) Launch the dashboard
python -m sparkedge_miso --serve
#   (equivalently: streamlit run sparkedge_miso/app.py)

# Diagnostics
python -m sparkedge_miso --status
```

The dashboard also has a **"Refresh today's data"** button in the sidebar.

---

## Configuration

All tunables live in [`sparkedge_miso/config.py`](sparkedge_miso/config.py):

- **`HUBS`** — the 8 MISO trading-hub labels and gridstatus `Location` node
  ids (`*.HUB`), each tagged `region="North"|"South"` for the money-strip
  grouping. `HUBS_NORTH` / `HUBS_SOUTH` are precomputed convenience lists.
- **`UNIT_CLASSES`** — the three representative unit heat rates (and optional
  VOM) — unchanged from the ERCOT lineage, generic across ISOs.
- **`Settings`** — rolling window (30d), σ threshold (2.0), inter-call sleeps,
  retries, gas-source preference (`eia`), backfill horizon, and
  **`display_tz`** (`"EST"` — MISO has no DST, unlike ERCOT's `US/Central`).
  Many are env-overridable (see `.env.example`).

---

## Package layout

```
miso-deploy/
├── pyproject.toml
├── requirements.txt
├── .env.example
├── README.md
├── BUILD_NOTES.md
├── smoke_test.py          # seeded-data validation script (see below)
└── sparkedge_miso/
    ├── __init__.py
    ├── __main__.py       # enables `python -m sparkedge_miso`
    ├── config.py         # 8 MISO hubs, unit heat rates, settings, display_tz
    ├── storage.py        # SQLite cache (idempotent upserts, safe reads)
    ├── data.py           # gridstatus + EIA fetchers (retry, rate-limit, graceful)
    ├── compute.py        # heat rates, spark spreads, rolling stats, alerts, net load
    ├── cli.py            # --backfill / --refresh / --status / --serve
    ├── ssl_compat.py      # optional MISO-scoped TLS relaxation
    └── app.py            # Streamlit dashboard (4 panels, 8-hub North/South strip)
```

---

## Notes & assumptions

- **Gas:** MISO has no free per-hub daily gas feed, so **EIA Henry Hub** daily
  spot is the reference gas for every hub — South directly, North as a labeled
  proxy. An `EIA_API_KEY` is required for heat rates.
- **Real-time backfill** is limited to the most recent 7 days by default
  (5-min RT data is large); day-ahead + gas backfill the full horizon.
- **Heat rate** uses same-day gas (daily grain) joined to each price interval.
- Spark spreads include a small VOM adder per unit class (editable in config);
  set VOM to 0 for a pure clean-spark comparison.
- All local times are **EST** (MISO does not observe DST, so this is a fixed
  offset, not `US/Eastern`).
- **MISO's `get_lmp` returns Energy/Congestion/Loss** components alongside
  LMP (unlike ERCOT's `get_spp`, which is LMP-only) — these are persisted in
  the `lmp` table.

Data: MISO via [gridstatus](https://github.com/gridstatus/gridstatus);
natural gas via the [EIA Open Data API](https://www.eia.gov/opendata/).

---

## Troubleshooting

**`SSL: CERTIFICATE_VERIFY_FAILED` on load / fuel-mix (empty duck curve).**
Some networks (corporate proxies, VPNs, HTTPS-inspecting antivirus) re-sign
the TLS chain for MISO's public endpoints with a certificate Python doesn't
trust. Enable the scoped TLS relaxation and re-run:

```bash
# macOS / Linux / Git Bash
export SPARKEDGE_INSECURE_SSL=1

# Windows PowerShell
$env:SPARKEDGE_INSECURE_SSL = "1"
```

Then `python -m sparkedge_miso --backfill` (or --refresh). This disables TLS
verification **for MISO hosts only**; every other HTTPS request stays
verified. The proper alternative is to install your proxy's root CA into the
system trust store.

**Windows: `python` opens the Microsoft Store / `venv` won't create.**
Windows' App-execution-alias stub is shadowing real Python. Use `py` instead
(`py -m venv .venv`), or turn off the aliases in Settings -> Apps -> Advanced
app settings -> App execution aliases (`python.exe`, `python3.exe`).

**Windows PowerShell: `Activate.ps1` blocked ("running scripts is disabled").**
Skip activation and call the venv Python directly:
`.venv\Scripts\python.exe -m sparkedge_miso --serve`.
