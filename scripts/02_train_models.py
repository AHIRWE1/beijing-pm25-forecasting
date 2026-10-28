"""
Task 1 (C): Train, tune and compare models that forecast PM2.5 six hours ahead.

Run from the project root:
    python scripts/02_train_models.py

Protocol
  * Chronological split: train 2010-2012, validation 2013, test 2014.
  * Hyperparameters are tuned ONLY on the training years, using
    TimeSeriesSplit cross-validation with a horizon-sized embargo so a
    training target cannot cross into the following validation block.
  * Experiments are ranked by validation RMSE. The winner is refit on
    train + validation and scored once on the untouched 2014 test set.

Outputs
    models/pm25_model.joblib           final fitted pipeline
    models/model_metadata.json         feature list, horizon, metrics
    outputs/tables/experiment_table.csv / .md
    outputs/tables/tuning_results_<name>.csv
    outputs/figures/M*.png
"""
import json
import os
import sys
import time

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.preprocessing import (HORIZON, MAX_INTERP_GAP, build_features,  # noqa: E402
                               chronological_split, load_raw)

RAW = "data/raw/PRSA_data_2010.1.1-2014.12.31.csv"
SEED = 42
os.makedirs("models", exist_ok=True)
os.makedirs("outputs/tables", exist_ok=True)
os.makedirs("outputs/figures", exist_ok=True)

BLUE, ORANGE, GREY, INK = "#2a6fb0", "#d9822b", "#9aa3ad", "#1f2937"
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e5e7eb", "figure.dpi": 130,
                     "axes.titleweight": "bold", "axes.titlesize": 11, "font.size": 9})


def metrics(y_true, y_pred):
    return {"MAE": mean_absolute_error(y_true, y_pred),
            "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "R2": r2_score(y_true, y_pred)}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
observations = load_raw(RAW).asfreq("h")
feature_data = observations.copy()
feature_data["pm25"] = observations["pm25"].ffill(limit=MAX_INTERP_GAP)
X, y = build_features(feature_data, target_values=observations["pm25"])
(Xtr, ytr), (Xva, yva), (Xte, yte) = chronological_split(X, y)
print(f"rows  train={len(Xtr)}  validation={len(Xva)}  test={len(Xte)}")
print(f"features: {X.shape[1]}")
print("PM2.5 feature gaps: causal forward fill, at most "
      f"{MAX_INTERP_GAP} hours; target labels use observed PM2.5 only")

ALL = list(X.columns)
CURRENT_ONLY = ["pm25", "dewp", "temp", "pres", "wind_speed", "snow_hours",
                "rain_hours", "hour_sin", "hour_cos", "month_sin", "month_cos",
                "is_weekend"] + [c for c in ALL if c.startswith("wind_") and
                                 c not in ("wind_speed", "wind_speed_ma6")]
CALENDAR = ["hour_sin", "hour_cos", "month_sin", "month_cos", "is_weekend"]
PM_HISTORY_ONLY = [c for c in ALL if c.startswith("pm25")] + CALENDAR  # no weather
cv = TimeSeriesSplit(n_splits=4, gap=HORIZON)

# ---------------------------------------------------------------------------
# Experiment definitions
# ---------------------------------------------------------------------------
EXPERIMENTS = [
    dict(name="Exp1_Ridge_all_features",
         description="Ridge regression, lag + moving-average features",
         features=ALL,
         estimator=Pipeline([("scale", StandardScaler()), ("m", Ridge())]),
         search=GridSearchCV,
         params={"m__alpha": [0.01, 0.1, 1, 10, 100, 1000]},
         search_kwargs={}),
    dict(name="Exp2_RandomForest_no_lags",
         description="Random Forest WITHOUT lag/moving-average features "
                     "(current weather + calendar only, plus current PM2.5)",
         features=CURRENT_ONLY,
         estimator=RandomForestRegressor(random_state=SEED, n_jobs=-1),
         search=RandomizedSearchCV,
         params={"n_estimators": [100, 200],
                 "max_depth": [8, 12, 20],
                 "min_samples_leaf": [5, 20, 50],
                 "max_features": [0.33, 0.6]},
         search_kwargs={"n_iter": 8, "random_state": SEED}),
    dict(name="Exp3_RandomForest_all_features",
         description="Random Forest, lag + moving-average features",
         features=ALL,
         estimator=RandomForestRegressor(random_state=SEED, n_jobs=-1),
         search=RandomizedSearchCV,
         params={"n_estimators": [100, 200, 300],
                 "max_depth": [8, 12, 20],
                 "min_samples_leaf": [5, 20, 50],
                 "max_features": [0.33, 0.6]},
         search_kwargs={"n_iter": 10, "random_state": SEED}),
    dict(name="Exp4_HistGradientBoosting_all_features",
         description="Histogram gradient boosting, lag + moving-average features",
         features=ALL,
         estimator=HistGradientBoostingRegressor(random_state=SEED,
                                                 early_stopping=False),
         search=RandomizedSearchCV,
         params={"learning_rate": [0.02, 0.05, 0.1],
                 "max_iter": [200, 400, 600],
                 "max_depth": [3, 6, None],
                 "min_samples_leaf": [20, 50, 100],
                 "l2_regularization": [0.0, 1.0, 10.0]},
         search_kwargs={"n_iter": 12, "random_state": SEED}),
    dict(name="Exp5_HistGradientBoosting_pm25_history_only",
         description="Histogram gradient boosting using ONLY PM2.5 history "
                     "(lags, moving averages) + calendar; no weather variables",
         features=PM_HISTORY_ONLY,
         estimator=HistGradientBoostingRegressor(random_state=SEED,
                                                 early_stopping=False),
         search=RandomizedSearchCV,
         params={"learning_rate": [0.02, 0.05, 0.1],
                 "max_iter": [200, 400, 600],
                 "max_depth": [3, 6, None],
                 "min_samples_leaf": [20, 50, 100],
                 "l2_regularization": [0.0, 1.0, 10.0]},
         search_kwargs={"n_iter": 12, "random_state": SEED}),
]

rows = []

# --- baseline: persistence ("future = now") ------------------------
base_val = metrics(yva, Xva["pm25"])
base_test = metrics(yte, Xte["pm25"])
rows.append({"experiment": "Exp0_Persistence_baseline",
             "model": f"PM2.5 in {HORIZON} h = PM2.5 now", "n_features": 1,
             "best_hyperparameters": "none", "cv_RMSE": np.nan,
             "val_MAE": base_val["MAE"], "val_RMSE": base_val["RMSE"], "val_R2": base_val["R2"],
             "test_MAE": base_test["MAE"], "test_RMSE": base_test["RMSE"],
             "test_R2": base_test["R2"], "fit_seconds": 0.0})

fitted = {}
for exp in EXPERIMENTS:
    t0 = time.time()
    search = exp["search"](exp["estimator"], exp["params"], cv=cv,
                           scoring="neg_root_mean_squared_error", n_jobs=-1,
                           refit=True, **exp["search_kwargs"])
    search.fit(Xtr[exp["features"]], ytr)
    secs = time.time() - t0
    best = search.best_estimator_
    pv, pt = best.predict(Xva[exp["features"]]), best.predict(Xte[exp["features"]])
    mv, mt = metrics(yva, pv), metrics(yte, pt)
    pd.DataFrame(search.cv_results_).sort_values("rank_test_score")[
        ["rank_test_score", "mean_test_score", "std_test_score", "params"]
    ].to_csv(f"outputs/tables/tuning_results_{exp['name']}.csv", index=False)
    rows.append({"experiment": exp["name"], "model": exp["description"],
                 "n_features": len(exp["features"]),
                 "best_hyperparameters": json.dumps(search.best_params_),
                 "cv_RMSE": -search.best_score_,
                 "val_MAE": mv["MAE"], "val_RMSE": mv["RMSE"], "val_R2": mv["R2"],
                 "test_MAE": mt["MAE"], "test_RMSE": mt["RMSE"], "test_R2": mt["R2"],
                 "fit_seconds": secs})
    fitted[exp["name"]] = (exp, search)
    print(f"{exp['name']:42s} cv={-search.best_score_:6.2f} "
          f"val_RMSE={mv['RMSE']:6.2f} test_RMSE={mt['RMSE']:6.2f}  ({secs:.0f}s)")

table = pd.DataFrame(rows)
table = table.round({"cv_RMSE": 2, "val_MAE": 2, "val_RMSE": 2, "val_R2": 4,
                     "test_MAE": 2, "test_RMSE": 2, "test_R2": 4, "fit_seconds": 1})
table.to_csv("outputs/tables/experiment_table.csv", index=False)
markdown_table = table.drop(columns=["fit_seconds"])
markdown_rows = [
    "| " + " | ".join(markdown_table.columns) + " |",
    "| " + " | ".join("---" for _ in markdown_table.columns) + " |",
]
for row in markdown_table.itertuples(index=False, name=None):
    cells = ["" if pd.isna(value) else str(value).replace("|", r"\|")
             for value in row]
    markdown_rows.append("| " + " | ".join(cells) + " |")
with open("outputs/tables/experiment_table.md", "w", encoding="utf-8") as f:
    f.write("\n".join(markdown_rows) + "\n")
print(table.drop(columns=["best_hyperparameters", "model"]).to_string(index=False))

# ---------------------------------------------------------------------------
# Select winner on VALIDATION RMSE (test set is not used for selection)
# ---------------------------------------------------------------------------
cands = table[table.experiment.isin(fitted.keys())]
winner_name = cands.sort_values("val_RMSE").iloc[0]["experiment"]
exp, search = fitted[winner_name]
print("\nSelected on validation RMSE:", winner_name, search.best_params_)

# refit on train + validation with the chosen hyperparameters, then test once
final = exp["estimator"].set_params(**search.best_params_)
Xtv = pd.concat([Xtr, Xva])[exp["features"]]
ytv = pd.concat([ytr, yva])
final.fit(Xtv, ytv)
final_pred = final.predict(Xte[exp["features"]])
final_metrics = metrics(yte, final_pred)
print("Final model on 2014 test:", {k: round(v, 3) for k, v in final_metrics.items()})

joblib.dump(final, "models/pm25_model.joblib")
meta = {"model_name": winner_name, "horizon_hours": HORIZON,
        "feature_columns": exp["features"], "best_params": search.best_params_,
        "pm25_feature_imputation": f"causal forward fill, limit {MAX_INTERP_GAP} hours",
        "target_labels": "observed PM2.5 only; missing targets excluded",
        "test_metrics_after_refit": final_metrics,
        "persistence_baseline_test": base_test,
        "trained_on": "2010-01-01 to 2013-12-31 (train + validation)",
        "tested_on": "2014-01-01 to 2014-12-31"}
with open("models/model_metadata.json", "w") as f:
    json.dump(meta, f, indent=2)

# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
# M1: experiment comparison (test RMSE, lower is better)
fig, ax = plt.subplots(figsize=(8, 3.6))
labels = [r.replace("Exp", "E").replace("_all_features", "").replace("_baseline", "")
          for r in table.experiment]
bars = ax.barh(labels[::-1], table.test_RMSE[::-1], color=BLUE, height=0.55)
for b, v in zip(bars, table.test_RMSE[::-1]):
    ax.text(v + 0.2, b.get_y() + b.get_height() / 2, f"{v:.1f}", va="center")
ax.set_xlabel("test RMSE, 2014 (ug/m3) - lower is better")
ax.set_title("Experiment comparison")
fig.tight_layout()
fig.savefig("outputs/figures/M1_experiment_comparison.png", bbox_inches="tight")
plt.close(fig)

# M2: predicted vs actual (two weeks of the test year, plus scatter)
idx = Xte.index
res = pd.DataFrame({"actual": yte.values, "predicted": final_pred}, index=idx + pd.Timedelta(hours=HORIZON))
fig, ax = plt.subplots(1, 2, figsize=(12, 3.6), gridspec_kw={"width_ratios": [1.6, 1]})
z = res["2014-02-01":"2014-02-14"]
ax[0].plot(z.index, z.actual, color=GREY, label="actual")
ax[0].plot(z.index, z.predicted, color=BLUE, label=f"predicted ({HORIZON} h ahead)")
ax[0].xaxis.set_major_locator(mdates.DayLocator(interval=3))
ax[0].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax[0].set_ylabel("PM2.5 (ug/m3)")
ax[0].set_title(f"{HORIZON}-hour-ahead forecast vs actual, 1-14 Feb 2014")
ax[0].legend(frameon=False)
ax[1].scatter(res.actual, res.predicted, s=3, alpha=0.25, color=BLUE)
m = max(res.actual.max(), res.predicted.max())
ax[1].plot([0, m], [0, m], color=ORANGE, lw=1)
ax[1].set_xlabel("actual")
ax[1].set_ylabel("predicted")
ax[1].set_title(f"Test set 2014  (R2 = {final_metrics['R2']:.3f})")
fig.tight_layout()
fig.savefig("outputs/figures/M2_predicted_vs_actual.png", bbox_inches="tight")
plt.close(fig)

# M3: feature importance (tree models) or |coefficient| (ridge)
model = final.named_steps["m"] if hasattr(final, "named_steps") else final
if hasattr(model, "feature_importances_"):
    imp = pd.Series(model.feature_importances_, index=exp["features"])
elif hasattr(model, "coef_"):
    imp = pd.Series(np.abs(model.coef_), index=exp["features"])
else:  # HistGradientBoosting has no built-in importances: use permutation
    from sklearn.inspection import permutation_importance
    pi = permutation_importance(final, Xte[exp["features"]], yte, n_repeats=5,
                                random_state=SEED, scoring="neg_root_mean_squared_error")
    imp = pd.Series(pi.importances_mean, index=exp["features"])
imp = imp.sort_values(ascending=False)
imp.to_csv("outputs/tables/feature_importance.csv", header=["importance"])
top = imp.head(12)[::-1]
fig, ax = plt.subplots(figsize=(7, 4))
ax.barh(top.index, top.values, color=BLUE, height=0.6)
ax.set_title(f"Top features - {winner_name}")
ax.set_xlabel("permutation importance: RMSE increase when shuffled (ug/m3)"
              if not hasattr(model, "feature_importances_") and not hasattr(model, "coef_")
              else "importance")
fig.tight_layout()
fig.savefig("outputs/figures/M3_feature_importance.png", bbox_inches="tight")
plt.close(fig)

# M4: error by horizon-hour-of-day and by pollution level (where does it fail?)
res["abs_err"] = (res.actual - res.predicted).abs()
res["level"] = pd.cut(res.actual, [-1, 35, 75, 150, 250, 1000],
                      labels=["0-35", "35-75", "75-150", "150-250", ">250"])
lvl = res.groupby("level", observed=True)["abs_err"].mean().round(1)
lvl.to_csv("outputs/tables/error_by_pollution_level.csv", header=["MAE"])
print("\nMAE by pollution level:\n", lvl.to_string())
