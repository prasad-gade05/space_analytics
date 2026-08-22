import numpy as np
import pandas as pd
import pytest

from src.analytics.metrics import chan_pc_zero_miss, foster_pc_numeric, gini, hhi
from src.modeling.operators import attribute_operator, owner_to_nation


def test_hhi_known_cases():
    assert hhi([]) == 0.0
    assert hhi([5.0]) == pytest.approx(1.0)                 # monopoly
    assert hhi([1, 1]) == pytest.approx(0.5)                # perfect duopoly
    assert hhi([10, 10, 10, 10]) == pytest.approx(0.25)
    assert hhi([90, 5, 5]) == pytest.approx((0.9**2 + 2 * 0.05**2))


def test_gini_known_cases():
    assert gini([]) == 0.0
    assert gini([3, 3, 3, 3]) == 0.0
    assert gini([0, 0, 0, 9]) == pytest.approx(0.75)        # one holder owns all
    x = [1, 2, 3, 4]
    expected = (4 + 1 - 2 * ((1 / 10) + (3 / 10) + (6 / 10) + (10 / 10))) / 4
    assert gini(x) == pytest.approx(expected)


def test_foster_matches_chan_zero_miss():
    # zero miss distance: numeric integral must match the analytic limit
    # Pc = 1 - exp(-R^2 / (2 sigma^2)); 1% tolerance covers grid discretization
    for sigma, radius in [(1.0, 0.15), (2.0, 0.30), (0.5, 0.10)]:
        analytic = chan_pc_zero_miss(sigma, radius)
        numeric = foster_pc_numeric(miss_distance_km=0.0, combined_sigma_km=sigma,
                                    hard_body_radius_km=radius,
                                    grid_half_width_sigmas=8.0, grid_points=1601)
        assert numeric == pytest.approx(analytic, rel=1e-2), (sigma, radius)


def test_foster_monotonic_and_bounded():
    pc_small = foster_pc_numeric(0.05, 1.0, 0.15)
    pc_large = foster_pc_numeric(5.0, 1.0, 0.15)
    assert 0.0 <= pc_small <= 1.0
    assert 0.0 <= pc_large < pc_small
    assert foster_pc_numeric(100.0, 1.0, 0.15) == pytest.approx(0.0, abs=1e-12)


def test_operator_attribution():
    names = pd.Series(["STARLINK-1234", "KUIPER-00008", "GUOWANG 24 OBJECT A",
                       "QIANFAN-99", "ONEWEB-0012", "ISS (ZARYA)", None])
    ids = attribute_operator(names)
    assert list(ids) == [1, 3, 5, 4, 2, 0, 0]


def test_owner_nation_mapping():
    s = pd.Series(["US", "CIS", "PRC", "XYZ"])
    out = owner_to_nation(s)
    assert list(out)[:3] == ["United States", "Russia/CIS", "China"]
    assert out.iloc[3] == "XYZ"  # unknown codes pass through
