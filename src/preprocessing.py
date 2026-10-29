"""
Shared preprocessing pipeline for the Beijing PM2.5 forecasting project.

The SAME functions are used in three places so that training and serving
never drift apart:
  * Task 1  - scripts/02_train_models.py (training)
  * Task 3  - the API returns records using the column names defined here
  * Task 4  - scripts/predict.py (inference on records fetched from the API)

Pipeline (in order):
  1. load_raw()            read CSV, build a datetime index, rename columns
  2. impute_missing()      fill short PM2.5 gaps by time interpolation
  3. build_features()      lag features, moving averages, calendar features,
                           one-hot wind direction, and the target HORIZON hours ahead
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Constants shared by training and prediction
TARGET_COL = "pm25"                       # what we forecast (ug/m3)
HORIZON = 6                               # forecast 6 hours ahead
MAX_INTERP_GAP = 6                        # hours; longer gaps are NOT filled
PM_LAGS = [1, 2, 3, 6, 12, 24]            # lag features of PM2.5 (hours)
PM_MA_WINDOWS = [3, 6, 12, 24, 72]        # moving-average windows (hours)
MAX_LOOKBACK = max(max(PM_LAGS), max(PM_MA_WINDOWS))  # rows needed before t
WIND_CATEGORIES = ["NE", "NW", "SE", "cv"]  # fixed so columns never change

# Column names after renaming (these are also the DB / API field names)
RENAME_MAP = {
    "pm2.5": "pm25", "DEWP": "dewp", "TEMP": "temp", "PRES": "pres",
    "cbwd": "wind_dir", "Iws": "wind_speed", "Is": "snow_hours",
    "Ir": "rain_hours",
}
RAW_COLUMNS = ["pm25", "dewp", "temp", "pres", "wind_dir",
               "wind_speed", "snow_hours", "rain_hours"]


# 1. Loading

def load_raw(path: str) -> pd.DataFrame:
    """Read the Kaggle/UCI CSV and return a DataFrame indexed by datetime."""
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df[["year", "month", "day", "hour"]])
    df = df.rename(columns=RENAME_MAP)
    df = df.set_index("datetime").sort_index()
    return df[RAW_COLUMNS]


# 2. Missing values

def impute_missing(df: pd.DataFrame, max_gap: int = MAX_INTERP_GAP,
                   fill_remaining: bool = False) -> pd.DataFrame:
    """
    Fill missing PM2.5 values.

    * Gaps of <= `max_gap` hours are filled by linear interpolation in time.
      PM2.5 changes smoothly hour to hour, so a straight line between the two
      neighbouring readings is a reasonable estimate for a short gap.
    * Longer gaps are left as NaN: inventing days of values would add
      artificial smoothness. In training, rows that depend on them are
      dropped instead.
    * `fill_remaining=True` (used only at prediction time) forward/back-fills
      whatever is left so a single live forecast can still be produced.
    """
    out = df.copy()
    out = out.asfreq("h")  # guarantees a regular hourly index
    s = out["pm25"]
    missing = s.isna()
    # length of the consecutive-missing stretch each missing hour belongs to
    stretch_id = (missing != missing.shift()).cumsum()
    stretch_len = missing.groupby(stretch_id).transform("size")
    interpolated = s.interpolate(method="time", limit_area="inside")
    # fill ONLY stretches that are entirely short (<= max_gap); never fill
    # part of a long outage, which would invent values inside it
    fill_here = missing & (stretch_len <= max_gap)
    out["pm25"] = s.where(~fill_here, interpolated)
    if fill_remaining:
        out["pm25"] = out["pm25"].ffill().bfill()
    return out


# 3. Feature engineering

def build_features(df: pd.DataFrame, with_target: bool = True,
                   dropna: bool = True,
                   target_values: Optional[pd.Series] = None):
    """
    Create model inputs from an hourly DataFrame with causally prepared features.

    The caller is responsible for ensuring that any imputed feature values
    use only information available at their timestamp. When supplied,
    `target_values` provides the un-imputed observations used for labels.
    The target is PM2.5 at t+HORIZON.

    Returns (X, y) when with_target else X.
    """
    d = df.copy()
    feats = pd.DataFrame(index=d.index)

    # current conditions 
    for c in ["pm25", "dewp", "temp", "pres", "wind_speed",
              "snow_hours", "rain_hours"]:
        feats[c] = d[c]

    # lagged PM2.5 
    for k in PM_LAGS:
        feats[f"pm25_lag{k}"] = d["pm25"].shift(k)

    # moving averages / rolling statistics of PM2.5 
    for w in PM_MA_WINDOWS:
        feats[f"pm25_ma{w}"] = d["pm25"].rolling(w, min_periods=w).mean()
    feats["pm25_std24"] = d["pm25"].rolling(24, min_periods=24).std()
    feats["pm25_diff1"] = d["pm25"].diff(1)           # last hour's change

    # rolling weather context 
    feats["wind_speed_ma6"] = d["wind_speed"].rolling(6, min_periods=6).mean()
    feats["rain_hours_sum24"] = d["rain_hours"].rolling(24, min_periods=24).sum()
    feats["temp_lag24"] = d["temp"].shift(24)

    # calendar (cyclical encoding so 23h is close to 0h) 
    hour = d.index.hour
    month = d.index.month
    feats["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    feats["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    feats["month_sin"] = np.sin(2 * np.pi * (month - 1) / 12)
    feats["month_cos"] = np.cos(2 * np.pi * (month - 1) / 12)
    feats["is_weekend"] = (d.index.dayofweek >= 5).astype(int)

    # wind direction one-hot (fixed categories) 
    for cat in WIND_CATEGORIES:
        feats[f"wind_{cat}"] = (d["wind_dir"] == cat).astype(int)

    if not with_target:
        return feats.dropna() if dropna else feats

    target_source = (d["pm25"] if target_values is None
                     else target_values.reindex(d.index))
    y = target_source.shift(-HORIZON).rename("target_pm25_next_hour")
    full = feats.join(y)
    if dropna:
        full = full.dropna()
    return full.drop(columns="target_pm25_next_hour"), full["target_pm25_next_hour"]


def chronological_split(X: pd.DataFrame, y: pd.Series):
    """
    Time-ordered split (never shuffled):
        train: 2010-2012   validation: 2013   test: 2014

    Exclude the last `HORIZON` hours before each boundary so no target
    crosses from an earlier split into the following split.
    """
    validation_start = pd.Timestamp("2013-01-01")
    test_start = pd.Timestamp("2014-01-01")
    horizon = pd.Timedelta(hours=HORIZON)
    tr = X.index < validation_start - horizon
    va = ((X.index >= validation_start) &
          (X.index < test_start - horizon))
    te = X.index >= "2014-01-01"
    return (X[tr], y[tr]), (X[va], y[va]), (X[te], y[te])
