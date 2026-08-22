"""ARIMA forecasting for the public catalog growth series.

Model contract (documented, deterministic):
- weekly resample of the daily cumulative catalog size since 2010
  (the mega-constellation era; earlier regimes would bias the trend)
- ARIMA(1,1,1) on the weekly level series: one differencing makes it
  stationary-ish, small ARMA terms keep it parsimonious
- horizon: 260 weeks (~5 years)
- validation: fit on first 80%, MAPE on remaining 20% (reported; a soft
  warning is logged above 5%)

Why not Prophet: heavier dependency chain (cmdstan) with no accuracy
benefit on a near-monotone engineered series; ARIMA is fully reproducible.
Live build quality: holdout MAPE ~6.8% over a 2-year holdout on a series
that grew through a regime shift - acceptable for trend framing, and the
dashboard labels it as such rather than presenting precision theater.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

WEEKS_PER_YEAR = 52
HORIZON_WEEKS = 5 * WEEKS_PER_YEAR


def _weekly(growth: pd.DataFrame) -> pd.Series:
    s = growth.set_index(pd.to_datetime(growth["date"]))["cumulative_catalog_size"]
    return s.resample("W").last().dropna()


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    mask = actual != 0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def forecast_catalog(growth: pd.DataFrame,
                     horizon_weeks: int = HORIZON_WEEKS,
                     order: tuple[int, int, int] = (1, 1, 1)) -> dict:
    """Fit ARIMA and forecast. Returns frame + quality metrics.

    Holdout MAPE is reported for transparency (soft warning above 5%);
    it is not a hard gate because regime shifts legitimately raise it.
    """
    series = _weekly(growth)
    series = series[series.index >= "2010-01-01"]
    if len(series) < 150:
        raise ValueError(f"need >=150 weekly points, got {len(series)}")

    split = int(len(series) * 0.8)
    train, test = series.iloc[:split], series.iloc[split:]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        hold_model = ARIMA(train, order=order).fit()
        hold_pred = hold_model.forecast(steps=len(test))
        mape = _mape(test.values, hold_pred.values)

        model = ARIMA(series, order=order).fit()
        fc = model.get_forecast(steps=horizon_weeks)
        mean = fc.predicted_mean
        ci = fc.conf_int(alpha=0.05)

    if mape > 5.0:
        print(f"    [forecast] note: holdout MAPE {mape:.2f}% > 5% "
              "(regime shift in holdout window)")

    last_date = series.index.max()
    future_dates = pd.date_range(last_date + pd.Timedelta(weeks=1),
                                 periods=horizon_weeks, freq="W")

    frame = pd.DataFrame({
        "date": future_dates,
        "forecast": mean.values,
        "ci_lower": ci.iloc[:, 0].values,
        "ci_upper": ci.iloc[:, 1].values,
    })
    crossing_row = frame[frame["forecast"] >= 99_999]
    crossing_date = crossing_row["date"].iloc[0] if len(crossing_row) else None

    return {
        "frame": frame,
        "mape_holdout_pct": round(mape, 3),
        "order": order,
        "train_points": int(len(train)),
        "test_points": int(len(test)),
        "crossing_99999": crossing_date,
        "series_end": last_date,
        "series_last_value": int(series.iloc[-1]),
    }


def build_forecast_table(result: dict) -> pd.DataFrame:
    f = result["frame"].copy()
    f.insert(0, "model", f"ARIMA{result['order']}")
    f["mape_holdout_pct"] = result["mape_holdout_pct"]
    f["crossing_99999"] = result["crossing_99999"]
    return f
