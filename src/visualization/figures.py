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


_FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def _dark(fig: go.Figure, title: str, height: int = 420, **layout) -> go.Figure:
    """Unified production styling: transparent backgrounds (CSS panels show
    through), subtle grids, consistent typography and hover chrome."""
    base = dict(
        template="plotly_dark", height=height,
        margin=dict(l=20, r=20, t=52, b=46),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=_FONT, size=12, color="#c9d1d9"),
        title=dict(font=dict(size=13.5, color="#e6edf3"),
                   x=0.004, xanchor="left"),
        hoverlabel=dict(bgcolor="#1b2028", bordercolor="#3a4150",
                        font=dict(family=_FONT, color="#e6edf3", size=12)),
        xaxis=dict(automargin=True, gridcolor="#20242c",
                   zerolinecolor="#20242c", linecolor="#2a2f39"),
        yaxis=dict(automargin=True, gridcolor="#20242c",
                   zerolinecolor="#20242c", linecolor="#2a2f39"),
        legend=dict(font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
    )
    base.update(layout)
    base["title"] = dict(text=title,
                         font=dict(size=13.5, color="#e6edf3"),
                         x=0.004, xanchor="left")
    fig.update_layout(**base)
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
                 barmode="stack", margin=dict(l=150))


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


# ------------------------------------------------------------- density pack

def fig_type_donut(dim_obj: pd.DataFrame) -> go.Figure:
    on = dim_obj[dim_obj["is_on_orbit"]]
    counts = on["object_type"].value_counts().reindex(["PAY", "R/B", "DEB", "UNK"]).fillna(0)
    fig = go.Figure(go.Pie(
        labels=[TYPE_LABELS[t] for t in counts.index],
        values=counts.values, hole=0.6,
        marker=dict(colors=[TYPE_COLORS[t] for t in counts.index]),
        textinfo="label+percent", textfont_size=11,
    ))
    return _dark(fig, "On-orbit composition", height=380)


def fig_hist(series: pd.Series, title: str, x_title: str,
             color: str = "#4cc9f0", log_x: bool = True, nbins: int = 40) -> go.Figure:
    """Histogram with manual bins. Log-scale data MUST use pre-computed
    log-spaced bins: go.Histogram's linear autobinning collapses skewed
    distributions into one sliver that vanishes under a log axis."""
    s = pd.Series(series).dropna().astype(float)
    s = s[s > 0]
    if s.empty:
        return _dark(go.Figure(go.Bar(x=[0], y=[0])), title,
                     yaxis_title="Events", xaxis_title=x_title)

    if not log_x:
        fig = go.Figure(go.Histogram(x=s, nbinsx=nbins, marker_color=color,
                                     hovertemplate="%{x}: %{y:,} events<extra></extra>"))
        return _dark(fig, title, yaxis_title="Events", xaxis_title=x_title)

    lo = float(np.log10(s.min()))
    hi = float(np.log10(s.max()))
    if hi - lo < 0.5:  # degenerate range: widen so bins are visible
        mid = (lo + hi) / 2
        lo, hi = mid - 0.5, mid + 0.5
    edges = np.logspace(lo, hi, nbins + 1)
    counts, _ = np.histogram(s, bins=edges)
    centers = np.sqrt(edges[:-1] * edges[1:])  # geometric mean of each bin
    widths = np.diff(edges) * 0.94
    ranges = [f"{a:.1e} - {b:.1e}" for a, b in zip(edges[:-1], edges[1:])]
    fig = go.Figure(go.Bar(
        x=centers, y=counts, width=widths, marker_color=color,
        customdata=ranges,
        hovertemplate="%{customdata}: %{y:,} events<extra></extra>",
    ))
    fig.update_xaxes(type="log")
    return _dark(fig, title, yaxis_title="Events", xaxis_title=x_title)


def fig_nation_pair_bar(conj: pd.DataFrame, top_n: int = 10) -> go.Figure:
    pairs = (
        conj.groupby([conj["primary_nation"].fillna("?"),
                      conj["secondary_nation"].fillna("?")], observed=True)
        .size().rename("events").nlargest(top_n).reset_index()
    )
    pairs["pair"] = pairs.iloc[:, 0] + "  vs  " + pairs.iloc[:, 1]
    fig = go.Figure(go.Bar(
        y=pairs["pair"][::-1], x=pairs["events"][::-1], orientation="h",
        marker_color="#f8961e",
        hovertemplate="%{y}: %{x:,} events<extra></extra>",
    ))
    return _dark(fig, f"Top {top_n} encounter corridors (owner-state pairs)",
                 xaxis_title="Events this week", height=460, margin=dict(l=220))


def fig_band_composition(dens: pd.DataFrame) -> go.Figure:
    d = dens[dens["band_start"] >= 100].sort_values("band_start")
    labels = (d["lower_km"].astype(int).astype(str) + "-" + d["upper_km"].astype(int).astype(str))
    totals = d[["payload_count", "rb_count", "debris_count"]].sum(axis=1)
    shares = pd.DataFrame({
        "Payloads": d["payload_count"] / totals * 100,
        "Rocket bodies": d["rb_count"] / totals * 100,
        "Debris": d["debris_count"] / totals * 100,
    })
    fig = go.Figure()
    for col, color in zip(shares.columns, ["#4cc9f0", "#f8961e", "#e63946"]):
        fig.add_bar(x=labels, y=shares[col], name=col, marker_color=color)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(tickangle=-45)
    return _dark(fig, "Band composition — % of objects that are junk",
                 yaxis_title="Share (%)", height=440)


def fig_clutter_line(dens: pd.DataFrame) -> go.Figure:
    d = dens[(dens["band_start"] >= 100)].sort_values("band_start")
    fig = go.Figure(go.Scatter(
        x=d["lower_km"] + 12.5, y=d["clutter_ratio"], mode="lines+markers",
        line=dict(color="#4cc9f0"), fill="tozeroy", opacity=0.9,
        hovertemplate="%{x:.0f} km: %{y:.0%} payloads<extra></extra>",
    ))
    fig.update_yaxes(tickformat=".0%", title="Useful share")
    return _dark(fig, "Clutter ratio by altitude — useful vs junk",
                 xaxis_title="Band centre (km)", height=400)


def fig_alt_cdf(dim_obj: pd.DataFrame, alt_max: float = 2000.0) -> go.Figure:
    alts = dim_obj[dim_obj["is_on_orbit"] & dim_obj["mean_altitude_km"].notna()]
    alts = np.sort(alts.loc[alts["mean_altitude_km"] <= alt_max, "mean_altitude_km"].values)
    cdf = np.arange(1, len(alts) + 1) / len(alts)
    p50 = float(np.percentile(alts, 50))
    p90 = float(np.percentile(alts, 90))
    fig = go.Figure(go.Scatter(
        x=alts, y=cdf, mode="lines", line=dict(color="#a78bfa"),
        hovertemplate="%{x:.0f} km: %{y:.0%}<extra></extra>",
    ))
    for pct, val, label in [(0.5, p50, "50%"), (0.9, p90, "90%")]:
        fig.add_hline(y=pct, line_dash="dot", line_color="#666")
        fig.add_vline(x=val, line_dash="dot", line_color="#666",
                      annotation_text=f"{label}: {val:.0f} km", annotation_font_size=10)
    return _dark(fig, "Cumulative altitude curve of on-orbit objects (≤2,000 km)",
                 xaxis_title="Mean altitude (km)", yaxis_title="Share of objects",
                 height=420)


def fig_month_heatmap(growth: pd.DataFrame, since_year: int = 2015) -> go.Figure:
    g = growth[pd.to_datetime(growth["date"]).dt.year >= since_year].copy()
    g["year"] = pd.to_datetime(g["date"]).dt.year
    g["month"] = pd.to_datetime(g["date"]).dt.month
    pivot = g.pivot_table(index="year", columns="month",
                          values="new_objects_added", aggfunc="sum")
    all_months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    month_labels = [all_months[int(m) - 1] for m in pivot.columns]
    fig = px.imshow(pivot, aspect="auto", color_continuous_scale="Viridis",
                    labels=dict(x="Month", y="Year", color="New objects"),
                    x=month_labels, text_auto=True)
    return _dark(fig, f"Catalog inflow by month ({since_year}–present)", height=430)


def fig_crossing_projection(growth: pd.DataFrame, target: float = 99_999.0) -> go.Figure:
    g = growth.sort_values("date").tail(366)
    x = pd.to_datetime(g["date"]).map(pd.Timestamp.toordinal).values
    y = g["cumulative_catalog_size"].values.astype(float)
    slope_per_day, intercept = np.polyfit(x, y, 1)

    hist_dates = pd.to_datetime(g["date"])
    future_end = hist_dates.max() + pd.Timedelta(days=int((target - y[-1]) / max(slope_per_day, 1)) + 30)
    proj_x = pd.date_range(hist_dates.max(), future_end, periods=100)
    proj_y = intercept + slope_per_day * proj_x.map(pd.Timestamp.toordinal)
    crossing = None
    if proj_y.max() >= target:
        idx = int(np.argmax(proj_y >= target))
        crossing = proj_x[idx]

    fig = go.Figure()
    fig.add_scatter(x=hist_dates, y=y, mode="lines", name="observed",
                    line=dict(color="#4cc9f0"))
    fig.add_scatter(x=proj_x, y=proj_y, mode="lines", name="linear trend",
                    line=dict(color="#f8961e", dash="dash"))
    fig.add_hline(y=target, line_dash="dash", line_color="#ff5d8f",
                  annotation_text=f"public catalog hits {int(target):,}",
                  annotation_font_size=10)
    if crossing is not None:
        years_away = (crossing - hist_dates.max()).days / 365.25
        fig.add_annotation(x=crossing, y=target, showarrow=True, arrowhead=1,
                           text=f"~{years_away:.1f} yr at current pace",
                           font=dict(color="#ff5d8f"))
    return _dark(fig, "Naive linear projection — public catalog size",
                 yaxis_title="Cumulative objects", height=440)


def fig_era_timeline() -> go.Figure:
    eras = [
        ("5-digit era", "1957-01-01", "2020-05-01", "#4cc9f0"),
        ("Alpha-5 capable", "2020-05-01", "2026-07-11", "#f8961e"),
        ("6-digit era", "2026-07-11", "2027-06-30", "#e63946"),
    ]
    fig = go.Figure()
    for i, (label, start, end, color) in enumerate(eras[::-1]):
        fig.add_trace(go.Scatter(
            x=[pd.Timestamp(start), pd.Timestamp(end)], y=[i, i], mode="lines",
            line=dict(color=color, width=18), name=label,
            hovertemplate=f"{label}: {start[:4]} → {end[:4]}<extra></extra>",
        ))
    fig.update_yaxes(range=[-0.6, len(eras) - 0.4],
                     tickvals=list(range(len(eras))),
                     ticktext=[e[0] for e in eras])
    return _dark(fig, "Catalog numbering eras", height=280)


def fig_ground_track(gp: pd.DataFrame, max_points: int = 5000) -> go.Figure:
    g = gp[gp["is_valid"]].dropna(subset=["subpoint_lat_deg"])
    if len(g) > max_points:
        g = g.sample(max_points, random_state=42)
    fig = go.Figure(go.Scattergeo(
        lat=g["subpoint_lat_deg"], lon=g["subpoint_lon_deg"],
        mode="markers", marker=dict(size=2.5, color="#4cc9f0", opacity=0.5),
        text=g["object_name"], hovertemplate="%{text}<extra></extra>",
    ))
    fig.update_geos(
        projection_type="natural earth", showcountries=True, countrycolor="#444",
        showcoastlines=True, coastlinecolor="#666", bgcolor="#111",
        landcolor="#222", oceancolor="#111",
    )
    return _dark(fig, "Ground tracks at element epochs (WGS84 subpoints)",
                 height=480)


def fig_catalog_forecast(growth: pd.DataFrame, fc_tbl: pd.DataFrame,
                         since: str = "2015-01-01") -> go.Figure:
    g = growth[pd.to_datetime(growth["date"]) >= since]
    hist_dates = pd.to_datetime(g["date"])
    fc_dates = pd.to_datetime(fc_tbl["date"])

    fig = go.Figure()
    fig.add_scatter(x=hist_dates, y=g["cumulative_catalog_size"],
                    mode="lines", name="observed", line=dict(color="#4cc9f0"))
    fig.add_scatter(x=fc_dates, y=fc_tbl["ci_upper"], mode="lines",
                    line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=fc_dates, y=fc_tbl["ci_lower"], mode="lines",
                    line=dict(width=0), fillcolor="rgba(248,150,30,.25)",
                    fill="tonexty", name="95% CI", hoverinfo="skip")
    fig.add_scatter(x=fc_dates, y=fc_tbl["forecast"], mode="lines",
                    name=f"ARIMA forecast", line=dict(color="#f8961e", dash="dash"))
    fig.add_hline(y=99_999, line_dash="dot", line_color="#ff5d8f")
    crossing = fc_tbl["crossing_99999"].dropna()
    if len(crossing):
        d = pd.Timestamp(crossing.iloc[0]).to_pydatetime()
        yv = float(fc_tbl.loc[fc_tbl["crossing_99999"].notna(), "forecast"].iloc[0])
        fig.add_annotation(x=d, y=yv, text=f"public catalog ~100k: {d:%b %Y}",
                           showarrow=True, arrowhead=1, font=dict(color="#ff5d8f"))
    mape = float(fc_tbl["mape_holdout_pct"].iloc[0])
    fig.add_annotation(xref="paper", x=0.01, y=0.06, showarrow=False,
                       text=f"holdout MAPE {mape}%", font=dict(color="#8b949e"))
    return _dark(fig, "ARIMA(1,1,1) weekly forecast of public catalog size (5-year)",
                 yaxis_title="Cumulative objects", height=470)


def fig_cluster_scatter(clusters: pd.DataFrame) -> go.Figure:
    c = clusters.copy()
    label_colors = {"Quiet": "#4cc9f0", "Moderate": "#a78bfa",
                    "Busy": "#f8961e", "Critical": "#e63946"}
    fig = go.Figure()
    for label in ["Quiet", "Moderate", "Busy", "Critical"]:
        s = c[c["risk_label"] == label]
        if s.empty:
            continue
        fig.add_scatter(
            x=s["object_count"], y=s["debris_share"] * 100, mode="markers",
            name=label, marker=dict(size=9, color=label_colors[label], opacity=.85),
            customdata=np.stack([
                s["lower_km"].astype(int).astype(str) + "-" + s["upper_km"].astype(int).astype(str) + " km",
                s["conj_events"], s["mean_rel_speed"],
            ], axis=-1),
            hovertemplate="%{customdata[0]}<br>%{x:,} objects | "
                          "%{y:.0f}% debris<br>events %{customdata[1]:,}"
                          " | speed %{customdata[2]:.1f} km/s<extra></extra>",
        )
    fig.update_xaxes(type="log", title="Objects in band (log)")
    fig.update_yaxes(title="Debris share (%)")
    return _dark(fig, "Danger-zone clustering of 25 km bands (K-Means, k=4)",
                 height=460)
