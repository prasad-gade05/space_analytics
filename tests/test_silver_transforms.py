import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.transformation import silver_datasets, silver_gp
from src.utils.paths import GP_DIR, latest_bronze_file


@pytest.fixture(scope="module")
def saramago_record():
    with latest_bronze_file(GP_DIR, "gp_active", ".json").open(
        encoding="utf-8"
    ) as fh:
        records = json.load(fh)
    return next(r for r in records if int(r["NORAD_CAT_ID"]) == 100_000)


def test_dedup_keeps_freshest_epoch():
    old = {"NORAD_CAT_ID": "1", "EPOCH": "2026-08-01T00:00:00", "OBJECT_NAME": "OLD"}
    new = {"NORAD_CAT_ID": "1", "EPOCH": "2026-08-20T00:00:00", "OBJECT_NAME": "NEW"}
    other = {"NORAD_CAT_ID": "2", "EPOCH": "2026-07-01T00:00:00", "OBJECT_NAME": "OTHER"}
    out = silver_gp.dedup_records([old, new, other])
    assert len(out) == 2
    assert out[1]["OBJECT_NAME"] == "NEW"
    assert out[2]["OBJECT_NAME"] == "OTHER"


def test_propagation_saramago(saramago_record):
    from skyfield.api import load

    ts = load.timescale()
    x, y, z, lat, lon = silver_gp.propagate_record(ts, saramago_record)
    r = (x * x + y * y + z * z) ** 0.5
    # SARAMAGO is a ~510 km LEO satellite; geocentric radius must be ~6,890 km
    assert 6_850 < r < 6_930
    assert -90 <= lat <= 90
    assert -180 <= lon <= 180


def test_build_silver_gp_small_subset(saramago_record):
    recs = [saramago_record]
    df = silver_gp.build_silver_gp([], datetime(2026, 8, 22, tzinfo=timezone.utc))
    assert isinstance(df, pd.DataFrame)
    # empty-input path: no crash
    assert len(df) == 0

    class FakeGroupFile:
        pass

    # inject one real record through the full pipeline via monkeypatched loader
    orig = silver_gp.load_gp_group
    try:
        silver_gp.load_gp_group = lambda path: recs
        df = silver_gp.build_silver_gp(
            [object()], datetime(2026, 8, 22, tzinfo=timezone.utc)
        )
    finally:
        silver_gp.load_gp_group = orig

    row = df.iloc[0]
    assert int(row["norad_cat_id"]) == 100_000
    assert bool(row["is_valid"])
    assert not bool(row["is_stale"])
    assert row["regime"] == "LEO-Constellation"
    assert 450 < float(row["mean_altitude_km"]) < 600
    assert not pd.isna(row["subpoint_lat_deg"])


def test_invalid_eccentricity_flagged():
    bad = {
        "NORAD_CAT_ID": "99999",
        "EPOCH": "2026-08-20T00:00:00",
        "OBJECT_NAME": "BAD",
        "MEAN_MOTION": 15.5,
        "ECCENTRICITY": 1.5,
        "BSTAR": 0.0,
        "MEAN_MOTION_DOT": 0.0,
        "MEAN_MOTION_DDOT": 0.0,
        "INCLINATION": 51.0,
        "RA_OF_ASC_NODE": 0.0,
        "ARG_OF_PERICENTER": 0.0,
        "MEAN_ANOMALY": 0.0,
    }
    orig = silver_gp.load_gp_group
    try:
        silver_gp.load_gp_group = lambda path: [bad]
        df = silver_gp.build_silver_gp(
            [object()], datetime(2026, 8, 22, tzinfo=timezone.utc)
        )
    finally:
        silver_gp.load_gp_group = orig
    row = df.iloc[0]
    assert not bool(row["is_valid"])
    assert "eccentricity_out_of_range" in row["reject_reason"]
    # rejected rows carry no derived geometry
    assert "regime" not in df.columns or pd.isna(row.get("regime"))


def test_satcat_types_and_on_orbit(tmp_path):
    p = tmp_path / "satcat.csv"
    p.write_text(
        "OBJECT_NAME,OBJECT_ID,NORAD_CAT_ID,OBJECT_TYPE,OPS_STATUS_CODE,OWNER,"
        "LAUNCH_DATE,LAUNCH_SITE,DECAY_DATE,PERIOD,INCLINATION,APOGEE,PERIGEE,"
        "RCS,DATA_STATUS_CODE,ORBIT_CENTER,ORBIT_TYPE\n"
        "ISS (ZARYA),1998-067A,25544,PAY,+,ISS,1998-11-20,TYMSC,,92.93,51.63,423,413,399.0524,,EA,ORB\n"
        "SL-1 R/B,1957-001A,1,R/B,D,CIS,1957-10-04,TYMSC,1957-12-01,96.19,65.10,938,214,20.4200,,EA,IMP\n",
        encoding="utf-8",
    )
    df = silver_datasets.build_silver_satcat(p)
    assert len(df) == 2
    iss = df[df["NORAD_CAT_ID"] == 25544].iloc[0]
    rb = df[df["NORAD_CAT_ID"] == 1].iloc[0]
    assert bool(iss["is_on_orbit"])
    assert not bool(rb["is_on_orbit"])
    assert str(iss["LAUNCH_DATE"].date()) == "1998-11-20"
    assert iss["PERIOD"] == pytest.approx(92.93)


def test_socrates_event_ids_unique_and_typed(tmp_path):
    header = ("NORAD_CAT_ID_1,OBJECT_NAME_1,DSE_1,NORAD_CAT_ID_2,OBJECT_NAME_2,"
              "DSE_2,TCA,TCA_RANGE,TCA_RELATIVE_SPEED,MAX_PROB,DILUTION\n")
    rows = (
        "25544,ISS (ZARYA),0,100000,SARAMAGO,0,2026-08-23 04:16:59.334,0.016,10.5,1.918E-01,0.001\n"
        "25544,ISS (ZARYA),0,100000,SARAMAGO,0,2026-08-25 06:00:00.000,1.2,7.3,1.0E-05,0.002\n"
    )
    p = tmp_path / "soc.csv"
    p.write_text(header + rows, encoding="utf-8")
    df = silver_datasets.build_silver_socrates(p)
    assert len(df) == 2
    assert df["event_id"].is_unique
    assert df["max_probability"].iloc[0] == pytest.approx(0.1918)
    assert df["min_range_km"].iloc[0] == pytest.approx(0.016)


def test_growth_series_delta(tmp_path):
    content = (
        "Date,Cataloged,Decayed,On Orbit\n"
        "2026-08-19,70352,35483,34869\n"
        "2026-08-20,70355,35487,34868\n"
        "2026-08-21,70355,35487,34868\n"
    )
    p = tmp_path / "growth.csv"
    p.write_text(content, encoding="utf-8")
    df = silver_datasets.build_silver_growth(p)
    assert list(df["new_cataloged"]) == [70352, 3, 0]
    assert list(df["new_decayed"]) == [0, 4, 0]
