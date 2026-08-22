"""Gold layer: DuckDB star schema + analytics-ready parquet exports.

Grains
------
- fact_orbital_inventory : run_date x regime x object_type (on-orbit population)
- fact_spatial_density   : run_date x 25 km band  (counts, debris, density, HHI)
- fact_conjunction_events: one row per SOCRATES event (regime-enriched)
- fact_catalog_growth    : one row per day since 1957 (+ format-era classification)

Population policy: inventory/density use the SATCAT on-orbit population binned
by its own APOGEE/PERIGEE columns (34k objects vs GP-only 19.6k). The GP
propagation enriches dim_space_object with fresh-epoch flags.
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, timezone

import duckdb
import numpy as np
import pandas as pd

from src.analytics.clustering import build_band_clusters
from src.analytics.forecast import build_forecast_table, forecast_catalog
from src.analytics.metrics import foster_pc_numeric, hhi
from src.modeling.operators import attribute_operator, build_dim_operator, owner_to_nation
from src.transformation.shells import EARTH_RADIUS_KM, REGIME_SHELLS, altitude_band, regime_shell
from src.utils.paths import GOLD_DIR, GOLD_EXPORTS_DIR, SILVER_DIR

# Catalog-format eras (kickstart narrative):
#   5-digit        : before Alpha-5 format existed (pre May 2020)
#   alpha5-capable : format existed but catalog numbers stayed < 100000
#   6-digit        : numbering crossed 100000 on 2026-07-11 ("Saramago")
ALPHA5_SINCE = pd.Timestamp("2020-05-01")
SIX_DIGIT_SINCE = pd.Timestamp("2026-07-11")


def _shell_volume_km3(lower_alt_km: float, upper_alt_km: float) -> float:
    ri, ro = EARTH_RADIUS_KM + lower_alt_km, EARTH_RADIUS_KM + upper_alt_km
    return 4.0 / 3.0 * math.pi * (ro**3 - ri**3)


def build_dim_shells() -> pd.DataFrame:
    rows = []
    for shell_id, (name, low, high) in enumerate(REGIME_SHELLS, start=1):
        rows.append({
            "shell_id": shell_id,
            "regime": name,
            "lower_km": low,
            "upper_km": high,
            "shell_volume_km3": _shell_volume_km3(low, high if math.isfinite(high) else 1_000_000.0),
        })
    return pd.DataFrame(rows)


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    days = pd.date_range(start.normalize(), end.normalize(), freq="D", name="date_key")
    df = pd.DataFrame({"date_key": days})
    df["year"] = df["date_key"].dt.year
    df["quarter"] = df["date_key"].dt.quarter
    df["month"] = df["date_key"].dt.month
    # Solar Cycle 25 heuristic phase labels (peak window 2024-2027, NOAA SWPC)
    def phase(y: int) -> str:
        if y <= 2020:
            return "SC25-minimum"
        if y <= 2023:
            return "SC25-ascending"
        if y <= 2027:
            return "SC25-maximum"
        return "SC25-declining"
    df["solar_cycle_phase"] = df["date_key"].dt.year.map(phase)
    return df


def build_dim_space_object(satcat: pd.DataFrame, gp: pd.DataFrame) -> pd.DataFrame:
    df = satcat.rename(columns={
        "OBJECT_NAME": "name",
        "OBJECT_ID": "intl_designator",
        "NORAD_CAT_ID": "object_id",
        "OBJECT_TYPE": "object_type",
        "OPS_STATUS_CODE": "operational_status",
        "OWNER": "owner_code",
        "RCS": "rcs_size_m2",
        "PERIOD": "period_min",
        "INCLINATION": "inclination_deg",
        "APOGEE": "satcat_apogee_km",
        "PERIGEE": "satcat_perigee_km",
        "DATA_STATUS_CODE": "data_status",
        "ORBIT_CENTER": "orbit_center",
        "ORBIT_TYPE": "orbit_type",
    })
    df["nation"] = owner_to_nation(df["owner_code"])
    df["operator_id"] = attribute_operator(df["name"])
    df["launch_date"] = df["LAUNCH_DATE"]
    df["decay_date"] = df["DECAY_DATE"]

    # regime from SATCAT's own apogee/perigee where present
    mean_alt = (df["satcat_apogee_km"] + df["satcat_perigee_km"]) / 2.0
    df["mean_altitude_km"] = mean_alt
    df["band_25km"] = mean_alt.map(lambda a: altitude_band(a) if pd.notna(a) else None).astype("Int64")
    df["regime"] = mean_alt.map(lambda a: regime_shell(a) if pd.notna(a) else None)

    # GP enrichment: freshest propagated elements flag
    gp_fresh = (
        gp[gp["is_valid"]]
        .assign(epoch_date=lambda d: pd.to_datetime(d["epoch_utc"]).dt.tz_localize(None))
        .loc[:, ["norad_cat_id", "epoch_utc", "is_stale", "subpoint_lat_deg", "subpoint_lon_deg"]]
        .rename(columns={"norad_cat_id": "object_id"})
        .drop_duplicates("object_id")
    )
    df = df.merge(gp_fresh, on="object_id", how="left")
    df["has_gp_elements"] = df["epoch_utc"].notna()
    df["is_active_payload"] = (df["is_on_orbit"]) & (df["operational_status"] == "+")

    cols = [
        "object_id", "name", "intl_designator", "owner_code", "nation", "operator_id",
        "object_type", "operational_status", "rcs_size_m2", "launch_date", "decay_date",
        "is_on_orbit", "is_active_payload", "period_min", "inclination_deg",
        "satcat_apogee_km", "satcat_perigee_km", "mean_altitude_km", "band_25km",
        "regime", "has_gp_elements", "epoch_utc", "is_stale", "data_status",
        "orbit_center", "orbit_type",
    ]
    return df[cols]


def build_fact_inventory(dim_obj: pd.DataFrame, run_date: datetime) -> pd.DataFrame:
    valid = dim_obj[dim_obj["is_on_orbit"] & dim_obj["regime"].notna()]
    shells = build_dim_shells()
    inv = (
        valid.groupby(["regime", "object_type"], observed=True)
        .agg(object_count=("object_id", "size"),
             active_payload_count=("is_active_payload", "sum"))
        .reset_index()
        .merge(shells[["shell_id", "regime"]], on="regime", how="left")
    )
    if inv["shell_id"].isna().any():
        raise ValueError(f"regimes missing from dim_altitude_shell: {inv.loc[inv['shell_id'].isna(), 'regime'].unique()}")
    inv["date_key"] = pd.Timestamp(run_date.date())
    return inv[["date_key", "shell_id", "regime", "object_type", "object_count", "active_payload_count"]]


def build_fact_spatial_density(dim_obj: pd.DataFrame, run_date: datetime) -> pd.DataFrame:
    pop = dim_obj[dim_obj["is_on_orbit"] & dim_obj["band_25km"].notna()].copy()
    pop["band_start"] = pop["band_25km"].astype(int)
    g = pop.groupby("band_start")
    density = pd.DataFrame({
        "object_count": g.size(),
        "debris_count": g["object_type"].apply(lambda s: int((s == "DEB").sum())),
        "payload_count": g["object_type"].apply(lambda s: int((s == "PAY").sum())),
        "rb_count": g["object_type"].apply(lambda s: int((s == "R/B").sum())),
    }).reset_index()

    # HHI of OWNER-code shares within each band (state-level concentration proxy)
    def band_hhi(frame: pd.DataFrame) -> float:
        counts = frame["owner_code"].value_counts().to_numpy(dtype=float)
        return hhi(counts)

    hhis = pop.groupby("band_start").apply(band_hhi, include_groups=False).rename("shell_hhi").reset_index()
    density = density.merge(hhis, on="band_start")

    density["lower_km"] = density["band_start"].astype(float)
    density["upper_km"] = density["lower_km"] + 25.0
    density["volume_km3"] = [_shell_volume_km3(l, u) for l, u in zip(density["lower_km"], density["upper_km"])]
    density["density_per_1000km3"] = density["object_count"] / density["volume_km3"] * 1000.0
    density["clutter_ratio"] = density["payload_count"] / density["object_count"].replace(0, np.nan)
    density["date_key"] = pd.Timestamp(run_date.date())

    # regime rollup per band midpoint for convenience joins
    density["regime"] = ((density["lower_km"] + density["upper_km"]) / 2.0).map(regime_shell)
    return density[
        ["date_key", "band_start", "lower_km", "upper_km", "regime", "object_count",
         "debris_count", "payload_count", "rb_count", "density_per_1000km3",
         "shell_hhi", "clutter_ratio"]
    ]


def build_fact_conjunctions(soc: pd.DataFrame, dim_obj: pd.DataFrame) -> pd.DataFrame:
    lookups = dim_obj.set_index("object_id")[["regime", "nation", "owner_code"]]
    f = soc.copy()
    for side in ("1", "2"):
        f = f.merge(
            lookups.add_suffix(f"_{side}"),
            left_on=f"NORAD_CAT_ID_{side}",
            right_index=True,
            how="left",
        )
    f = f.rename(columns={
        "NORAD_CAT_ID_1": "primary_object_id",
        "NORAD_CAT_ID_2": "secondary_object_id",
        "OBJECT_NAME_1": "primary_name",
        "OBJECT_NAME_2": "secondary_name",
        "TCA": "tca_utc",
        "regime_1": "primary_regime",
        "regime_2": "secondary_regime",
        "nation_1": "primary_nation",
        "nation_2": "secondary_nation",
    })
    f["date_key"] = f["tca_utc"].dt.normalize()
    return f[[
        "event_id", "date_key", "tca_utc", "primary_object_id", "primary_name",
        "secondary_object_id", "secondary_name", "min_range_km", "rel_speed_km_s",
        "max_probability", "dilution_km", "primary_regime", "secondary_regime",
        "primary_nation", "secondary_nation",
    ]]


def build_fact_growth(growth: pd.DataFrame) -> pd.DataFrame:
    def era(d: pd.Timestamp) -> str:
        if d < ALPHA5_SINCE:
            return "5-digit"
        if d < SIX_DIGIT_SINCE:
            return "alpha5-capable"
        return "6-digit"
    f = growth.copy()
    f["format_type"] = f["date"].map(era)
    f = f.rename(columns={
        "cataloged": "cumulative_catalog_size",
        "new_cataloged": "new_objects_added",
        "on_orbit": "on_orbit_count",
    })
    return f[[
        "date", "cumulative_catalog_size", "new_objects_added", "new_decayed",
        "decayed", "on_orbit_count", "format_type",
    ]]


def build_foster_topn(fact_soc: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    """Re-derive Pc for the highest-risk events with our own Foster integrator
    and benchmark against SOCRATES's reported max_probability.

    Assumptions (documented, per CARA/Foster short-encounter model):
    - combined positional 1-sigma covariance sigma = SOCRATES DILUTION column (km)
    - spherical uncorrelated Gaussian covariance
    - combined hard-body radius R = 20 m (two ~10 m-class objects)
    """
    top = fact_soc.nlargest(top_n, "max_probability").copy()
    top["foster_pc"] = [
        foster_pc_numeric(miss, sigma, hard_body_radius_km=0.02)
        if pd.notna(miss) and pd.notna(sigma) and sigma > 0
        else np.nan
        for miss, sigma in zip(top["min_range_km"], top["dilution_km"])
    ]
    top["pc_ratio_ours_vs_socrates"] = top["foster_pc"] / top["max_probability"].replace(0, np.nan)
    return top.reset_index(drop=True)[[
        "event_id", "primary_name", "secondary_name", "tca_utc", "min_range_km",
        "rel_speed_km_s", "dilution_km", "max_probability", "foster_pc",
        "pc_ratio_ours_vs_socrates",
    ]]


EXPORT_TABLES = {
    "dim_space_object",
    "dim_altitude_shell",
    "dim_operator",
    "dim_date",
    "fact_orbital_inventory",
    "fact_spatial_density",
    "fact_conjunction_events",
    "fact_catalog_growth",
    "analytics_foster_topn",
    "analytics_catalog_forecast",
    "analytics_band_clusters",
}


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    run_date = datetime.now(timezone.utc)
    print(f"=== Orbital Commons Gold build — {run_date.isoformat(timespec='seconds')} ===")

    gp = pd.read_parquet(SILVER_DIR / "gp_objects.parquet")
    satcat = pd.read_parquet(SILVER_DIR / "satcat.parquet")
    soc = pd.read_parquet(SILVER_DIR / "conjunctions.parquet")
    growth = pd.read_parquet(SILVER_DIR / "catalog_growth.parquet")

    print("[gold] building dimensions ...")
    dim_operator = build_dim_operator()
    dim_shells = build_dim_shells()
    dim_obj = build_dim_space_object(satcat, gp)
    t_end = max(soc["TCA"].max(), pd.Timestamp(run_date.date()))
    dim_date = build_dim_date(pd.Timestamp("1957-01-01"), pd.Timestamp(t_end))

    print("[gold] building facts ...")
    fact_inv = build_fact_inventory(dim_obj, run_date)
    fact_dens = build_fact_spatial_density(dim_obj, run_date)
    fact_soc = build_fact_conjunctions(soc, dim_obj)
    fact_growth = build_fact_growth(growth)
    print("[gold] Foster/Chan Pc re-derivation on top-N risk events ...")
    foster_topn = build_foster_topn(fact_soc)

    print("[gold] ARIMA catalog forecast (weekly, 5-year horizon) ...")
    fc = forecast_catalog(fact_growth)
    forecast_tbl = build_forecast_table(fc)
    print(f"    holdout MAPE {fc['mape_holdout_pct']}% | crossing 99,999: "
          f"{fc['crossing_99999'].date() if fc['crossing_99999'] is not None else 'beyond horizon'}")

    print("[gold] K-Means danger-zone clustering of bands ...")
    band_clusters = build_band_clusters(fact_dens, fact_soc, dim_obj)
    n_critical = int((band_clusters["risk_label"] == "Critical").sum())
    print(f"    {band_clusters['risk_label'].nunique()} clusters; "
          f"{n_critical} bands rated Critical")

    tables = {
        "dim_space_object": dim_obj,
        "dim_altitude_shell": dim_shells,
        "dim_operator": dim_operator,
        "dim_date": dim_date,
        "fact_orbital_inventory": fact_inv,
        "fact_spatial_density": fact_dens,
        "fact_conjunction_events": fact_soc,
        "fact_catalog_growth": fact_growth,
        "analytics_foster_topn": foster_topn,
        "analytics_catalog_forecast": forecast_tbl,
        "analytics_band_clusters": band_clusters,
    }

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    db_path = GOLD_DIR / "orbital.duckdb"
    con = duckdb.connect(str(db_path))
    for name, df in tables.items():
        con.register("tmp_view", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_view")
        con.unregister("tmp_view")
        out = GOLD_EXPORTS_DIR / f"{name}.parquet"
        df.to_parquet(out, index=False)
        print(f"    {name}: {len(df):,} rows -> duckdb + exports/{out.name} "
              f"({out.stat().st_size/1024:,.0f} KB)")
    con.close()

    print(f"\nduckdb: {db_path.relative_to(GOLD_DIR.parents[2])}")
    print("gold build complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
