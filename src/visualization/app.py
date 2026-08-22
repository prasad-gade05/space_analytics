"""Orbital Commons — mission console (Streamlit, top navigation).

Run:  streamlit run src/visualization/app.py
Reads committed Gold-layer parquet exports; no DB locking, deploy-friendly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analytics.metrics import gini, hhi  # noqa: E402
from src.utils.paths import GOLD_EXPORTS_DIR, SILVER_DIR  # noqa: E402
from src.visualization import figures  # noqa: E402

st.set_page_config(page_title="Orbital Commons", page_icon=None,
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
    # NOTE: DuckDB DDL cannot bind prepared parameters; paths are local,
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

def visual(fig, note: str, **kwargs):
    """Render a figure followed by a one-line plain-English explanation."""
    st.plotly_chart(fig, width="stretch", **kwargs)
    st.caption(note)


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
    inv = load("fact_orbital_inventory")
    on = objs[objs["is_on_orbit"]]
    next24 = conj[conj["tca_utc"] <= conj["tca_utc"].min() + pd.Timedelta(days=1)]
    worst = next24.loc[next24["max_probability"].idxmax()]

    kpi_row([
        ("Public catalog (all-time)", f"{len(objs):,}",
         "Objects publicly queryable via CelesTrak SATCAT"),
        ("On-orbit tracked", f"{len(on):,}", "No decay date in latest snapshot"),
        ("Debris share on orbit", f"{(on['object_type'] == 'DEB').mean():.0%}", None),
        ("Official counter gap", f"{OFFICIAL_COUNTER - len(objs):,}",
         "Max-assigned number minus public rows: withheld 7xxxx–9xxxx block"),
        ("Events next 24 h", f"{len(next24):,}", None),
        ("Top Pc next 24 h", f"{worst['max_probability']:.3f}", None),
        ("Events Pc ≥ 1%", f"{(conj['max_probability'] >= 0.01).sum():,}", None),
        ("Catalog growth yesterday", f"+{int(growth['new_objects_added'].iloc[-1]):,}", None),
    ])

    st.info(
        f"Highest-risk encounter in the next 24h: **{worst['primary_name']}** vs "
        f"**{worst['secondary_name']}** - miss **{worst['min_range_km']*1000:.0f} m**, "
        f"Pc **{worst['max_probability']:.3f}** at {worst['tca_utc']:%Y-%m-%d %H:%M} UTC "
        f"- closing speed {worst['rel_speed_km_s']:.1f} km/s"
    )

    c1, c2 = st.columns(2)
    with c1:
        visual(figures.fig_regime_inventory(inv),
               "How many tracked objects sit at each altitude class, stacked by type "
               "(payloads = working satellites, R/B = spent rocket stages, DEB = junk).")
    with c2:
        visual(figures.fig_type_donut(objs),
               "Of everything currently up there, how much is still useful vs junk.")

    c1, c2 = st.columns(2)
    with c1:
        visual(figures.fig_growth_eras(growth),
               "The catalog has only ever grown. Pink marks the day 5-digit IDs ran out; "
               "the dashed line is the true official count including withheld entries.")
    with c2:
        visual(figures.fig_conj_timeline(conj),
               "How many close-approach warnings the weekly screen produced for each "
               "upcoming day. More events = busier week ahead.")

    section("Top risks this week and who owns them")
    c1, c2 = st.columns([3, 2])
    with c1:
        show = next24.nlargest(8, "max_probability")[
            ["primary_name", "secondary_name", "tca_utc",
             "min_range_km", "max_probability"]
        ].copy()
        show["min_range_km"] = ((show["min_range_km"] * 1000).round(0).astype(int)
                                .astype(str) + " m")
        show.columns = ["Primary", "Secondary", "TCA (UTC)", "Miss", "Pc"]
        st.dataframe(show, width="stretch", height=320, hide_index=True)
        st.caption("The eight closest-scored encounters forecast for tomorrow; Pc is the "
                   "probability of collision reported by SOCRATES.")
    with c2:
        attributed = (on[on["operator_id"] > 0].groupby("operator_id")
                      .size().rename("on_orbit_objects"))
        league = load("dim_operator").set_index("operator_id").join(attributed)
        league = league.dropna(subset=["on_orbit_objects"]).nlargest(6, "on_orbit_objects")
        visual(figures.fig_operator_share(
            league.reset_index()[["operator_name", "on_orbit_objects"]]
            .set_index("operator_name")),
            "Which constellation operators own the most of what's up there right now.")


def page_risk_radar() -> None:
    conj = load("fact_conjunction_events")

    kpi_row([
        ("Screened events (7-day)", f"{len(conj):,}", None),
        ("Miss < 1 km", f"{(conj['min_range_km'] < 1).sum():,}", None),
        ("Median miss", f"{conj['min_range_km'].median()*1000:.0f} m", None),
        ("Median closing speed", f"{conj['rel_speed_km_s'].median():.1f} km/s", None),
        ("Max Pc", f"{conj['max_probability'].max():.3f}", None),
    ])

    visual(figures.fig_risk_matrix(conj),
           "Every screened event as a dot: left = closer passes, up = higher collision "
           "probability. The dangerous corner is top-left.")

    c1, c2, c3 = st.columns(3)
    with c1:
        visual(figures.fig_hist(conj["max_probability"],
                                "Collision probability distribution", "Pc",
                                color="#e63946"),
               "Almost all passes are harmless (far-left); the tiny right tail is what "
               "operators lose sleep over.")
    with c2:
        visual(figures.fig_hist(conj["min_range_km"], "Miss distance distribution",
                                "Miss distance (km, log)"),
               "How close things actually get. Each step left means ten times closer.")
    with c3:
        visual(figures.fig_hist(conj["rel_speed_km_s"], "Closing speed distribution",
                                "Relative speed (km/s)", color="#f8961e", log_x=False),
               "Two bumps: slow same-orbit drifts (left bump) and head-on LEO "
               "crossings near 14 km/s (right bump). Faster = far more energy.")

    visual(figures.fig_conj_timeline(conj), "Warning volume per forecast day.")

    c1, c2 = st.columns([2, 3])
    with c2:
        visual(figures.fig_nation_pair_bar(conj),
               "Which countries' objects keep meeting each other. A few pairs dominate.")
    with c1:
        regime_mix = (
            conj.groupby("primary_regime", observed=True)
            .agg(events=("event_id", "size"), avg_pc=("max_probability", "mean"))
            .sort_values("events", ascending=False).reset_index()
        )
        regime_mix["avg_pc"] = regime_mix["avg_pc"].map("{:.2e}".format)
        regime_mix.columns = ["Regime", "Events", "Mean Pc"]
        st.markdown("##### Screening load by regime")
        st.dataframe(regime_mix, width="stretch", height=440, hide_index=True)
        st.caption("Where conjunction screening effort concentrates this week.")

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
    st.dataframe(view.sort_values("max_probability", ascending=False).head(500),
                 width="stretch", height=420, hide_index=True)
    st.caption(f"{len(view):,} matching events (showing up to 500)")


def page_congestion_atlas() -> None:
    dens = load("fact_spatial_density")
    objs = load("dim_space_object")
    leo = dens[dens["band_start"] >= 100]
    busiest = leo.loc[leo["object_count"].idxmax()]

    kpi_row([
        ("Busiest band", f"{int(busiest['lower_km'])}-{int(busiest['upper_km'])} km",
         f"{int(busiest['object_count']):,} objects"),
        ("Peak HHI", f"{leo['shell_hhi'].max():.2f}",
         f"@ {int(leo.loc[leo['shell_hhi'].idxmax(), 'lower_km'])} km band"),
        ("LEO clutter ratio", f"{leo['clutter_ratio'].mean():.2f}",
         "Payload share across LEO bands"),
        ("Objects above 2,000 km", f"{int((objs[objs['is_on_orbit'] & objs['regime'].notna()]['regime'].isin(['MEO','GEO','HEO/Deep-Space'])).sum()):,}",
         None),
    ])

    visual(figures.fig_density_bands(dens),
           "Object population per 25-km altitude slice. The towers show where traffic "
           "piles up - notably the 450-600 km Starlink neighbourhood.")

    c1, c2 = st.columns(2)
    with c1:
        visual(figures.fig_hhi_bands(dens),
               "Concentration of ownership per band (HHI). Red bands are effectively "
               "run by one operator or state, like a market monopoly.")
    with c2:
        visual(figures.fig_band_composition(dens),
               "Within each slice: what fraction is useful payload vs rocket bodies vs "
               "debris. Orange+red = legacy junk zones.")

    c1, c2 = st.columns(2)
    with c1:
        visual(figures.fig_altitude_inclination(objs),
               "A map of orbits: horizontal = height, vertical = tilt. Bright streaks "
               "are popular orbital highways (53 deg = Starlink shells, 98 deg = "
               "sun-synchronous Earth-observation lanes).")
    with c2:
        visual(figures.fig_clutter_line(dens),
               "Useful-share line: high values are busy commercial shells, low values "
               "are abandoned junk belts around 800-1,000 km.")

    c1, c2 = st.columns([3, 2])
    with c1:
        visual(figures.fig_alt_cdf(objs),
               "Read it as: half of all tracked objects live below the first dotted "
               "line's altitude.")
    with c2:
        section("Band detail")
        tbl = dens.sort_values("band_start")[
            ["lower_km", "upper_km", "object_count", "debris_count",
             "shell_hhi", "clutter_ratio"]
        ].copy()
        tbl.columns = ["Low km", "High km", "Objects", "Debris", "HHI", "Payload share"]
        st.dataframe(tbl, width="stretch", height=380, hide_index=True)


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
         "0 = evenly shared responsibility, toward 1 = concentrated"),
        ("Worst debris/payload ratio", f"{nations['debris_per_payload'].max():.1f}x",
         f"{nations['debris_per_payload'].idxmax()}"),
        ("Attributed to curated operators", f"{int((on['operator_id'] > 0).sum()):,}", None),
    ])

    c1, c2 = st.columns(2)
    with c1:
        visual(figures.fig_nation_footprint(objs),
               "Each state's on-orbit estate: blue payloads they operate, orange spent "
               "rockets, red junk their launches left behind (log scale).")
    with c2:
        visual(figures.fig_lorenz_debris(objs),
               "If debris responsibility were shared equally the curve would hug the "
               "diagonal; sagging under it means a few states hold most of the mess.")

    visual(figures.fig_responsibility_frontier(objs),
           "Countries above the dashed line carry more junk than active assets; below "
           "it means their presence is mostly productive hardware.")

    c1, c2 = st.columns([2, 3])
    with c1:
        section("National league table (on-orbit)")
        st.dataframe(nations.reset_index(), width="stretch", height=400, hide_index=True)
    with c2:
        attributed = (on[on["operator_id"] > 0].groupby("operator_id")
                      .size().rename("on_orbit_objects"))
        league = ops.set_index("operator_id").join(attributed).fillna({"on_orbit_objects": 0})
        league["share_of_attributed"] = (
            league["on_orbit_objects"] / league["on_orbit_objects"].sum()
        )
        visual(figures.fig_operator_share(
            league.reset_index()[["operator_name", "on_orbit_objects"]]
            .set_index("operator_name")),
            "Constellation operators ranked by objects in orbit today.")
        st.dataframe(league.reset_index()[["operator_name", "nation",
                                           "constellation_name", "on_orbit_objects"]],
                     width="stretch", height=180, hide_index=True)

    visual(figures.fig_launch_cadence(objs),
           "Six decades of launch activity. The post-2019 wall is the "
           "mega-constellation era.")


def page_catalog_crisis() -> None:
    growth = load("fact_catalog_growth")
    days_since = (growth["date"].max() - SARAMAGO_DAY).days
    objs = load("dim_space_object")
    n_six = int((objs["object_id"] >= 100_000).sum())

    kpi_row([
        ("Days since overflow", f"{days_since}", "Saramago cataloged 2026-07-11"),
        ("Public catalog size", f"{int(growth['cumulative_catalog_size'].iloc[-1]):,}", None),
        ("Official counter", f"{OFFICIAL_COUNTER:,}",
         "Includes unpublished 7xxxx-9xxxx block"),
        ("Six-digit IDs in our layers", f"{n_six:,}",
         "TLE pipelines would drop every one of these"),
    ])

    visual(figures.fig_growth_eras(growth),
           "Full growth history colored by numbering era. The pink dashes mark the "
           "official count that includes withheld objects - the gap to our public "
           "curve is the hidden catalog.")
    visual(figures.fig_new_objects_daily(growth),
           "Daily additions minus removals. Spikes usually mean new constellations "
           "deploying or breakup events.")

    c1, c2 = st.columns(2)
    with c1:
        visual(figures.fig_month_heatmap(growth),
               "Brighter cells = more new objects that month. Recent columns glow as "
               "constellations scale.")
    with c2:
        visual(figures.fig_crossing_projection(growth),
               "Naive trendline: if growth simply continues, when does the public "
               "catalog itself approach six-digit saturation? Back-of-envelope, not a "
               "forecast model.")

    visual(figures.fig_era_timeline(),
           "Three numbering regimes side by side - note how short the current era is.")

    with st.expander("Why this matters for data engineering"):
        st.markdown(
            """
The legacy fixed-field SATCAT/TLE format can only express catalog numbers below
70,000, and TLE cannot represent IDs above 99,999 at all. The *official* USSF
counter passed 100,403 on 2026-07-11 ("SARAMAGO"), but CelesTrak's public interface
still serves only the ~70k legacy-numbered population plus newly numbered six-digit
objects - the reserved 7xxxx-9xxxx block was never published.

This project ingests OMM JSON/CSV exclusively, so every six-digit-ID satellite
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

    kpi_row([
        ("Objects plotted (sampled)", f"{min(len(valid), 5000):,}", None),
        ("Unique objects in selection", f"{len(valid):,}", None),
        ("Stale elements (>14 d)", f"{int(valid['is_stale'].sum()):,}",
         "Older element sets propagate less accurately"),
        ("Frame", "TEME + WGS84 subpoints", None),
    ])

    visual(figures.fig_ground_track(valid),
           "Where each selected object sat directly above Earth when its orbit was "
           "last measured - a global snapshot of who flies where.")

    visual(figures.fig_3d_snapshot(valid),
           "Same selection in inertial space: the rings are individual orbits seen "
           "edge-on. Drag to rotate.")

    visual(figures.fig_stale_split(gp),
           "Freshness check: blue = measured within two weeks (trustworthy), red = "
           "older elements whose predicted positions drift.")


def page_explorer() -> None:
    st.caption("Whitelisted analytical presets compiled against the Gold layer. "
               "No free-form SQL is accepted - deterministic semantic layer pattern.")
    picked = st.pills("Preset", list(EXPLORER_PRESETS), default=list(EXPLORER_PRESETS)[0])
    if picked is None:
        st.stop()
    st.code(EXPLORER_PRESETS[picked], language="sql")
    df = preset_query(picked)
    kpi_row([("Rows returned", f"{len(df):,}", None)])
    st.dataframe(df, width="stretch", height=520, hide_index=True)
    st.download_button("Download CSV", df.to_csv(index=False).encode(),
                       file_name=f"{picked[:40].replace(' ', '_')}.csv",
                       mime="text/csv")


def page_methodology() -> None:
    topn = load("analytics_foster_topn")
    silver_qr = SILVER_DIR / "_quality_report.json"

    t1, t2, t3, t4 = st.tabs(["Pipeline", "Validation & quality",
                              "Foster benchmark", "Sources & exclusions"])

    with t1:
        st.markdown(
            """
**Medallion flow:** raw bytes (Bronze) -> physics-clean tables (Silver) ->
star schema (Gold) -> this console.

| Stage | What happens |
|---|---|
| Bronze | Byte-faithful CelesTrak downloads + SHA-256 manifests; OMM JSON only (never TLE) |
| Silver | Dedup by NORAD ID, SGP4 propagation at epoch, TEME->WGS84 transform, validation gates |
| Gold   | DuckDB star schema: 4 dimensions, 4 facts + Foster benchmark table |

Propagation uses Skyfield (`EarthSatellite.from_omm`); geometry constants
mu = 398600.4418 km3/s2, Earth radius 6378.137 km.
"""
        )

    with t2:
        if silver_qr.exists():
            qr = json.loads(silver_qr.read_text(encoding="utf-8"))
            gpq = qr.get("gp_objects", {})
            kpi_row([
                ("GP objects valid", f"{gpq.get('valid', 0):,}", None),
                ("GP rejected", f"{gpq.get('rejected', 0):,}", None),
                ("Stale epochs >14 d", f"{gpq.get('stale', 0):,}", None),
                ("SATCAT rows", f"{qr.get('satcat', {}).get('rows', 0):,}", None),
                ("On-orbit", f"{qr.get('satcat', {}).get('on_orbit', 0):,}", None),
            ])
        st.caption(
            "Rejection gates keep bad records visible instead of dropping them "
            "silently: non-positive mean motion, eccentricity outside [0,1), and "
            "SGP4 propagation failures. Cross-check performed on build day: SATCAT "
            "on-orbit count equals CelesTrak's official growth-series final value."
        )
        with st.expander("Raw quality report JSON"):
            if silver_qr.exists():
                st.json(json.loads(silver_qr.read_text(encoding="utf-8")))

    with t3:
        c1, c2 = st.columns(2)
        with c1:
            visual(figures.fig_foster_benchmark(topn),
                   "Our independently computed collision probability vs the operator-"
                   "grade number SOCRATES publishes, log-log.")
        with c2:
            visual(figures.fig_foster_ratio_hist(topn),
                   "Ratios cluster under 1x: our spherical-covariance shortcut is "
                   "conservative; big outliers flag covariance-sensitive cases.")
        st.caption(
            "Assumptions (CARA/Foster short-encounter model): linear relative motion, "
            "spherical hard-body radius R = 20 m combined, uncorrelated Gaussian "
            "covariance with sigma taken from SOCRATES DILUTION. Validated against the "
            "analytic zero-miss limit Pc = 1 - exp(-R^2/2 sigma^2) to <1%."
        )

    with t4:
        st.markdown(
            """
| Source | Used for | Access |
|---|---|---|
| CelesTrak GP API | orbital elements (OMM JSON) | free, no account |
| CelesTrak SATCAT sweep | full catalog metadata | free, documented query |
| CelesTrak SOCRATES Plus | conjunction events + Pc | free, bulk CSV |
| NASA ODQN | validation benchmarks | free PDFs |
| Space-Track.org | deliberately excluded (gated, 30-day approval) | n/a |
| ESA DISCOS | excluded (member-state gating) | n/a |

Usage policy compliance: identified User-Agent, polite pacing (>=3 s; 10 s during
historical sweeps), incremental caching so steady-state costs ~2 requests/day.
"""
        )


PAGES = [
    st.Page(page_mission_control, title="Mission Control", default=True),
    st.Page(page_risk_radar, title="Conjunction Radar"),
    st.Page(page_congestion_atlas, title="Congestion Atlas"),
    st.Page(page_league_tables, title="League Tables"),
    st.Page(page_catalog_crisis, title="Catalog Crisis"),
    st.Page(page_globe, title="Orbit Explorer 3D"),
    st.Page(page_explorer, title="Explorer"),
    st.Page(page_methodology, title="Methodology"),
]

nav = st.navigation(PAGES, position="top")
nav.run()
