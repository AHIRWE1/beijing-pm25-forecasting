
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import joblib
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.preprocessing import (HORIZON, MAX_INTERP_GAP, MAX_LOOKBACK,  # noqa: E402
                               RAW_COLUMNS, build_features)

DEFAULT_API_URL = "http://127.0.0.1:8000"
MODEL_PATH = "models/pm25_model.joblib"
METADATA_PATH = "models/model_metadata.json"
PAGE_SIZE = 1000  # the API's maximum page size
# Extra hours before the lookback window so a gap at its start can be filled
HISTORY_BUFFER = 24
WEATHER_COLUMNS = ["dewp", "temp", "pres", "wind_dir", "wind_speed",
                   "snow_hours", "rain_hours"]


# 1. Fetch records from the API

class APIError(RuntimeError):
    pass


def get_json(base_url: str, path: str, params: dict = None):
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise APIError(f"GET {url} returned {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise APIError(f"Could not reach the API at {base_url} ({e.reason}). "
                       "Is the server running? (uvicorn api.main:app)") from e


def fetch_latest(base_url: str, db: str) -> dict:
    return get_json(base_url, f"/{db}/readings/latest")


def fetch_range(base_url: str, db: str, start: datetime, end: datetime) -> list:
    """Return every reading in [start, end], following the API's pagination."""
    items, offset = [], 0
    while True:
        page = get_json(base_url, f"/{db}/readings/range", {
            "start": start.isoformat(), "end": end.isoformat(),
            "limit": PAGE_SIZE, "offset": offset})
        items.extend(page["items"])
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            return items


# 2. Preprocess

def records_to_frame(records: list) -> pd.DataFrame:
    """Flatten API readings into the Task 1 column names, indexed by datetime."""
    rows = []
    for r in records:
        weather = r["weather"]
        precip = r.get("precipitation") or {}
        rows.append({
            "datetime": pd.Timestamp(r["timestamp"]),
            "pm25": r["pm25"],
            "dewp": weather["dew_point"],
            "temp": weather["temperature"],
            "pres": weather["pressure"],
            "wind_dir": weather["wind_dir"],
            "wind_speed": weather["wind_speed"],
            "snow_hours": precip.get("snow_hours", 0),
            "rain_hours": precip.get("rain_hours", 0),
        })
    df = pd.DataFrame(rows, columns=["datetime"] + RAW_COLUMNS)
    df["pm25"] = df["pm25"].astype(float)
    # the SQL API allows one reading per hour, MongoDB does not: keep the last
    df = df.drop_duplicates("datetime", keep="last")
    return df.set_index("datetime").sort_index()


def prepare_features(df: pd.DataFrame, start: datetime, origin: datetime):
    """
    Apply the training pipeline and return the feature row for `origin`,
    plus a short report of the gaps that were filled.
    """
    hourly = df.reindex(pd.date_range(start, origin, freq="h"))
    report = {"hours_expected": len(hourly),
              "hours_missing": int(hourly["dewp"].isna().sum()),
              "pm25_missing": int(hourly["pm25"].isna().sum())}

    # Same rule as scripts/02_train_models.py: carry the last observed PM2.5
    # forward for at most MAX_INTERP_GAP hours. This only uses the past, so
    # the forecast never sees values after its origin.
    hourly["pm25"] = hourly["pm25"].ffill(limit=MAX_INTERP_GAP)
    # Weather was never missing in the raw data, but an hour can be absent
    # from the database. Treat it the same way as a PM2.5 gap.
    hourly[WEATHER_COLUMNS] = hourly[WEATHER_COLUMNS].ffill(limit=MAX_INTERP_GAP)
    report["pm25_still_missing"] = int(hourly["pm25"].isna().sum())

    X = build_features(hourly, with_target=False, dropna=False)
    return X.loc[[pd.Timestamp(origin)]], hourly, report


# 3. Load the trained model

def load_model(model_path: str, metadata_path: str):
    for path in (model_path, metadata_path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found. Run "
                                    "scripts/02_train_models.py first.")
    with open(metadata_path) as f:
        meta = json.load(f)
    if meta["horizon_hours"] != HORIZON:
        raise ValueError(f"Model forecasts {meta['horizon_hours']} h ahead but "
                         f"src/preprocessing.py uses HORIZON={HORIZON}.")
    return joblib.load(model_path), meta


# 4. Forecast

def forecast(base_url: str, db: str, at: datetime = None,
             model_path: str = MODEL_PATH, metadata_path: str = METADATA_PATH) -> dict:
    model, meta = load_model(model_path, metadata_path)

    origin = at or datetime.fromisoformat(fetch_latest(base_url, db)["timestamp"])
    origin = origin.replace(minute=0, second=0, microsecond=0)
    start = origin - timedelta(hours=MAX_LOOKBACK + HISTORY_BUFFER - 1)
    records = fetch_range(base_url, db, start, origin)
    if not records:
        raise ValueError(f"The API returned no readings between {start} and {origin}.")

    df = records_to_frame(records)
    X, hourly, report = prepare_features(df, start, origin)
    X = X[meta["feature_columns"]]
    missing = X.columns[X.isna().iloc[0]].tolist()
    if missing:
        raise ValueError(
            f"Cannot build features for {origin}: {missing} are missing. The "
            f"{MAX_LOOKBACK} hours before the origin have a gap longer than "
            f"{MAX_INTERP_GAP} hours (missing hours: {report['hours_missing']}, "
            f"missing PM2.5: {report['pm25_missing']}). Choose another time with --at.")

    target_time = origin + timedelta(hours=HORIZON)
    prediction = float(model.predict(X)[0])

    # For historical origins the actual value may already be stored
    actual = None
    later = fetch_range(base_url, db, target_time, target_time)
    if later and later[-1]["pm25"] is not None:
        actual = float(later[-1]["pm25"])

    return {
        "database": db,
        "model": meta["model_name"],
        "origin": origin.isoformat(),
        "target_time": target_time.isoformat(),
        "horizon_hours": HORIZON,
        "predicted_pm25": round(prediction, 1),
        "current_pm25": round(float(hourly["pm25"].iloc[-1]), 1),
        "pm25_ma24": round(float(X["pm25_ma24"].iloc[0]), 1),
        "actual_pm25": actual,
        "records_fetched": len(records),
        "data_quality": report,
    }


def print_summary(r: dict):
    q = r["data_quality"]
    print(f"Database:          {r['database']}")
    print(f"Model:             {r['model']}")
    print(f"Records fetched:   {r['records_fetched']} "
          f"({q['hours_missing']} of {q['hours_expected']} hours absent, "
          f"{q['pm25_missing']} PM2.5 gaps, {q['pm25_still_missing']} left unfilled)")
    print(f"Forecast origin:   {r['origin']}")
    print(f"  PM2.5 now:       {r['current_pm25']:.1f} ug/m3")
    print(f"  24 h average:    {r['pm25_ma24']:.1f} ug/m3")
    print(f"Forecast for:      {r['target_time']} (+{r['horizon_hours']} h)")
    print(f"  Predicted PM2.5: {r['predicted_pm25']:.1f} ug/m3")
    if r["actual_pm25"] is not None:
        err = r["predicted_pm25"] - r["actual_pm25"]
        print(f"  Actual PM2.5:    {r['actual_pm25']:.1f} ug/m3 (error {err:+.1f})")


def parse_args():
    p = argparse.ArgumentParser(
        description="Forecast PM2.5 6 hours ahead from readings served by the API.")
    p.add_argument("--api-url", default=os.getenv("API_URL", DEFAULT_API_URL),
                   help=f"base URL of the API (default {DEFAULT_API_URL})")
    p.add_argument("--db", choices=["mongo", "sql"], default="mongo",
                   help="which database's endpoints to read from (default mongo)")
    p.add_argument("--at", type=datetime.fromisoformat,
                   help="forecast origin, e.g. 2014-06-15T12:00:00 "
                        "(default: the latest reading)")
    p.add_argument("--model", default=MODEL_PATH)
    p.add_argument("--metadata", default=METADATA_PATH)
    p.add_argument("--json", action="store_true",
                   help="print the result as JSON instead of a summary")
    return p.parse_args()


def main():
    args = parse_args()
    try:
        result = forecast(args.api_url, args.db, args.at, args.model, args.metadata)
    except (APIError, ValueError, FileNotFoundError) as e:
        sys.exit(f"error: {e}")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_summary(result)


if __name__ == "__main__":
    main()
