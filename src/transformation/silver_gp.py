"""Silver transform: GP OMM records -> physics-validated object table.

For every GP record across all bronze groups:
- deduplicate by NORAD_CAT_ID keeping the freshest epoch
- propagate with SGP4 at the element epoch (skyfield EarthSatellite.from_omm)
- convert TEME state to WGS84 geodetic subpoint
- apply validation gates; rejected rows are kept with a reject_reason
- flag epoch staleness (> 14 days)
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from skyfield.api import EarthSatellite, load, wgs84

from src.transformation.shells import (
    altitude_band,
    perigee_apogee_km,
    regime_shell,
)

STALENESS_LIMIT_DAYS = 14

OMM_COLUMNS = {
    "NORAD_CAT_ID": "str",
    "OBJECT_NAME": "str",
    "OBJECT_ID": "str",
    "EPOCH": "str",
    "MEAN_MOTION": "float",
    "ECCENTRICITY": "float",
    "INCLINATION": "float",
    "RA_OF_ASC_NODE": "float",
    "ARG_OF_PERICENTER": "float",
    "MEAN_ANOMALY": "float",
    "BSTAR": "float",
    "MEAN_MOTION_DOT": "float",
    "MEAN_MOTION_DDOT": "float",
    "ELEMENT_SET_NO": "float",
    "REV_AT_EPOCH": "float",
    "CLASSIFICATION_TYPE": "str",
    "EPHEMERIS_TYPE": "str",
}


def load_gp_group(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def dedup_records(records: list[dict]) -> dict[int, dict]:
    """Keep the freshest record per catalog number across all groups."""
    best: dict[int, tuple[datetime, dict]] = {}
    for rec in records:
        catnr = int(rec["NORAD_CAT_ID"])
        epoch = datetime.fromisoformat(rec["EPOCH"]).replace(tzinfo=timezone.utc)
        if catnr not in best or epoch > best[catnr][0]:
            best[catnr] = (epoch, rec)
    return {k: v[1] for k, v in best.items()}


def propagate_record(ts, rec: dict) -> tuple[float, float, float, float, float, float]:
    """SGP4 at epoch -> (r_teme_x/y/z km, lat_deg, lon_deg)."""
    sat = EarthSatellite.from_omm(ts, rec)
    t = ts.from_datetime(datetime.fromisoformat(rec["EPOCH"]).replace(tzinfo=timezone.utc))
    geo = sat.at(t)
    x, y, z = geo.position.km
    lat, lon = wgs84.latlon_of(geo)
    return x, y, z, lat.degrees, lon.degrees


def build_silver_gp(group_files: list[Path], run_date: datetime) -> pd.DataFrame:
    ts = load.timescale()
    raw: list[dict] = []
    for path in group_files:
        raw.extend(load_gp_group(path))
    deduped = dedup_records(raw)

    stale_cutoff = run_date - timedelta(days=STALENESS_LIMIT_DAYS)
    rows: list[dict] = []
    for catnr, rec in sorted(deduped.items()):
        row: dict = {"norad_cat_id": catnr}
        for col in OMM_COLUMNS:
            row[col.lower()] = rec.get(col)
        try:
            epoch = datetime.fromisoformat(rec["EPOCH"]).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            epoch = None
        row["epoch_utc"] = epoch

        reject_reasons: list[str] = []
        ecc = rec.get("ECCENTRICITY")
        mm = rec.get("MEAN_MOTION")
        if mm is None or mm <= 0:
            reject_reasons.append("non_positive_mean_motion")
        elif not (0.0 <= float(ecc) < 1.0):
            reject_reasons.append("eccentricity_out_of_range")

        if not reject_reasons:
            try:
                x, y, z, lat, lon = propagate_record(ts, rec)
                row.update({
                    "teme_x_km": x, "teme_y_km": y, "teme_z_km": z,
                    "subpoint_lat_deg": lat, "subpoint_lon_deg": lon,
                })
                r_norm = math.sqrt(x * x + y * y + z * z)
                row["radius_km"] = r_norm
            except Exception as err:  # sgp4 propagation failure (e.g. decayed/mean motion < 0)
                reject_reasons.append(f"sgp4_error")
                row["sgp4_error"] = str(err)[:200]

        row["reject_reason"] = ";".join(reject_reasons)
        row["is_valid"] = len(reject_reasons) == 0

        if row["is_valid"] and mm is not None and ecc is not None:
            perigee, apogee = perigee_apogee_km(float(mm), float(ecc))
            mean_alt = (perigee + apogee) / 2.0
            row["perigee_km"] = perigee
            row["apogee_km"] = apogee
            row["mean_altitude_km"] = mean_alt
            row["altitude_band_25km"] = altitude_band(mean_alt)
            row["regime"] = regime_shell(mean_alt)

        row["is_stale"] = bool(epoch is None or epoch < stale_cutoff)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["run_date_utc"] = run_date.replace(tzinfo=None)
    return df
