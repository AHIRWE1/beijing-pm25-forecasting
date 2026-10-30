"""
Task 4 check: the forecast made from API records must equal the forecast the
training pipeline makes from the raw CSV for the same origin.

Run from the project root while the API is running, with the full dataset
loaded into the databases:
    python scripts/check_predict.py                 # 10 origins, both databases
    python scripts/check_predict.py --n 20 --db sql

Origins are sampled from hours where the training pipeline can build every
feature. Some are taken right after a PM2.5 gap, so gap filling is checked too.
"""
import argparse
import json
import os
import random
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.preprocessing import MAX_INTERP_GAP, build_features, load_raw  # noqa: E402
from scripts.predict import (DEFAULT_API_URL, METADATA_PATH, MODEL_PATH,  # noqa: E402
                             APIError, forecast, load_model)

RAW = "data/raw/PRSA_data_2010.1.1-2014.12.31.csv"


def reference_features(csv_path: str, feature_columns: list) -> tuple:
    """Build features from the CSV exactly as scripts/02_train_models.py does."""
    observations = load_raw(csv_path).asfreq("h")
    feature_data = observations.copy()
    feature_data["pm25"] = observations["pm25"].ffill(limit=MAX_INTERP_GAP)
    X = build_features(feature_data, with_target=False, dropna=False)
    return X[feature_columns].dropna(), observations["pm25"].isna()


def sample_origins(X: pd.DataFrame, pm25_missing: pd.Series, n: int, seed: int) -> list:
    """Half random origins, half the first observed hour after a PM2.5 gap."""
    after_gap = [t for t in X.index
                 if t - pd.Timedelta(hours=1) in pm25_missing.index
                 and pm25_missing[t - pd.Timedelta(hours=1)]]
    rng = random.Random(seed)
    n_gap = min(n // 2, len(after_gap))
    return sorted(rng.sample(list(X.index), n - n_gap) + rng.sample(after_gap, n_gap))


def main():
    p = argparse.ArgumentParser(
        description="Check API forecasts against the training pipeline.")
    p.add_argument("--api-url", default=os.getenv("API_URL", DEFAULT_API_URL))
    p.add_argument("--db", choices=["mongo", "sql", "both"], default="both")
    p.add_argument("--csv", default=RAW)
    p.add_argument("--n", type=int, default=10, help="number of origins (default 10)")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    if not os.path.exists(args.csv):
        sys.exit(f"error: CSV not found: {args.csv}")
    model, meta = load_model(MODEL_PATH, METADATA_PATH)
    X, pm25_missing = reference_features(args.csv, meta["feature_columns"])
    dbs = ["mongo", "sql"] if args.db == "both" else [args.db]

    failures = 0
    for origin in sample_origins(X, pm25_missing, args.n, args.seed):
        expected = round(float(model.predict(X.loc[[origin]])[0]), 1)
        for db in dbs:
            try:
                got = forecast(args.api_url, db, origin.to_pydatetime())["predicted_pm25"]
            except (APIError, ValueError) as e:
                got = f"error: {e}"
            ok = got == expected
            failures += not ok
            print(f"{origin}  {db:5}  pipeline {expected:6.1f}  api {got}  "
                  f"{'OK' if ok else 'MISMATCH'}")

    total = args.n * len(dbs)
    print(json.dumps({"checked": total, "matched": total - failures}))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
