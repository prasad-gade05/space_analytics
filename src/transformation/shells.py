"""Altitude-shell classification and orbital-element derived geometry.

Semi-major axis from mean motion: a = (mu / n^2)^(1/3), n in rad/s.
Perigee/apogee follow the same convention as CelesTrak SATCAT columns
(kilometres above an equatorial-radius Earth, R = 6378.137 km).
"""

from __future__ import annotations

import math

MU_KM3_S2 = 398_600.4418
EARTH_RADIUS_KM = 6_378.137

# Canonical regimes (kickstart spec Section 3, Silver step 5).
REGIME_SHELLS: tuple[tuple[str, float, float], ...] = (
    ("VLEO", 100.0, 350.0),
    ("LEO-Constellation", 350.0, 650.0),
    ("LEO-SSO", 650.0, 950.0),
    ("Legacy-Debris", 950.0, 1_500.0),
    ("Upper-LEO", 1_500.0, 2_000.0),
    ("MEO", 2_000.0, 35_586.0),
    ("GEO", 35_586.0, 36_100.0),
    ("HEO/Deep-Space", 36_100.0, float("inf")),
)

BAND_WIDTH_KM = 25.0
FINE_BAND_TOP_KM = 2_000.0


def semi_major_axis_km(mean_motion_rev_per_day: float) -> float:
    if mean_motion_rev_per_day <= 0:
        raise ValueError(f"Mean motion must be positive, got {mean_motion_rev_per_day}")
    n_rad_s = mean_motion_rev_per_day * 2.0 * math.pi / 86_164.0905  # sidereal day
    return (MU_KM3_S2 / (n_rad_s * n_rad_s)) ** (1.0 / 3.0)


def perigee_apogee_km(mean_motion_rev_per_day: float, eccentricity: float) -> tuple[float, float]:
    a = semi_major_axis_km(mean_motion_rev_per_day)
    return a * (1.0 - eccentricity) - EARTH_RADIUS_KM, a * (1.0 + eccentricity) - EARTH_RADIUS_KM


def altitude_band(mean_altitude_km: float) -> int:
    """25 km band label for the fine LEO density grid; -1 above the grid top."""
    if mean_altitude_km >= FINE_BAND_TOP_KM:
        return -1
    return int((max(mean_altitude_km, 0.0) // BAND_WIDTH_KM) * BAND_WIDTH_KM)


def regime_shell(mean_altitude_km: float) -> str:
    for name, low, high in REGIME_SHELLS:
        if low <= mean_altitude_km < high:
            return name
    return "Unknown"
