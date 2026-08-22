"""Pure Plotly figure builders for the Orbital Commons dashboard.

No Streamlit imports here: these functions take Gold-layer DataFrames and
return plotly Figure objects so they can be unit-tested headlessly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.analytics.metrics import gini

REGIME_ORDER = [
    "VLEO", "LEO-Constellation", "LEO-SSO", "Legacy-Debris",
    "Upper-LEO", "MEO", "GEO", "HEO/Deep-Space",
]

TYPE_COLORS = {"PAY": "#4cc9f0", "R/B": "#f8961e", "DEB": "#e63946", "UNK": "#adb5bd"}
TYPE_LABELS = {"PAY": "Payloads", "R/B": "Rocket bodies", "DEB": "Debris", "UNK": "Unknown"}


def _dark(fig: go.Figure, title: str, height: int = 420, **layout) -> go.Figure:
    fig.update_layout(template="plotly_dark", title=title, height=height,
                      margin=dict(l=10, r=10, t=60, b=10), **layout)
    return fig


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
    return _dark(fig, "On-orbit population by altitude regime",
                 yaxis_title="Objects", barmode="stack")


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
        text=f"peak: {int(peak['object_count']):,} @ {int(peak['lower_km'])}-{int(peak['upper_km'])} km",
        showarrow=True, arrowhead=1, yshift=18,
    )
    return _dark(fig, "Object counts across LEO 25 km bands",
                 xaxis_title="Band centre altitude (km)", yaxis_title="Objects",
                 barmode="overlay")


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
    fig.add_hline(y=0.25, line_dash="dash",
                  annotation_text="high concentration", annotation_font_size=10)
    return _dark(fig, "HHI concentration by band (owner-state proxy)",
                 yaxis_title="HHI (0-1)")


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
    return _dark(fig, "Public SATCAT growth, 1957 - present",
                 height=460, yaxis_title="Cumulative cataloged",
                 legend_title="Numbering era")


def fig_new_objects_daily(growth: pd.DataFrame, last_days: int = 400) -> go.Figure:
    g = growth.sort_values("date").tail(last_days)
    fig = go.Figure()
    fig.add_bar(x=pd.to_datetime(g["date"]), y=g["new_objects_added"], name="New cataloged",
                marker_color="#4cc9f0")
    fig.add_bar(x=pd.to_datetime(g["date"]), y=-g["new_decayed"], name="Decayed",
                marker_color="#e63946")
    mean_new = float(g["new_objects_added"].tail(90).mean())
    fig.add_hline(y=mean_new, line_dash="dash", line_color="#f8961e",
                  annotation_text=f"90-day avg +{mean_new:.0f}/day",
                  annotation_font_size=10)
    return _dark(fig, f"Daily catalog inflow/outflow — last {min(last_days, len(g))} days",
                 yaxis_title="Objects/day")


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
    return _dark(fig, f"On-orbit footprint by nation/state (top {top_n})",
                 height=520, xaxis_title="Objects (log)", xaxis_type="log",
                 barmode="stack")


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
    fig.add_annotation(x=0.02, y=0.94, showarrow=False,
                       text=f"Gini = {gini(counts.values):.3f}")
    return _dark(fig, "Lorenz curve — debris footprint inequality",
                 height=460,
                 xaxis_title="Cumulative share of states",
                 yaxis_title="Cumulative share of debris")


def fig_responsibility_frontier(dim_obj: pd.DataFrame, top_n: int = 14) -> go.Figure:
    """Payloads vs debris per nation on log-log; above diagonal = debris-heavy."""
    on = dim_obj[dim_obj["is_on_orbit"]]
    tab = (on.pivot_table(index="nation", columns="object_type",
                          values="object_id", aggfunc="count")
           .fillna(0))
    for col in ("PAY", "DEB"):
        if col not in tab.columns:
            tab[col] = 0
    tab = tab[(tab["PAY"] + tab["DEB"]) > 0].nlargest(top_n, "DEB")
    fig = go.Figure()
    lim = float(max(tab["PAY"].max(), tab["DEB"].max(), 10))
    fig.add_scatter(x=[1, lim], y=[1, lim], mode="lines",
                    line=dict(color="#666", dash="dash"), name="parity")
    fig.add_scatter(x=tab["PAY"], y=tab["DEB"], mode="markers+text",
                    text=tab.index, textposition="top center",
                    marker=dict(size=9, color="#f8961e"),
                    hovertemplate="%{text}<br>payloads %{x:,}<br>debris %{y:,}<extra></extra>")
    fig.update_xaxes(type="log", title="Active/on-orbit payloads")
    fig.update_yaxes(type="log", title="Debris")
    return _dark(fig, "Responsibility frontier — debris vs payloads (log-log)")


def fig_altitude_inclination(dim_obj: pd.DataFrame, alt_max: float = 2200.0) -> go.Figure:
    on = dim_obj[dim_obj["is_on_orbit"] & dim_obj["mean_altitude_km"].notna()
                 & dim_obj["inclination_deg"].notna()]
    leo = on[on["mean_altitude_km"] <= alt_max]
    fig = px.density_heatmap(
        leo, x="mean_altitude_km", y="inclination_deg", nbinsx=60, nbinsy=36,
        color_continuous_scale="Viridis", labels={
            "mean_altitude_km": "Mean altitude (km)",
            "inclination_deg": "Inclination (deg)",
        },
    )
    return _dark(fig, "Where do objects orbit? Altitude × inclination density (≤2,200 km)",
                 height=460)


def fig_launch_cadence(dim_obj: pd.DataFrame) -> go.Figure:
    pay = dim_obj[dim_obj["object_type"] == "PAY"]
    years = pd.to_datetime(pay["launch_date"]).dt.year.dropna().astype(int)
    cadence = years.value_counts().sort_index()
    fig = go.Figure(go.Bar(
        x=cadence.index.astype(str), y=cadence.values, marker_color="#4cc9f0",
        hovertemplate="%{x}: %{y:,} payloads<extra></extra>",
    ))
    fig.update_xaxes(dtick=10)
    return _dark(fig, "Payload launch cadence by year (all-time)",
                 yaxis_title="Payloads launched")


def fig_conj_timeline(conj: pd.DataFrame) -> go.Figure:
    daily = conj.groupby(conj["tca_utc"].dt.date).size()
    fig = go.Figure(go.Bar(
        x=list(daily.index), y=daily.values, marker_color="#f8961e",
        hovertemplate="%{x}: %{y:,} events<extra></extra>",
    ))
    return _dark(fig, "Conjunction screening load by forecast day (rolling 7-day run)",
                 yaxis_title="Events")


def fig_risk_matrix(conj: pd.DataFrame, sample: int = 3000) -> go.Figure:
    c = conj[conj["primary_regime"].notna()]
    if len(c) > sample:
        c = c.sample(sample, random_state=42)
    fig = px.scatter(
        c, x="min_range_km", y="max_probability", color="primary_regime",
        log_x=True, log_y=True, opacity=0.55, height=460,
        hover_data={"primary_name": True, "secondary_name": True,
                    "min_range_km": ":.3f", "max_probability": ".2e",
                    "rel_speed_km_s": True},
        labels={"min_range_km": "Miss distance (km, log)", "max_probability": "Pc (log)"},
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    return _dark(fig, "Risk matrix — miss distance vs collision probability")


def fig_foster_benchmark(topn: pd.DataFrame) -> go.Figure:
    t = topn.dropna(subset=["foster_pc"])
    lim = max(t["max_probability"].max(), t["foster_pc"].max()) * 1.3
    fig = go.Figure()
    fig.add_scatter(x=[0, lim], y=[0, lim], mode="lines",
                    line=dict(color="#666", dash="dash"), name="perfect agreement")
    fig.add_scatter(x=t["max_probability"], y=t["foster_pc"], mode="markers",
                    marker=dict(color="#4cc9f0", size=8),
                    customdata=np.stack([
                        t["primary_name"] + " vs " + t["secondary_name"],
                        t["pc_ratio_ours_vs_socrates"],
                    ], axis=-1),
                    hovertemplate="%{customdata[0]}<br>SOCRATES %{x:.4f}"
                                  " | ours %{y:.4f} (ratio %{customdata[1]:.2f})<extra></extra>")
    fig.update_xaxes(title="SOCRATES max_probability", type="log")
    fig.update_yaxes(title="Foster/Chan Pc (ours)", type="log")
    return _dark(fig, "Re-derived Pc vs SOCRATES reported Pc (top-N events)", height=460)


def fig_foster_ratio_hist(topn: pd.DataFrame) -> go.Figure:
    r = topn["pc_ratio_ours_vs_socrates"].replace([np.inf, -np.inf], np.nan).dropna()
    fig = go.Figure(go.Histogram(x=r, nbinsx=25, marker_color="#a78bfa"))
    fig.add_vline(x=float(r.median()), line_dash="dash", annotation_text="median")
    return _dark(fig, "Distribution of Pc ratios (ours / SOCRATES)",
                 xaxis_title="Ratio")


def fig_operator_share(attributed: pd.DataFrame) -> go.Figure:
    """attributed: index operator_name, column on_orbit_objects."""
    d = attributed.sort_values("on_orbit_objects")
    fig = go.Figure(go.Bar(
        y=d.index, x=d["on_orbit_objects"], orientation="h",
        marker_color="#4cc9f0",
        hovertemplate="%{y}: %{x:,}<extra></extra>",
    ))
    return _dark(fig, "Curated operators — on-orbit object attribution",
                 xaxis_title="Objects", height=380)


def fig_stale_split(gp: pd.DataFrame) -> go.Figure:
    valid = gp[gp["is_valid"]]
    counts = pd.Series({
        "fresh (≤14 d)": int((~valid["is_stale"]).sum()),
        "stale (>14 d)": int(valid["is_stale"].sum()),
    })
    fig = go.Figure(go.Pie(
        labels=counts.index, values=counts.values, hole=0.55,
        marker=dict(colors=["#4cc9f0", "#e63946"]),
        textinfo="label+percent",
    ))
    return _dark(fig, "Element-set freshness (GP epochs)", height=360)


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
        height=680, opacity=0.55,
    )
    fig.update_traces(marker=dict(size=2))
    return _dark(fig, "Catalog snapshot at element epochs (TEME inertial frame, SGP4)",
                 legend_title="Regime")
