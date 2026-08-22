import pandas as pd
import plotly.graph_objects as go
import pytest

from src.visualization import figures


@pytest.fixture
def inv():
    return pd.DataFrame({
        "date_key": [pd.Timestamp("2026-08-22")] * 3,
        "shell_id": [2, 2, 3],
        "regime": ["LEO-Constellation", "LEO-Constellation", "LEO-SSO"],
        "object_type": ["PAY", "DEB", "PAY"],
        "object_count": [12000, 300, 2500],
        "active_payload_count": [9000, 0, 10],
    })


@pytest.fixture
def dens():
    return pd.DataFrame({
        "band_start": [100, 125, 450, 475, 550, 800],
        "lower_km": [100.0, 125.0, 450.0, 475.0, 550.0, 800.0],
        "upper_km": [125.0, 150.0, 475.0, 500.0, 575.0, 825.0],
        "regime": ["VLEO"] * 2 + ["LEO-Constellation"] * 3 + ["LEO-SSO"],
        "object_count": [10, 20, 5000, 3800, 1000, 900],
        "debris_count": [2, 1, 30, 25, 90, 650],
        "payload_count": [6, 15, 4950, 3750, 880, 80],
        "rb_count": [2, 4, 20, 25, 30, 170],
        "density_per_1000km3": [1e-6] * 6,
        "shell_hhi": [.1, .2, .92, .83, .59, .32],
        "clutter_ratio": [.6, .75, .99, .98, .88, .09],
    })


def test_regime_inventory(inv):
    fig = figures.fig_regime_inventory(inv)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2  # PAY + DEB present


def test_density_and_hhi(dens):
    f1 = figures.fig_density_bands(dens)
    f2 = figures.fig_hhi_bands(dens)
    assert isinstance(f1, go.Figure) and isinstance(f2, go.Figure)
    xs = list(f2.data[0].x)  # bands below 350 km excluded from HHI view
    assert all(int(x.split()[0]) >= 350 for x in xs)


def test_growth_eras():
    growth = pd.DataFrame({
        "date": pd.to_datetime(["1957-01-01", "2020-04-30", "2020-05-01",
                                "2026-07-10", "2026-07-11", "2026-08-21"]),
        "cumulative_catalog_size": [1, 45_000, 45_001, 69_970, 70_000, 70_355],
        "format_type": ["5-digit", "5-digit", "alpha5-capable",
                        "alpha5-capable", "6-digit", "6-digit"],
    })
    fig = figures.fig_growth_eras(growth)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3  # one trace per era


def test_nation_and_lorenz():
    dim_obj = pd.DataFrame({
        "nation": ["United States"] * 3 + ["China"] * 2,
        "is_on_orbit": [True] * 5,
        "object_type": ["DEB", "PAY", "R/B", "DEB", "PAY"],
    })
    assert isinstance(figures.fig_nation_footprint(dim_obj), go.Figure)
    assert isinstance(figures.fig_lorenz_debris(dim_obj), go.Figure)


def test_foster_benchmark():
    topn = pd.DataFrame({
        "primary_name": ["A"], "secondary_name": ["B"],
        "max_probability": [0.19], "foster_pc": [0.57],
        "pc_ratio_ours_vs_socrates": [2.97],
    })
    assert isinstance(figures.fig_foster_benchmark(topn), go.Figure)


def test_3d_snapshot():
    gp = pd.DataFrame({
        "norad_cat_id": [1, 2], "object_name": ["X", "Y"],
        "teme_x_km": [7000.0, None], "teme_y_km": [0.0, None], "teme_z_km": [0.0, None],
        "is_valid": [True, True], "regime": ["VLEO", "MEO"],
    })
    assert isinstance(figures.fig_3d_snapshot(gp), go.Figure)


def test_new_objects_daily():
    growth = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-19", "2026-08-20", "2026-08-21"]),
        "new_objects_added": [0, 3, 0],
        "new_decayed": [0, 4, 0],
    })
    assert isinstance(figures.fig_new_objects_daily(growth), go.Figure)


def test_conj_timeline_and_risk_matrix():
    conj = pd.DataFrame({
        "tca_utc": pd.to_datetime(["2026-08-23 04:00", "2026-08-23 06:00",
                                   "2026-08-24 05:00", "2026-08-25 07:00"]),
        "min_range_km": [0.016, 1.2, 5.0, 12.0],
        "max_probability": [0.19, 1e-4, 1e-6, 1e-8],
        "rel_speed_km_s": [14.9, 7.0, 10.0, 3.0],
        "primary_regime": ["LEO-Constellation", "LEO-SSO", "MEO", None],
        "primary_name": ["A", "B", "C", "D"],
        "secondary_name": ["E", "F", "G", "H"],
    })
    assert isinstance(figures.fig_conj_timeline(conj), go.Figure)
    assert isinstance(figures.fig_risk_matrix(conj), go.Figure)


def test_altitude_inclination_launch_cadence():
    objs = pd.DataFrame({
        "is_on_orbit": [True] * 4,
        "mean_altitude_km": [550.0, 800.0, 2100.0, 300.0],
        "inclination_deg": [53.0, 98.0, 55.0, 51.0],
        "object_type": ["PAY", "DEB", "PAY", "R/B"],
        "launch_date": pd.to_datetime(["2019-05-24", "1999-01-01",
                                       "2021-03-01", "1985-07-04"]),
    })
    assert isinstance(figures.fig_altitude_inclination(objs), go.Figure)
    assert isinstance(figures.fig_launch_cadence(objs), go.Figure)


def test_frontier_operator_share_stale_foster_hist():
    objs = pd.DataFrame({
        "is_on_orbit": [True] * 3,
        "nation": ["US", "CIS", "PRC"],
        "object_type": ["PAY", "DEB", "DEB"],
        "object_id": [1, 2, 3],
    })
    assert isinstance(figures.fig_responsibility_frontier(objs), go.Figure)

    attributed = pd.DataFrame(
        {"on_orbit_objects": [100, 50]}, index=pd.Index(["SpaceX", "OneWeb"], name="op"))
    assert isinstance(figures.fig_operator_share(attributed), go.Figure)

    gp = pd.DataFrame({"is_valid": [True, True, False], "is_stale": [False, True, False]})
    assert isinstance(figures.fig_stale_split(gp), go.Figure)

    topn = pd.DataFrame({
        "max_probability": [0.19, 0.15], "foster_pc": [0.57, 0.16],
        "pc_ratio_ours_vs_socrates": [2.97, 1.05],
        "primary_name": ["A", "B"], "secondary_name": ["C", "D"],
    })
    assert isinstance(figures.fig_foster_benchmark(topn), go.Figure)
    assert isinstance(figures.fig_foster_ratio_hist(topn), go.Figure)


def test_density_pack_figures(dens):
    objs = pd.DataFrame({
        "is_on_orbit": [True] * 5,
        "object_type": ["PAY", "R/B", "DEB", "PAY", "DEB"],
        "nation": ["US", "CIS", "CIS", "PRC", "FR"],
        "mean_altitude_km": [550.0, 850.0, 1400.0, 300.0, 1900.0],
        "inclination_deg": [53.0, 98.0, 74.0, 51.0, 100.0],
        "object_id": [1, 2, 3, 4, 5],
        "operator_id": [1, 0, 0, 2, 0],
    })
    conj = pd.DataFrame({
        "min_range_km": [0.016, 0.5, 3.0, 12.0, 1.1],
        "max_probability": [1e-2, 1e-4, 1e-6, 1e-8, 5e-5],
        "primary_nation": ["US", "US", "CIS", "PRC", "US"],
        "secondary_nation": ["CIS", "PRC", "PRC", "US", "CIS"],
    })
    growth = pd.DataFrame({
        "date": pd.to_datetime([f"2026-08-{d:02d}" for d in range(1, 29)]),
        "cumulative_catalog_size": range(70_000, 70_028),
        "new_objects_added": [1] * 28,
        "new_decayed": [0] * 28,
    })
    gp = pd.DataFrame({
        "is_valid": [True, True], "subpoint_lat_deg": [10.0, -20.0],
        "subpoint_lon_deg": [20.0, 40.0],
        "object_name": ["A", "B"],
    })

    assert isinstance(figures.fig_type_donut(objs), go.Figure)
    assert isinstance(figures.fig_hist(conj["max_probability"], "t", "x"), go.Figure)
    assert isinstance(figures.fig_nation_pair_bar(conj), go.Figure)
    assert isinstance(figures.fig_band_composition(dens), go.Figure)
    assert isinstance(figures.fig_clutter_line(dens), go.Figure)
    assert isinstance(figures.fig_alt_cdf(objs), go.Figure)
    assert isinstance(figures.fig_month_heatmap(growth), go.Figure)
    assert isinstance(figures.fig_crossing_projection(growth), go.Figure)
    assert isinstance(figures.fig_era_timeline(), go.Figure)
    assert isinstance(figures.fig_ground_track(gp), go.Figure)
