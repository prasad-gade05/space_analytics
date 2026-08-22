"""Pure-function analytics metrics: HHI, Gini, Foster/Chan collision probability.

References (verified in repo verification_report.md):
- HHI: sum of squared market shares, 0..10_000 on the percentage scale or 0..1 fractional.
- Gini: standard rank-based inequality coefficient.
- Foster/Chan Pc: 2D integral of a bivariate Gaussian (zero mean, combined
  covariance sigma^2 * I under the documented spherical assumption) over a
  disk of hard-body radius R centred at the miss vector, evaluated on the
  encounter plane. Chan's closed-form series for the zero-miss special case
  is used as the unit-test oracle.
"""

from __future__ import annotations

import math

import numpy as np


def hhi(shares: np.ndarray | list[float]) -> float:
    """Herfindahl-Hirschman Index on fractional shares (0..1)."""
    s = np.asarray(shares, dtype=float)
    if s.size == 0:
        return 0.0
    total = s.sum()
    if total <= 0:
        return 0.0
    p = s / total
    return float((p ** 2).sum())


def gini(values: np.ndarray | list[float]) -> float:
    """Gini coefficient; 0 = perfectly equal, ~1 = maximally concentrated."""
    x = np.sort(np.asarray(values, dtype=float))
    n = x.size
    if n == 0 or x.sum() <= 0:
        return 0.0
    cumulative = np.cumsum(x)
    return float((n + 1 - 2 * (cumulative / cumulative[-1]).sum()) / n)


def chan_pc_zero_miss(sigma_km: float, radius_km: float) -> float:
    """Analytic Pc for zero miss distance under spherical covariance:
    integrating N(0, sigma^2 I) over a disk of radius R centred on the
    density peak gives Pc = 1 - exp(-R^2 / (2 sigma^2)).
    This is the d->0 limit of Chan's formulation and serves as the
    unit-test oracle for foster_pc_numeric."""
    if sigma_km <= 0:
        raise ValueError("sigma must be positive")
    return float(1.0 - math.exp(-radius_km**2 / (2.0 * sigma_km**2)))


def foster_pc_numeric(
    miss_distance_km: float,
    combined_sigma_km: float,
    hard_body_radius_km: float,
    grid_half_width_sigmas: float = 8.0,
    grid_points: int = 1601,
) -> float:
    """Numerical Foster-style 2D Pc.

    Integrates the 2D Gaussian pdf (isotropic, std=combined_sigma_km) over a
    circle of radius hard_body_radius_km centred `miss_distance_km` from the
    density peak, on the encounter plane. Assumes short-encounter linear
    relative motion and uncorrelated spherical covariance per CARA/Foster.
    """
    if combined_sigma_km <= 0:
        raise ValueError("combined_sigma must be positive")
    if hard_body_radius_km <= 0:
        return 0.0

    half = grid_half_width_sigmas * combined_sigma_km
    axis = np.linspace(-half, half, grid_points)
    step = axis[1] - axis[0]
    inv2s2 = 1.0 / (2.0 * combined_sigma_km**2)

    # Gaussian peak fixed at origin; encounter disk centred at (+miss, 0).
    # Shifted coordinates u = x - d put the disk at the origin.
    U, V = np.meshgrid(axis - miss_distance_km, axis)
    inside = (U * U + V * V) <= hard_body_radius_km**2
    pdf = np.exp(-(((U + miss_distance_km) ** 2 + V**2) * inv2s2)) / (
        2.0 * math.pi * combined_sigma_km**2
    )
    pc = float(pdf[inside].sum() * step * step)
    return min(max(pc, 0.0), 1.0)
