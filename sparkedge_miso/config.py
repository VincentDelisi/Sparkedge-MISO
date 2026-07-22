"""Central configuration for Sparkedge MISO.

Everything that a user might reasonably want to tune lives here: which MISO
trading hubs to monitor, the representative generating-unit heat rates used for
spark-spread economics, gas-price source wiring, rolling-window statistics, and
API/rate-limit behaviour.

Values can be overridden with environment variables (see ``Settings``) so the
package works both as a checked-in config file and in a 12-factor deployment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# Trading hubs
# --------------------------------------------------------------------------- #
# MISO exposes its trading hubs as settlement-point aggregates. ``node`` is the
# exact identifier gridstatus returns in the "Location" column of get_lmp;
# ``label`` is the friendly name used in the UI. MISO's footprint splits
# cleanly into a North/Central group and a South (post-2013 integration) group
# with a well-known North/South congestion story, so each hub also carries a
# ``region`` tag ("North" | "South") the UI uses to group the money strip.
#
# Gas mapping (per-hub, EIA-free): both series are free via EIA (the same
# EIA_API_KEY the ERCOT app already used) -- NO OilPriceAPI needed for MISO.
#   - South hubs (Arkansas, Louisiana, Mississippi, Texas) sit Gulf-adjacent,
#     so Henry Hub (EIA series RNGWHHD) is the *direct* marginal gas reference:
#     gas_region="HENRY_HUB", gas_label="Henry Hub (EIA)".
#   - North hubs (Minnesota, Michigan, Illinois, Indiana) clear more often on
#     Chicago Citygate, but Chicago Citygate does not have a free EIA *daily*
#     series (only Henry Hub RNGWHHD does) -- the same limitation ERCOT hit
#     for its non-Houston hubs. So North hubs are wired to Henry Hub as a
#     clearly *labeled proxy*: gas_region="HENRY_HUB",
#     gas_label="Henry Hub (EIA) — proxy (Chicago Citygate not sourced)".
#     TODO: swap the North proxy for a real Chicago Citygate feed (EIA weekly
#     series or a paid NGI feed) if/when one is wired up; the Hub.gas_* fields
#     and _gas_for_hub machinery already support a per-hub source swap.
#   Since every hub uses source="eia"/region="HENRY_HUB", the oilpriceapi/Waha
#   basis branch in _gas_for_hub simply never triggers for MISO -- it's kept
#   intact (harmless) in case a future hub needs it.
@dataclass(frozen=True)
class Hub:
    label: str          # e.g. "Illinois"
    node: str           # e.g. "ILLINOIS.HUB"
    gas_region: str     # gas storage-region label, e.g. "HENRY_HUB"
    description: str = ""
    gas_source: str = "eia"          # "eia" | "oilpriceapi"
    gas_label: str = "Henry Hub (EIA) — proxy"  # human string for the UI
    region: str = "North"            # "North" | "South" -- money-strip grouping


HUBS: list[Hub] = [
    # --- MISO North (Minnesota, Michigan, Illinois, Indiana) --- #
    Hub(
        label="Minnesota",
        node="MINN.HUB",
        gas_region="HENRY_HUB",
        description="MISO Minnesota trading hub (MINN.HUB)",
        gas_source="eia",
        gas_label="Henry Hub (EIA) — proxy (Chicago Citygate not sourced)",
        region="North",
    ),
    Hub(
        label="Michigan",
        node="MICHIGAN.HUB",
        gas_region="HENRY_HUB",
        description="MISO Michigan trading hub (MICHIGAN.HUB)",
        gas_source="eia",
        gas_label="Henry Hub (EIA) — proxy (Chicago Citygate not sourced)",
        region="North",
    ),
    Hub(
        label="Illinois",
        node="ILLINOIS.HUB",
        gas_region="HENRY_HUB",
        description="MISO Illinois trading hub (ILLINOIS.HUB)",
        gas_source="eia",
        gas_label="Henry Hub (EIA) — proxy (Chicago Citygate not sourced)",
        region="North",
    ),
    Hub(
        label="Indiana",
        node="INDIANA.HUB",
        gas_region="HENRY_HUB",
        description="MISO Indiana trading hub (INDIANA.HUB)",
        gas_source="eia",
        gas_label="Henry Hub (EIA) — proxy (Chicago Citygate not sourced)",
        region="North",
    ),
    # --- MISO South (Arkansas, Louisiana, Mississippi, Texas) --- #
    Hub(
        label="Arkansas",
        node="ARKANSAS.HUB",
        gas_region="HENRY_HUB",
        description="MISO Arkansas trading hub (ARKANSAS.HUB)",
        gas_source="eia",
        gas_label="Henry Hub (EIA)",
        region="South",
    ),
    Hub(
        label="Louisiana",
        node="LOUISIANA.HUB",
        gas_region="HENRY_HUB",
        description="MISO Louisiana trading hub (LOUISIANA.HUB)",
        gas_source="eia",
        gas_label="Henry Hub (EIA)",
        region="South",
    ),
    Hub(
        label="Mississippi",
        node="MS.HUB",
        gas_region="HENRY_HUB",
        description="MISO Mississippi trading hub (MS.HUB)",
        gas_source="eia",
        gas_label="Henry Hub (EIA)",
        region="South",
    ),
    Hub(
        label="Texas",
        node="TEXAS.HUB",
        gas_region="HENRY_HUB",
        description="MISO Texas trading hub (TEXAS.HUB)",
        gas_source="eia",
        gas_label="Henry Hub (EIA)",
        region="South",
    ),
]

HUBS_BY_LABEL: dict[str, Hub] = {h.label: h for h in HUBS}
HUBS_BY_NODE: dict[str, Hub] = {h.node: h for h in HUBS}
HUBS_NORTH: list[Hub] = [h for h in HUBS if h.region == "North"]
HUBS_SOUTH: list[Hub] = [h for h in HUBS if h.region == "South"]


# --------------------------------------------------------------------------- #
# Representative generating-unit classes
# --------------------------------------------------------------------------- #
# Heat rate is expressed in MMBtu/MWh. Spark spread for a given unit is:
#     spark = power_price - (unit_heat_rate * gas_price) - vom
# A unit is "in the money" when its spark spread is positive.
@dataclass(frozen=True)
class UnitClass:
    key: str            # short id used in the db / config
    label: str          # friendly name
    heat_rate: float    # MMBtu/MWh
    vom: float = 0.0     # variable O&M adder in $/MWh (optional)
    color: str = "#888888"


UNIT_CLASSES: list[UnitClass] = [
    UnitClass(
        key="cc_68",
        label="6.8 HR Combined-Cycle",
        heat_rate=6.8,
        vom=2.0,
        color="#2ca02c",
    ),
    UnitClass(
        key="cc_75",
        label="7.5 HR Combined-Cycle",
        heat_rate=7.5,
        vom=2.5,
        color="#1f77b4",
    ),
    UnitClass(
        key="peaker_105",
        label="10.5 HR Peaker",
        heat_rate=10.5,
        vom=4.5,
        color="#d62728",
    ),
]

UNIT_CLASSES_BY_KEY: dict[str, UnitClass] = {u.key: u for u in UNIT_CLASSES}


# --------------------------------------------------------------------------- #
# Runtime settings (env-overridable)
# --------------------------------------------------------------------------- #
def _default_db_path() -> str:
    # Store the cache next to the package by default so it survives restarts.
    root = Path(os.environ.get("SPARKEDGE_HOME", Path.home() / ".sparkedge_miso"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "sparkedge_miso.db")


@dataclass
class Settings:
    # --- storage ---
    db_path: str = field(default_factory=_default_db_path)

    # --- rolling statistics ---
    rolling_window_days: int = 30      # window for HR mean / std
    sigma_threshold: float = 2.0       # dislocation flag threshold (in std devs)
    min_periods_frac: float = 0.5      # min fraction of window needed for a stat
    hod_min_samples: int = 10          # min *same-hour* obs before a band/z-score
                                       # is emitted (hour-of-day conditioned)

    # --- API rate limiting ---
    # gridstatus already sleeps between paginated calls; we add our own inter-call
    # sleep on top. MISO's public API is friendlier than CAISO OASIS, but we keep
    # the knobs so behaviour is tunable.
    oasis_sleep_seconds: int = 3       # passed to gridstatus get_lmp
    inter_call_sleep_seconds: float = 2.0  # our own sleep between distinct pulls
    max_retries: int = 3
    retry_backoff_seconds: float = 10.0

    # --- display timezone ---
    # MISO operates on a fixed EST offset and does NOT observe DST (unlike
    # ERCOT's "US/Central"), so a plain IANA zone like "US/Eastern" would be
    # wrong for half the year. gridstatus already returns tz-aware timestamps
    # in EST for MISO; we display in the same fixed offset. pandas accepts the
    # literal "EST" as a fixed-offset zone (equivalent to "Etc/GMT+5").
    display_tz: str = "EST"

    # --- SSL handling ---
    # Some networks (corporate proxies, HTTPS-inspecting antivirus, certain VPNs)
    # break certificate validation for the public data endpoints gridstatus uses.
    # Symptom:
    #   SSL: CERTIFICATE_VERIFY_FAILED ... self-signed certificate in chain.
    # When True, we relax TLS verification so load / fuel-mix (and the duck curve)
    # work on those networks. Off by default; set env SPARKEDGE_INSECURE_SSL=1 to
    # enable.
    insecure_ssl_caiso: bool = field(
        default_factory=lambda: os.environ.get("SPARKEDGE_INSECURE_SSL", "")
        .strip().lower() in {"1", "true", "yes", "on"}
    )

    # --- EIA (Henry Hub) ---
    # Henry Hub daily spot: route natural-gas/pri/fut, series RNGWHHD.
    eia_api_key: str | None = field(
        default_factory=lambda: os.environ.get("EIA_API_KEY")
    )
    eia_henry_hub_series: str = "RNGWHHD"
    eia_route: str = "natural-gas/pri/fut"

    # --- gas price source preference ---
    # MISO has no free per-hub daily gas feed, so Henry Hub (EIA) is the
    # reference gas for every hub (South directly, North as a labeled proxy).
    # "eia" -> use Henry Hub as the primary reference gas.
    gas_source_primary: str = "eia"

    # --- OilPriceAPI (Waha / Permian gas, used for HB_WEST) ---
    # Free tier: 200 req/month, 10/min after the 7-day trial. We only pull the
    # daily "latest" quote (fits comfortably in the free quota), and treat any
    # historical backfill as optional/best-effort -- see data.fetch_gas_waha.
    oilpriceapi_key: str = field(
        default_factory=lambda: os.environ.get("OILPRICEAPI_KEY", "")
    )
    oilpriceapi_waha_code: str = "NATURAL_GAS_WAHA"

    # --- backfill defaults ---
    backfill_days: int = 45            # enough to seed a 30d rolling window

    def __post_init__(self) -> None:
        env = os.environ
        if "SPARKEDGE_DB_PATH" in env:
            self.db_path = env["SPARKEDGE_DB_PATH"]
        if "SPARKEDGE_ROLLING_DAYS" in env:
            self.rolling_window_days = int(env["SPARKEDGE_ROLLING_DAYS"])
        if "SPARKEDGE_SIGMA" in env:
            self.sigma_threshold = float(env["SPARKEDGE_SIGMA"])
        if "SPARKEDGE_HOD_MIN_SAMPLES" in env:
            self.hod_min_samples = int(env["SPARKEDGE_HOD_MIN_SAMPLES"])
        if "SPARKEDGE_GAS_SOURCE" in env:
            self.gas_source_primary = env["SPARKEDGE_GAS_SOURCE"].lower()
        if "SPARKEDGE_OASIS_SLEEP" in env:
            self.oasis_sleep_seconds = int(env["SPARKEDGE_OASIS_SLEEP"])
        if "OILPRICEAPI_KEY" in env:
            self.oilpriceapi_key = env["OILPRICEAPI_KEY"]


# A module-level singleton is convenient for the app; callers may also build
# their own Settings() for tests.
SETTINGS = Settings()
