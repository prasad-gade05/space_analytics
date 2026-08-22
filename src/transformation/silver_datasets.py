"""Silver transforms for SATCAT, SOCRATES conjunctions and catalog growth."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SATCAT_DTYPE = {
    "OBJECT_NAME": "string",
    "OBJECT_ID": "string",
    "NORAD_CAT_ID": "Int64",
    "OBJECT_TYPE": "string",
    "OPS_STATUS_CODE": "string",
    "OWNER": "string",
    "LAUNCH_SITE": "string",
    "DATA_STATUS_CODE": "string",
    "ORBIT_CENTER": "string",
    "ORBIT_TYPE": "string",
}

SOCRATES_DTYPE = {
    "NORAD_CAT_ID_1": "Int64",
    "OBJECT_NAME_1": "string",
    "DSE_1": "string",
    "NORAD_CAT_ID_2": "Int64",
    "OBJECT_NAME_2": "string",
    "DSE_2": "string",
}


def build_silver_satcat(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=SATCAT_DTYPE)
    df["LAUNCH_DATE"] = pd.to_datetime(df["LAUNCH_DATE"], errors="coerce")
    df["DECAY_DATE"] = pd.to_datetime(df["DECAY_DATE"], errors="coerce")
    for col in ("PERIOD", "INCLINATION", "APOGEE", "PERIGEE", "RCS"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["is_on_orbit"] = df["DECAY_DATE"].isna()
    # object_type domain: PAY payload, R/B rocket body, DEB debris, UNK unknown
    bad_types = ~df["OBJECT_TYPE"].isin(["PAY", "R/B", "DEB", "UNK"])
    if bad_types.any():
        raise ValueError(f"Unexpected OBJECT_TYPE values: {df.loc[bad_types, 'OBJECT_TYPE'].unique()}")
    return df


def build_silver_socrates(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=SOCRATES_DTYPE)
    df["TCA"] = pd.to_datetime(df["TCA"], format="%Y-%m-%d %H:%M:%S.%f", errors="raise")
    for col in ("TCA_RANGE", "TCA_RELATIVE_SPEED", "MAX_PROB", "DILUTION"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={
        "TCA_RANGE": "min_range_km",
        "TCA_RELATIVE_SPEED": "rel_speed_km_s",
        "MAX_PROB": "max_probability",
        "DILUTION": "dilution_km",
    })
    df["event_id"] = (
        df["NORAD_CAT_ID_1"].astype(str) + "-"
        + df["NORAD_CAT_ID_2"].astype(str) + "-"
        + df["TCA"].dt.strftime("%Y%m%d%H%M%S")
    )
    dup = int(df["event_id"].duplicated().sum())
    if dup:
        raise ValueError(f"{dup} duplicate event_ids in SOCRATES data")
    return df


def build_silver_growth(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    expected = {"date", "cataloged", "decayed", "on_orbit"}
    if set(df.columns) != expected:
        raise ValueError(f"growth.csv columns {set(df.columns)} != {expected}")
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="raise")
    if not df["date"].is_monotonic_increasing:
        raise ValueError("growth series dates are not monotonic")
    df["new_cataloged"] = df["cataloged"].diff().fillna(df["cataloged"]).astype("int64")
    df["new_decayed"] = df["decayed"].diff().fillna(0).astype("int64")
    return df
