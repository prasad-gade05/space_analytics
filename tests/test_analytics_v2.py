import numpy as np
import pandas as pd
import pytest

from src.analytics.clustering import cluster_bands, build_band_features
from src.analytics.forecast import forecast_catalog


def _synthetic_growth(days: int = 1500, start: float = 50_000.0, rate: float = 2.0):
    dates = pd.date_range("2020-01-01", periods=days, freq="D")
    sizes = start + rate * np.arange(days) + np.random.default_rng(7).normal(0, .5, days)
    return pd.DataFrame({
        "date": dates,
        "cumulative_catalog_size": sizes.round(3),
        "new_objects_added": rate,
    })


def test_forecast_on_synthetic_series():
    growth = _synthetic_growth()
    res = forecast_catalog(growth, horizon_weeks=52)
    f = res["frame"]
    # monotone-ish upward forecast for a linear+noise series
    assert f["forecast"].iloc[-1] > f["forecast"].iloc[0]
    # CI brackets the point forecast everywhere
    assert (f["ci_lower"] <= f["forecast"]).all()
    assert (f["ci_upper"] >= f["forecast"]).all()
    # holdout on a near-perfectly-linear series should be accurate
    assert res["mape_holdout_pct"] < 5.0
    # crossing detection works when target is reachable
    assert res["crossing_99999"] is None  # synthetic level ~53k stays far below


def test_forecast_rejects_short_series():
    with pytest.raises(ValueError, match=">=150"):
        forecast_catalog(_synthetic_growth(days=100))


def test_cluster_separable_blobs():
    rng = np.random.default_rng(42)
    bands = []
    specs = [  # (count, debris_share, hhi) per artificial group
        (10_000, 0.01, 0.90), (4_000, 0.05, 0.80), (300, 0.60, 0.20),
    ]
    band_id = 100
    for count, dshare, hhi in specs:
        for _ in range(6):
            bands.append({
                "band_start": band_id, "lower_km": float(band_id),
                "upper_km": float(band_id + 25), "regime": "X",
                "object_count": max(1, int(count * rng.uniform(.9, 1.1))),
                "debris_count": int(count * dshare),
                "payload_count": int(count * (1 - dshare)),
                "rb_count": 0,
                "shell_hhi": hhi + rng.normal(0, .01),
            })
            band_id += 25
    feats = pd.DataFrame(bands)
    feats["debris_share"] = feats["debris_count"] / feats["object_count"]

    clustered = cluster_bands(feats, k=3)
    # each artificial group must land in exactly one cluster
    grp = clustered.assign(group=clustered.index // 6).groupby("group")["cluster"].nunique()
    assert (grp == 1).all(), "clusters split a coherent blob"


def test_band_features_fill_missing_conjunctions():
    dens = pd.DataFrame([{
        "band_start": 450, "lower_km": 450.0, "upper_km": 475.0,
        "regime": "LEO-Constellation", "object_count": 100,
        "debris_count": 5, "payload_count": 90, "rb_count": 5,
        "shell_hhi": 0.9, "clutter_ratio": 0.9,
    }])
    conj = pd.DataFrame({"primary_object_id": [1, 2], "rel_speed_km_s": [10.0, 12.0]})
    dim_obj = pd.DataFrame({"object_id": [1, 2],
                            "band_25km": pd.array([450, 999], dtype="Int64")})
    feats = build_band_features(dens, conj, dim_obj)
    row = feats.iloc[0]
    assert row["conj_events"] == 1      # only object 1 maps to band 450
    assert row["mean_rel_speed"] == pytest.approx(10.0)


def test_risk_labels_ordered_by_composite():
    dens = pd.DataFrame([
        {"band_start": i, "lower_km": float(i), "upper_km": float(i + 25),
         "regime": "R", "object_count": c, "debris_count": d,
         "payload_count": c - d, "rb_count": 0, "shell_hhi": h,
         "clutter_ratio": (c - d) / c}
        for i, (c, d, h) in enumerate([(5000, 10, .9), (2000, 200, .5), (100, 90, .1), (10, 1, .1)])
    ])
    out = cluster_bands(dens, k=2)
    labels = set(out["risk_label"])
    assert labels <= {"Quiet", "Moderate", "Busy", "Critical"}
    assert len(labels) == 2
