"""K-Means danger-zone clustering of 25 km altitude bands.

Features per band (from Gold facts, standardized before clustering):
- object_count (log1p)          : crowding
- debris_share                  : junk fraction
- hhi                           : single-operator dominance
- conj_events                   : conjunction screening load touching the band
- mean_rel_speed                : encounter violence in the band

k = 4 fixed for interpretability; clusters are ranked by a composite risk
score (mean of z-scored count, debris share and conj load) and mapped to
ordered labels: Quiet / Moderate / Busy / Critical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

RISK_LABELS = ["Quiet", "Moderate", "Busy", "Critical"]


def build_band_features(dens: pd.DataFrame, conj: pd.DataFrame,
                        dim_obj: pd.DataFrame) -> pd.DataFrame:
    d = dens[dens["band_start"] >= 100].copy()
    d["debris_share"] = d["debris_count"] / d["object_count"].replace(0, np.nan)

    # map each event's primary object to its 25 km band, count load per band
    band_of = dim_obj.set_index("object_id")["band_25km"]
    primary_band = conj["primary_object_id"].map(band_of)
    speed_by_band = (
        pd.DataFrame({"band": primary_band, "speed": conj["rel_speed_km_s"]})
        .dropna()
        .groupby("band")
        .agg(conj_events=("speed", "size"), mean_rel_speed=("speed", "mean"))
    )
    feats = d.merge(speed_by_band, left_on="band_start",
                    right_index=True, how="left")
    feats[["conj_events", "mean_rel_speed"]] = (
        feats[["conj_events", "mean_rel_speed"]].fillna(0)
    )
    return feats


def cluster_bands(feats: pd.DataFrame,
                  k: int = 4, random_state: int = 42) -> pd.DataFrame:
    feature_cols = ["log_objects", "debris_share", "shell_hhi", "conj_events"]
    f = feats.copy()
    if "debris_share" not in f.columns:
        f["debris_share"] = f["debris_count"] / f["object_count"].replace(0, np.nan)
    f["log_objects"] = np.log1p(f["object_count"])
    for col in ("conj_events", "mean_rel_speed"):  # absent outside pipeline runs
        if col not in f.columns:
            f[col] = 0.0
    X = StandardScaler().fit_transform(f[feature_cols])

    km = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit(X)
    f["cluster"] = km.labels_

    # composite risk -> ordered labels
    z = pd.DataFrame(X, columns=feature_cols)
    composite = (z["log_objects"] + z["debris_share"] + z["conj_events"]) / 3.0
    rank = f.assign(composite=composite.values).groupby("cluster")["composite"].mean()
    order = rank.sort_values().index.tolist()
    label_map = {c: RISK_LABELS[i] for i, c in enumerate(order)}
    f["risk_label"] = f["cluster"].map(label_map)
    return f.sort_values("band_start").reset_index(drop=True)


def build_band_clusters(dens: pd.DataFrame, conj: pd.DataFrame,
                        dim_obj: pd.DataFrame) -> pd.DataFrame:
    feats = build_band_features(dens, conj, dim_obj)
    out = cluster_bands(feats)
    cols = ["band_start", "lower_km", "upper_km", "regime", "object_count",
            "debris_share", "shell_hhi", "conj_events", "mean_rel_speed",
            "cluster", "risk_label"]
    return out[cols]
