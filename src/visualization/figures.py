"""Pure Plotly figure builders for the Orbital Commons dashboard.

No Streamlit imports here: these functions take Gold-layer DataFrames and
return plotly Figure objects so they can be unit-tested headlessly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

REGIME_ORDER = [
    "VLEO", "LEO-Constellation", "LEO-SSO", "Legacy-Debris",
    "Upper-LEO", "MEO", "GEO", "HEO/Deep-Space",
]

TYPE_COLORS = {"PAY": "#4cc9f0", "R/B": "#f8961e", "DEB": "#e63946", "UNK": "#adb5bd"}
TYPE_LABELS = {"PAY": "Payloads", "R/B": "Rocket bodies", "DEB": "Debris", "UNK": "Unknown"}


def fig_regime_inventory(inv: pd.DataFrame) -> go.Figure:
    pivot = (
        inv.pivot_table(index="regime", columns="object_type",
                        values="object_count", aggfunc="sum")
        .reindex(REGIME_ORDER)
        .fillna(0)
    )
    fig = go.Figure()
    for t in ["PAY", "R/B", "DEB", "UNK"]:
        if t in pivot.columns:
            fig.add_bar(x=pivot.index, y=pivot[t], name=TYPE_LABELS[t],
                        marker_color=TYPE_COLORS[t])
    fig.update_layout(
        barmode="stack", template="plotly_dark",
        title="On-orbit population by altitude regime",
        xaxis_title="", yaxis_title="Objects",
        legend_title="", height=420,
    )
    return fig


def fig_density_bands(dens: pd.DataFrame) -> go.Figure:
    d = dens[dens["band_start"] >= 100].sort_values("band_start")
    fig = go.Figure()
    fig.add_bar(x=d["lower_km"] + 12.5, y=d["object_count"], name="All objects",
                marker_color="#4cc9f0", width=20)
    fig.add_bar(x=d["lower_km"] + 12.5, y=d["debris_count"], name="Debris",
                marker_color="#e63946", width=20)
    peak = d.loc[d["object_count"].idxmax()]
    fig.add_annotation(
        x=peak["lower_km"] + 12.5, y=peak["object_count"],
        text=f"peak: {int(peak['object_count']):,} objects @ {int(peak['lower_km'])}-{int(peak['upper_km'])} km",
        showarrow=True, arrowhead=1, yshift=18,
    )
    fig.update_layout(
        barmode="overlay", template="plotly_dark",
        title="Object density across LEO 25 km bands",
        xaxis_title="Band centre altitude (km)", yaxis_title="Objects",
        legend_title="", height=420,
    )
    return fig


def fig_hhi_bands(dens: pd.DataFrame) -> go.Figure:
    d = dens[dens["band_start"] >= 350].sort_values("shell_hhi")
    colors = ["#e63946" if v >= 0.25 else "#f8961e" if v >= 0.15 else "#4cc9f0"
              for v in d["shell_hhi"]]
    fig = go.Figure(go.Bar(
        x=d["lower_km"].astype(int).astype(str) + " km",
        y=d["shell_hhi"], marker_color=colors,
        hovertext=[
            f"{int(r.lower_km)}-{int(r.upper_km)} km · {r.object_count:,} objects"
            for r in d.itertuples()
        ],
    ))
    fig.add_hline(y=0.25, line_dash="dash", annotation_text="high concentration (0.25)")
    fig.update_layout(
        template="plotly_dark",
        title="Operator-concentration (HHI) by band — state-level owner proxy",
        xaxis_title="", yaxis_title="HHI (0-1)", height=420,
    )
    return fig


def fig_growth_eras(growth: pd.DataFrame) -> go.Figure:
    g = growth.copy()
    era_colors = {"5-digit": "#4cc9f0", "alpha5-capable": "#f8961e", "6-digit": "#e63946"}
    fig = go.Figure()
    for era, chunk in g.groupby("format_type", sort=False):
        fig.add_scatter(x=pd.to_datetime(chunk["date"]), y=chunk["cumulative_catalog_size"],
                        mode="lines", name=era,
                        line=dict(color=era_colors.get(era, "#888"), width=2),
                        connectgaps=True)
    overflow_day = pd.Timestamp("2026-07-11").to_pydatetime()
    if g["date"].max() >= overflow_day:
        fig.add_vline(x=overflow_day, line_dash="dot", line_color="#ff5d8f")
        fig.add_annotation(x=overflow_day, y=1.06, yref="paper", showarrow=False,
                           font=dict(color="#ff5d8f"),
                           text="5-digit IDs exhausted (Saramago)")
    official_max = 100_403
    fig.add_hline(y=official_max, line_dash="dash", line_color="#ff5d8f")
    fig.add_annotation(xref="paper", x=0.01, y=official_max, showarrow=False,
                       xanchor="left", font=dict(color="#ff5d8f"),
                       text=f"official catalog counter {official_max:,}")
    fig.update_layout(
        template="plotly_dark",
        title="Public SATCAT growth, 1957 - present (CelesTrak)",
        xaxis_title="", yaxis_title="Cumulative cataloged objects",
        legend_title="Numbering era", height=460,
    )
    return fig


def fig_nation_footprint(dim_obj: pd.DataFrame, top_n: int = 14) -> go.Figure:
    on = dim_obj[dim_obj["is_on_orbit"]]
    tab = (
        on.groupby(["nation", "object_type"], observed=True).size().unstack(fill_value=0)
        .assign(total=lambda d: d.sum(axis=1)).nlargest(top_n, "total")
        .drop(columns="total")
    )
    tab = tab.drop(columns=[c for c in ("UNK",) if c in tab.columns])
    for t in ("PAY", "R/B", "DEB"):
        if t not in tab.columns:
            tab[t] = 0
    fig = go.Figure()
    for t in ("PAY", "R/B", "DEB"):
        fig.add_bar(y=tab.index[::-1], x=tab[t][::-1], name=TYPE_LABELS[t],
                    orientation="h", marker_color=TYPE_COLORS[t])
    fig.update_layout(
        barmode="stack", template="plotly_dark",
        title=f"On-orbit footprint by nation/state (top {top_n})",
        xaxis_title="Objects (log)", yaxis_title="",
        xaxis_type="log", legend_title="", height=520,
    )
    return fig


def fig_lorenz_debris(dim_obj: pd.DataFrame) -> go.Figure:
    deb = dim_obj[(dim_obj["is_on_orbit"]) & (dim_obj["object_type"] == "DEB")]
    counts = deb.groupby("nation").size().sort_values()
    cum = counts.cumsum() / max(counts.sum(), 1)
    n = len(counts)
    fig = go.Figure()
    fig.add_scatter(x=np.linspace(0, 1, 50), y=np.linspace(0, 1, 50),
                    mode="lines", name="perfect equality",
                    line=dict(color="#666", dash="dash"))
    fig.add_scatter(x=[0] + list((np.arange(1, n + 1)) / n),
                    y=[0] + list(cum.values), mode="lines", fill="toself",
                    name="debris footprint", line=dict(color="#e63946"))
    from src.analytics.metrics import gini
    fig.add_annotation(x=0.02, y=0.94, showarrow=False,
                       text=f"Gini = {gini(counts.values):.3f}")
    fig.update_layout(
        template="plotly_dark",
        title="Lorenz curve — orbital-debris footprint inequality by nation",
        xaxis_title="Cumulative share of responsible states",
        yaxis_title="Cumulative share of debris", height=460,
    )
    return fig


def fig_3d_snapshot(gp: pd.DataFrame, max_points: int = 6000) -> go.Figure:
    g = gp[gp["is_valid"]].dropna(subset=["teme_x_km"])
    if len(g) > max_points:
        g = g.sample(max_points, random_state=42)
    fig = px.scatter_3d(
        g, x="teme_x_km", y="teme_y_km", z="teme_z_km",
        color="regime", category_orders={"regime": REGIME_ORDER},
        hover_name="object_name",
        hover_data={"norad_cat_id": True, "teme_x_km": False,
                    "teme_y_km": False, "teme_z_km": False},
        labels={"teme_x_km": "TEME X (km)", "teme_y_km": "TEME Y (km)", "teme_z_km": "TEME Z (km)"},
        height=640, opacity=0.55,
    )
    fig.update_traces(marker=dict(size=2))
    fig.update_layout(
        template="plotly_dark",
        title="Catalog snapshot at element epochs (TEME inertial frame, SGP4)",
        legend_title="Regime",
    )
    return fig


def fig_foster_benchmark(topn: pd.DataFrame) -> go.Figure:
    t = topn.dropna(subset=["foster_pc"])
    lim = max(t["max_probability"].max(), t["foster_pc"].max()) * 1.3
    fig = go.Figure()
    fig.add_scatter(x=[0, lim], y=[0, lim], mode="lines",
                    line=dict(color="#666", dash="dash"), name="perfect agreement")
    fig.add_scatter(x=t["max_probability"], y=t["foster_pc"], mode="markers",
                    marker=dict(color="#4cc9f0", size=8),
                    text=t["primary_name"] + " vs " + t["secondary_name"],
                    hovertemplate="%{text}<br>SOCRATES %{x:.4f} | ours %{y:.4f}<extra></extra>")
    fig.update_layout(
        template="plotly_dark",
        title="Foster re-derived Pc vs SOCRATES reported Pc (top-N events)",
        xaxis_title="SOCRATES max_probability", yaxis_title="Foster/Chan Pc (ours)",
        height=460,
    )
    return fig
