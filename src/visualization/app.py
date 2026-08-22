"""Orbital Commons — mission console (Streamlit, top navigation).

Run:  streamlit run src/visualization/app.py
Reads committed Gold-layer parquet exports; no DB locking, deploy-friendly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analytics.metrics import gini, hhi  # noqa: E402
from src.utils.paths import GOLD_EXPORTS_DIR, SILVER_DIR  # noqa: E402
from src.visualization import figures  # noqa: E402

st.set_page_config(page_title="Orbital Commons", page_icon="🛰",
                   layout="wide", initial_sidebar_state="collapsed")

OFFICIAL_COUNTER = 100_403  # max catalog number ever assigned (USSF, 2026-07-11)
SARAMAGO_DAY = pd.Timestamp("2026-07-11")


# ---------------------------------------------------------------- data access

@st.cache_data(ttl=3600, show_spinner="Loading Gold exports ...")
def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(GOLD_EXPORTS_DIR / f"{name}.parquet")


@st.cache_data(ttl=3600, show_spinner="Loading propagated catalog ...")
def load_gp() -> pd.DataFrame:
    return pd.read_parquet(SILVER_DIR / "gp_objects.parquet")


@st.cache_resource
def duck() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    # NOTE: DDL cannot bind prepared parameters in DuckDB; the paths are local,
    # repo-controlled constants so inline interpolation is safe.
    for view, table in (("conj", "fact_conjunction_events"),
                        ("objs", "dim_space_object"),
                        ("growth", "fact_catalog_growth"),
                        ("dens", "fact_spatial_density")):
        p = (GOLD_EXPORTS_DIR / f"{table}.parquet").as_posix()
        con.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet('{p}')")
    return con


EXPLORER_PRESETS: dict[str, str] = {
    "Sub-100 m close approaches": """
        SELECT primary_name AS primary_, secondary_name, tca_utc, min_range_km,
               rel_speed_km_s, max_probability
        FROM conj WHERE min_range_km < 0.1 ORDER BY min_range_km LIMIT 200""",
    "Hypervelocity encounters (> 14 km/s)": """
        SELECT primary_name AS primary_, secondary_name, tca_utc, rel_speed_km_s,
               min_range_km, max_probability
        FROM conj WHERE rel_speed_km_s > 14 ORDER BY rel_speed_km_s DESC LIMIT 200""",
    "Highest-risk events this week": """
        SELECT primary_name AS primary_, secondary_name, tca_utc, min_range_km,
               max_probability FROM conj ORDER BY max_probability DESC LIMIT 200""",
    "Debris involved in conjunctions": """
        SELECT primary_name AS primary_, secondary_name, primary_regime,
               min_range_km, max_probability
        FROM conj WHERE primary_name LIKE '%DEB%' OR secondary_name LIKE '%DEB%'
        ORDER BY max_probability DESC LIMIT 200""",
    "Oldest objects still on orbit": """
        SELECT object_id, name, intl_designator, nation, launch_date, regime
        FROM objs WHERE is_on_orbit AND launch_date IS NOT NULL
        ORDER BY launch_date LIMIT 100""",
    "Six-digit era objects (post-Saramago)": """
        SELECT object_id, name, intl_designator, launch_date, owner_code, nation
        FROM objs WHERE object_id >= 100000 ORDER BY object_id LIMIT 500""",
    "Most congested bands by debris count": """
        SELECT lower_km || '-' || upper_km AS band, object_count, debris_count,
               round(density_per_1000km3 * 1e9, 3) AS per_billion_km3,
               round(shell_hhi, 3) AS hhi
        FROM dens WHERE band_start >= 100 ORDER BY debris_count DESC LIMIT 50""",
    "Busiest launch years in history": """
        SELECT year(launch_date) AS launch_year, count(*) AS payloads
        FROM objs WHERE object_type = 'PAY' AND launch_date IS NOT NULL
        GROUP BY 1 ORDER BY payloads DESC LIMIT 25""",
}


def preset_query(name: str) -> pd.DataFrame:
    return duck().execute(EXPLORER_PRESETS[name]).fetchdf()


# ---------------------------------------------------------------- page parts

def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value, help_text) in zip(cols, items):
        col.metric(label, value, help=help_text)


def section(label: str) -> None:
    st.markdown(f"#### {label}")


# ---------------------------------------------------------------- pages

def page_mission_control() -> None:
    objs = load("dim_space_object")
    growth = load("fact_catalog_growth")
    conj = load("fact_conjunction_events")
    on = objs[objs["is_on_orbit"]]

    kpi_row([
        ("Public catalog (all-time)", f"{len(objs):,}",
         "Objects publicly queryable via CelesTrak SATCAT"),
        ("On-orbit tracked", f"{len(on):,}", "No decay date in latest snapshot"),
        ("Debris share on orbit", f"{(on['object_type'] == 'DEB').mean():.0%}", None),
        ("Official counter gap", f"{OFFICIAL_COUNTER - len(objs):,}",
         "Max-assigned number minus public rows: withheld 7xxxx–9xxxx block"),
        ("Events next 24 h", f"{(conj['tca_utc'] <= conj['tca_utc'].min() + pd.Timedelta(days=1)).sum():,}", None),
        ("Top Pc next 24 h", f"{next24_top(conj):.3f}", None),
        ("Events Pc ≥ 1%", f"{(conj['max_probability'] >= 0.01).sum():,}", None),
        ("Catalog growth yesterday", f"+{int(growth['new_objects_added'].iloc[-1]):,}", None),
    ])

    next24 = conj[conj["tca_utc"] <= conj["tca_utc"].min() + pd.Timedelta(days=1)]
    worst = next24.loc[next24["max_probability"].idxmax()]
    st.info(
        f"🔴 **Highest-risk encounter in the next 24h:** **{worst['primary_name']}** ↔ "
        f"**{worst['secondary_name']}** · miss **{worst['min_range_km']*1000:.0f} m** · "
        f"Pc **{worst['max_probability']:.3f}** at {worst['tca_utc']:%Y-%m-%d %H:%M} UTC "
        f"· closing speed {worst['rel_speed_km_s']:.1f} km/s"
    )

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(figures.fig_regime_inventory(load("fact_orbital_inventory")),
                        width="stretch")
        st.plotly_chart(figures.fig_conj_timeline(conj), width="stretch")
    with right:
        st.plotly_chart(figures.fig_growth_eras(growth), width="stretch")
        section("Top-5 risks this week")
        show = conj.nlargest(5, "max_probability")[
            ["primary_name", "secondary_name", "tca_utc", "min_range_km", "max_probability"]
        ].copy()
        show["min_range_km"] = (show["min_range_km"] * 1000).round(0).astype(int).astype(str) + " m"
        show["tca_utc"] = show["tca_utc"].dt.strftime("%m-%d %H:%M")
        st.dataframe(show, width="stretch", height=260, hide_index=True)


def next24_top(conj: pd.DataFrame) -> float:
    next24 = conj[conj["tca_utc"] <= conj["tca_utc"].min() + pd.Timedelta(days=1)]
    return float(next24["max_probability"].max())


def page_congestion_atlas() -> None:
    dens = load("fact_spatial_density")
    objs = load("dim_space_object")
    leo = dens[dens["band_start"] >= 100]
    busiest = leo.loc[leo["object_count"].idxmax()]

    kpi_row([
        ("Busiest band", f"{int(busiest['lower_km'])}–{int(busiest['upper_km'])} km",
         f"{int(busiest['object_count']):,} objects"),
        ("Peak HHI", f"{leo['shell_hhi'].max():.2f}",
         f"@ {int(leo.loc[leo['shell_hhi'].idxmax(), 'lower_km'])} km — single-operator dominance"),
        ("LEO clutter ratio", f"{leo['clutter_ratio'].mean():.2f}",
         "Payloads ÷ all objects across LEO bands"),
        ("Regimes tracked", f"{dens['regime'].nunique()}", None),
    ])

    st.plotly_chart(figures.fig_density_bands(dens), width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(figures.fig_hhi_bands(dens), width="stretch")
    with c2:
        st.plotly_chart(figures.fig_altitude_inclination(objs), width="stretch")

    section("Band detail")
    st.dataframe(
        dens.sort_values("band_start")[
            ["lower_km", "upper_km", "regime", "object_count", "debris_count",
             "payload_count", "rb_count", "density_per_1000km3", "shell_hhi",
             "clutter_ratio"]
        ],
        width="stretch", height=340,
    )


def page_risk_radar() -> None:
    conj = load("fact_conjunction_events")

    kpi_row([
        ("Screened events (7-day)", f"{len(conj):,}", None),
        ("Miss < 1 km", f"{(conj['min_range_km'] < 1).sum():,}", None),
        ("Median miss", f"{conj['min_range_km'].median()*1000:.0f} m", None),
        ("Median closing speed", f"{conj['rel_speed_km_s'].median():.1f} km/s", None),
        ("Max Pc", f"{conj['max_probability'].max():.3f}", None),
    ])

    c1, c2 = st.columns([3, 2])
    with c1:
        st.plotly_chart(figures.fig_risk_matrix(conj), width="stretch")
    with c2:
        st.plotly_chart(figures.fig_conj_timeline(conj), width="stretch")
        regime_mix = (
            conj.groupby("primary_regime", observed=True)
            .agg(events=("event_id", "size"), avg_pc=("max_probability", "mean"))
            .sort_values("events", ascending=False).reset_index()
        )
        st.markdown("##### Screening load & mean Pc by regime")
        st.dataframe(regime_mix, width="stretch", height=250)

    section("Event explorer")
    c1, c2, c3 = st.columns(3)
    regime = c1.selectbox("Primary regime", ["All"] +
                          sorted(conj["primary_regime"].dropna().unique()))
    prob_min = c2.slider("Minimum Pc", 0.0, 0.2, 0.001, 0.001, format="%f")
    miss_max = c3.slider("Max miss distance (km)", 0.05, 25.0, 5.0, 0.05)

    view = conj[(conj["max_probability"] >= prob_min) &
                (conj["min_range_km"] <= miss_max)]
    if regime != "All":
        view = view[view["primary_regime"] == regime]
    st.dataframe(
        view.sort_values("max_probability", ascending=False).head(500),
        width="stretch", height=460,
    )
    st.caption(f"{len(view):,} matching events (showing up to 500)")


def page_league_tables() -> None:
    objs = load("dim_space_object")
    ops = load("dim_operator")
    on = objs[objs["is_on_orbit"]]

    nations = (on.groupby("nation").agg(
        payloads=("object_type", lambda s: int((s == "PAY").sum())),
        rocket_bodies=("object_type", lambda s: int((s == "R/B").sum())),
        debris=("object_type", lambda s: int((s == "DEB").sum())),
    ).assign(total=lambda d: d.sum(axis=1)).nlargest(15, "total"))
    nations["debris_per_payload"] = (
        nations["debris"] / nations["payloads"].replace(0, pd.NA)
    )

    deb_only = on[on["object_type"] == "DEB"].groupby("nation").size()
    kpi_row([
        ("States on orbit", f"{on['nation'].nunique()}", None),
        ("Debris-footprint Gini", f"{gini(deb_only.values):.3f}",
         "0 = evenly shared responsibility, →1 = concentrated"),
        ("Worst debris/payload ratio",
         f"{nations['debris_per_payload'].max():.1f}×",
         f"{nations['debris_per_payload'].idxmax()}"),
        ("Attributed to curated operators", f"{int((on['operator_id'] > 0).sum()):,}", None),
    ])

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(figures.fig_nation_footprint(objs), width="stretch")
    with c2:
        st.plotly_chart(figures.fig_lorenz_debris(objs), width="stretch")

    st.plotly_chart(figures.fig_responsibility_frontier(objs), width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        section("National league table (on-orbit)")
        st.dataframe(nations, width="stretch", height=420)
    with c2:
        section("Constellation operator league")
        attributed = (on[on["operator_id"] > 0].groupby("operator_id")
                      .size().rename("on_orbit_objects"))
        league = ops.set_index("operator_id").join(attributed).fillna({"on_orbit_objects": 0})
        league["share_of_attributed"] = (
            league["on_orbit_objects"] / league["on_orbit_objects"].sum()
        )
        st.plotly_chart(
            figures.fig_operator_share(league.reset_index()[["operator_name", "on_orbit_objects"]]
                                       .set_index("operator_name")),
            width="stretch")
        st.dataframe(league[["operator_name", "nation", "constellation_name",
                             "on_orbit_objects", "share_of_attributed"]],
                     width="stretch", height=300)

    section("Historical context")
    st.plotly_chart(figures.fig_launch_cadence(objs), width="stretch")


def page_catalog_crisis() -> None:
    growth = load("fact_catalog_growth")
    days_since = (growth["date"].max() - SARAMAGO_DAY).days
    six_digit_objs = load("dim_space_object")
    n_six = int((six_digit_objs["object_id"] >= 100_000).sum())

    kpi_row([
        ("Days since overflow", f"{days_since}", "Saramago cataloged 2026-07-11"),
        ("Public catalog size", f"{int(growth['cumulative_catalog_size'].iloc[-1]):,}", None),
        ("Official counter", f"{OFFICIAL_COUNTER:,}",
         "Includes unpublished 7xxxx–9xxxx block"),
        ("Six-digit IDs in our layers", f"{n_six:,}",
         "TLE pipelines would drop every one of these"),
    ])

    st.plotly_chart(figures.fig_growth_eras(growth), width="stretch")
    st.plotly_chart(figures.fig_new_objects_daily(growth), width="stretch")

    st.markdown(
        """
##### Why the numbering crisis matters for data engineering

The legacy fixed-field SATCAT/TLE format can only express catalog numbers below
**70,000**, and TLE cannot represent IDs above **99,999** at all. The *official*
USSF counter passed **100,403** on 2026-07-11 ("SARAMAGO"), but CelesTrak's public
interface still serves only the ~70k legacy-numbered population plus newly numbered
six-digit objects — the reserved 7xxxx–9xxxx block was never published.

This project ingests **OMM JSON/CSV exclusively**, so every six-digit-ID satellite
already flying is present in Bronze, Silver and Gold. A TLE-based pipeline built
in June 2026 would now be silently missing all of them.
"""
    )


def page_globe() -> None:
    gp = load_gp()
    regimes = st.multiselect(
        "Regimes shown", sorted(gp["regime"].dropna().unique()),
        default=["VLEO", "LEO-Constellation", "Legacy-Debris"],
    )
    valid = gp[gp["is_valid"] & gp["regime"].isin(regimes)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Objects plotted (sampled)", f"{min(len(valid), 6000):,}")
    c2.metric("Unique objects in selection", f"{len(valid):,}")
    c3.metric("Stale elements", f"{int(valid['is_stale'].sum()):,}",
              help="Epoch older than 14 days")
    c4.metric("Frame", "TEME (inertial)")

    st.plotly_chart(figures.fig_3d_snapshot(valid), width="stretch")
    st.plotly_chart(figures.fig_stale_split(gp), width="stretch")


def page_explorer() -> None:
    st.caption("Whitelisted analytical presets compiled against the Gold layer. "
               "No free-form SQL is accepted — same deterministic pattern as a production "
               "semantic layer.")
    picked = st.pills("Preset", list(EXPLORER_PRESETS), default=list(EXPLORER_PRESETS)[0])
    if picked is None:
        st.stop()
    st.code(EXPLORER_PRESETS[picked], language="sql")
    df = preset_query(picked)
    st.dataframe(df, width="stretch", height=520)
    st.download_button("Download CSV", df.to_csv(index=False).encode(),
                       file_name=f"{picked[:40].replace(' ', '_')}.csv",
                       mime="text/csv")


def page_methodology() -> None:
    topn = load("analytics_foster_topn")
    silver_qr = SILVER_DIR / "_quality_report.json"

    kpi_row([
        ("Propagation engine", "SGP4", "via skyfield EarthSatellite.from_omm"),
        ("Coordinate transform", "TEME→WGS84", "Skyfield ITRS machinery"),
        ("Pc method", "Foster/Chan 2D", "spherical covariance assumption"),
        ("Validation gates", "3", "perigee/ecc/sgp4-error"),
    ])

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(figures.fig_foster_benchmark(topn), width="stretch")
    with c2:
        st.plotly_chart(figures.fig_foster_ratio_hist(topn), width="stretch")

    section("Silver-layer quality report (latest build)")
    if silver_qr.exists():
        import json
        qr = json.loads(silver_qr.read_text(encoding="utf-8"))
        st.json(qr, expanded=False)
    section("Reference document")
    ref = Path(__file__).parents[2] / "technical_reference.md"
    st.markdown(ref.read_text(encoding="utf-8")[:9_000])


# ---------------------------------------------------------------- navigation

PAGES = [
    st.Page(page_mission_control, title="Mission Control", icon="🛰", default=True),
    st.Page(page_risk_radar, title="Conjunction Radar", icon="⚠️"),
    st.Page(page_congestion_atlas, title="Congestion Atlas", icon="🗺️"),
    st.Page(page_league_tables, title="League Tables", icon="🏆"),
    st.Page(page_catalog_crisis, title="Catalog Crisis", icon="🚨"),
    st.Page(page_globe, title="3D Snapshot", icon="🌐"),
    st.Page(page_explorer, title="Explorer", icon="🔎"),
    st.Page(page_methodology, title="Methodology", icon="📐"),
]

nav = st.navigation(PAGES, position="top")
nav.run()
