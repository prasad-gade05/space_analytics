"""Orbital Commons — mission console (Streamlit).

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
from src.visualization import figures  # noqa: E402
from src.utils.paths import GOLD_EXPORTS_DIR, SILVER_DIR  # noqa: E402

st.set_page_config(page_title="Orbital Commons", page_icon="🛰", layout="wide")


@st.cache_data(ttl=3600)
def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(GOLD_EXPORTS_DIR / f"{name}.parquet")


@st.cache_data(ttl=3600)
def load_gp() -> pd.DataFrame:
    return pd.read_parquet(SILVER_DIR / "gp_objects.parquet")


def sql(preset: str) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        con.execute("CREATE VIEW conj AS SELECT * FROM read_parquet(?)",
                    [str(GOLD_EXPORTS_DIR / "fact_conjunction_events.parquet")])
        con.execute("CREATE VIEW objs AS SELECT * FROM read_parquet(?)",
                    [str(GOLD_EXPORTS_DIR / "dim_space_object.parquet")])
        return con.execute(preset).fetchdf()
    finally:
        con.close()


EXPLORER_PRESETS: dict[str, str] = {
    "Closest approaches overall (< 100 m)": """
        SELECT primary_name, secondary_name, tca_utc, min_range_km,
               rel_speed_km_s, max_probability
        FROM conj WHERE min_range_km < 0.1 ORDER BY min_range_km LIMIT 200""",
    "Fastest encounters (> 14 km/s)": """
        SELECT primary_name, secondary_name, tca_utc, rel_speed_km_s,
               min_range_km, max_probability
        FROM conj WHERE rel_speed_km_s > 14 ORDER BY rel_speed_km_s DESC LIMIT 200""",
    "Highest-risk events this week": """
        SELECT primary_name, secondary_name, tca_utc, min_range_km,
               max_probability FROM conj
        ORDER BY max_probability DESC LIMIT 200""",
    "Debris involved in conjunctions": """
        SELECT primary_name, secondary_name, primary_regime, min_range_km,
               max_probability
        FROM conj
        WHERE primary_name LIKE '%DEB%' OR secondary_name LIKE '%DEB%'
        ORDER BY max_probability DESC LIMIT 200""",
    "Oldest objects still on orbit": """
        SELECT object_id, name, intl_designator, nation, launch_date, regime
        FROM objs WHERE is_on_orbit AND launch_date IS NOT NULL
        ORDER BY launch_date LIMIT 100""",
    "Six-digit catalog era objects": """
        SELECT object_id, name, intl_designator, launch_date, owner_code, nation
        FROM objs WHERE object_id >= 100000 ORDER BY object_id LIMIT 500""",
}


def page_mission_control() -> None:
    objs = load("dim_space_object")
    growth = load("fact_catalog_growth")
    conj = load("fact_conjunction_events")
    on = objs[objs["is_on_orbit"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Public catalog (all time)", f"{len(objs):,}")
    c2.metric("On-orbit tracked", f"{len(on):,}",
              help="Objects with no decay date in today's snapshot")
    c3.metric("Debris share on orbit",
              f"{(on['object_type'] == 'DEB').mean():.0%}")
    c4.metric("Official counter (USSF)", "100,403",
              delta="+6-digit era", delta_color="off",
              help="Max catalog number assigned incl. unpublished 7xxxx-9xxxx block")

    c1, c2, c3, c4 = st.columns(4)
    next24 = conj[conj["tca_utc"] <= conj["tca_utc"].min() + pd.Timedelta(days=1)]
    worst = next24.loc[next24["max_probability"].idxmax()]
    c1.metric("Events next 24 h", f"{len(next24):,}")
    c2.metric("Top Pc next 24 h", f"{worst['max_probability']:.3f}")
    c3.metric("Events Pc ≥ 1%", f"{(conj['max_probability'] >= 0.01).sum():,}")
    c4.metric("New objects added yesterday",
              f"{int(growth['new_objects_added'].iloc[-1]):,}")

    st.caption(
        f"Highest-risk encounter in the next 24h: **{worst['primary_name']}** vs "
        f"**{worst['secondary_name']}** — miss {worst['min_range_km']*1000:.0f} m, "
        f"Pc {worst['max_probability']:.3f}"
    )

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(figures.fig_regime_inventory(load("fact_orbital_inventory")),
                        use_container_width=True)
    with right:
        st.plotly_chart(figures.fig_growth_eras(growth), use_container_width=True)


def page_globe() -> None:
    st.caption("SGP4-propagated positions at each element's epoch, TEME inertial frame. "
               "Sampled for performance.")
    gp = load_gp()
    regimes = st.multiselect("Regimes", sorted(gp["regime"].dropna().unique()),
                             default=["LEO-Constellation", "LEO-SSO"])
    st.plotly_chart(figures.fig_3d_snapshot(gp[gp["regime"].isin(regimes)]),
                    use_container_width=True)


def page_risk_radar() -> None:
    conj = load("fact_conjunction_events")
    c1, c2, c3 = st.columns(3)
    regime = c1.selectbox("Primary regime", ["All"] + sorted(
        conj["primary_regime"].dropna().unique()))
    prob_min = c2.slider("Minimum Pc", 0.0, 0.2, 0.001, 0.001, format="%f")
    miss_max = c3.slider("Max miss distance (km)", 0.05, 25.0, 5.0, 0.05)

    view = conj[
        (conj["max_probability"] >= prob_min) & (conj["min_range_km"] <= miss_max)
    ]
    if regime != "All":
        view = view[view["primary_regime"] == regime]
    view = view.sort_values("max_probability", ascending=False)
    st.dataframe(view.head(500), use_container_width=True, height=520)
    st.caption(f"{len(view):,} matching events (showing up to 500)")


def page_density() -> None:
    dens = load("fact_spatial_density")
    st.plotly_chart(figures.fig_density_bands(dens), use_container_width=True)
    st.plotly_chart(figures.fig_hhi_bands(dens), use_container_width=True)
    with st.expander("Band table"):
        st.dataframe(dens.sort_values("band_start"), use_container_width=True)


def page_league_tables() -> None:
    objs = load("dim_space_object")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(figures.fig_nation_footprint(objs), use_container_width=True)
    with right:
        st.plotly_chart(figures.fig_lorenz_debris(objs), use_container_width=True)

    on = objs[objs["is_on_orbit"]]
    nations = on.groupby("nation").agg(
        payloads=("object_type", lambda s: int((s == "PAY").sum())),
        debris=("object_type", lambda s: int((s == "DEB").sum())),
        rocket_bodies=("object_type", lambda s: int((s == "R/B").sum())),
    ).assign(total=lambda d: d.sum(axis=1)).nlargest(15, "total")
    nations["debris_per_payload"] = (
        nations["debris"] / nations["payloads"].replace(0, pd.NA)
    )
    st.markdown("#### National league table (on-orbit)")
    st.dataframe(nations, use_container_width=True)

    ops = load("dim_operator")
    attributed = on[on["operator_id"] > 0].groupby("operator_id").size()
    league = ops.set_index("operator_id").join(attributed.rename("on_orbit_objects"))
    league["share_of_attributed"] = (
        league["on_orbit_objects"] / league["on_orbit_objects"].sum()
    )
    st.markdown(f"#### Constellation operators — HHI "
                f"{hhi(league['on_orbit_objects'].fillna(0)):.3f}")
    st.dataframe(league, use_container_width=True)


def page_catalog_crisis() -> None:
    st.plotly_chart(figures.fig_growth_eras(load("fact_catalog_growth")),
                    use_container_width=True)
    st.markdown(
        """
        **Why the pink line matters.** The legacy fixed-field SATCAT/TLE format can
        only express catalog numbers below **70,000**, and TLE cannot represent IDs
        above 99,999 at all. The *official* USSF counter passed **100,403** on
        2026-07-11 ("SARAMAGO"), but CelesTrak's public query interface still serves
        only the ~70k legacy-numbered population plus newly numbered six-digit
        objects. Any pipeline built on TLE silently drops everything new.

        This project ingests **OMM JSON/CSV exclusively**, so the 331+ six-digit-ID
        satellites already flying are present in every layer.
        """
    )


def page_explorer() -> None:
    preset = st.selectbox("Preset query", list(EXPLORER_PRESETS))
    st.code(EXPLORER_PRESETS[preset], language="sql")
    if st.button("Run"):
        st.dataframe(sql(EXPLORER_PRESETS[preset]), use_container_width=True)


def page_methodology() -> None:
    st.markdown(open(Path(__file__).parents[2] / "technical_reference.md",
                     encoding="utf-8").read()[:12_000])


PAGES = {
    "Mission Control": page_mission_control,
    "3D Snapshot": page_globe,
    "Conjunction Risk Radar": page_risk_radar,
    "Altitude & Density": page_density,
    "League Tables": page_league_tables,
    "Catalog Crisis": page_catalog_crisis,
    "Explorer": page_explorer,
    "Methodology": page_methodology,
}

page = st.sidebar.radio("Navigate", list(PAGES), format_func=str)
PAGES[page]()
