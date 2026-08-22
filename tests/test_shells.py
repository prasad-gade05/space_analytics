import pytest

from src.transformation.shells import (
    altitude_band,
    perigee_apogee_km,
    regime_shell,
    semi_major_axis_km,
)


def test_iss_semi_major_axis():
    # ISS mean motion ~15.50 rev/day -> a ~ 6,782 km -> mean alt ~ 404 km
    a = semi_major_axis_km(15.50)
    assert 6_770 < a < 6_795


def test_perigee_apogee_starlink_like():
    # Starlink: mm ~ 15.06 rev/day, e ~ 0.0001 -> ~550 km circular
    p, a = perigee_apogee_km(15.06, 0.0001)
    assert 500 < p < 600
    assert 500 < a < 600


def test_geo_belt_classified_as_geo():
    # GEO: 1.0027 rev/day -> mean altitude ~35,786 km
    p, a = perigee_apogee_km(1.0027, 0.0002)
    mean = (p + a) / 2
    assert regime_shell(mean) == "GEO"
    assert altitude_band(mean) == -1  # above the fine-band grid


def test_regime_boundaries():
    assert regime_shell(200) == "VLEO"
    assert regime_shell(550) == "LEO-Constellation"
    assert regime_shell(800) == "LEO-SSO"
    assert regime_shell(1200) == "Legacy-Debris"
    assert regime_shell(1800) == "Upper-LEO"
    assert regime_shell(20_000) == "MEO"
    assert regime_shell(50_000) == "HEO/Deep-Space"


def test_fine_bands():
    assert altitude_band(-50) == 0      # clamp sub-surface to band 0
    assert altitude_band(549.9) == 525
    assert altitude_band(550.0) == 550
    with pytest.raises(ValueError):
        semi_major_axis_km(0)
