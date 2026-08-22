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
    })
    assert isinstance(figures.fig_foster_benchmark(topn), go.Figure)


def test_3d_snapshot():
    gp = pd.DataFrame({
        "norad_cat_id": [1, 2], "object_name": ["X", "Y"],
        "teme_x_km": [7000.0, None], "teme_y_km": [0.0, None], "teme_z_km": [0.0, None],
        "is_valid": [True, True], "regime": ["VLEO", "MEO"],
    })
    assert isinstance(figures.fig_3d_snapshot(gp), go.Figure)
