"""
Task 1 (A + B): Exploratory data analysis and analytical questions.

Run from the project root:
    python scripts/01_eda.py

Outputs
    outputs/figures/*.png      one or more figures per question
    outputs/tables/*.csv       summary tables
    outputs/tables/eda_findings.json   the numbers quoted in the report
    data/processed/pm25_clean.csv      imputed hourly series used by later tasks
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.preprocessing import HORIZON, load_raw, impute_missing, MAX_INTERP_GAP  # noqa: E402

RAW = "data/raw/PRSA_data_2010.1.1-2014.12.31.csv"
FIG = "outputs/figures"
TAB = "outputs/tables"
os.makedirs(FIG, exist_ok=True)
os.makedirs(TAB, exist_ok=True)
os.makedirs("data/processed", exist_ok=True)

# ---- restrained plotting style: thin marks, recessive grid, one accent ----
BLUE, ORANGE, GREY, INK = "#2a6fb0", "#d9822b", "#9aa3ad", "#1f2937"
plt.rcParams.update({
    "figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": GREY, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK, "ytick.color": INK, "axes.grid": True,
    "grid.color": "#e5e7eb", "grid.linewidth": 0.6, "axes.titleweight": "bold",
    "axes.titlesize": 11, "font.size": 9, "lines.linewidth": 1.4,
})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{FIG}/{name}.png", bbox_inches="tight")
    plt.close(fig)


F = {}  # findings dictionary, dumped to JSON at the end

# ===========================================================================
# PART A - understanding the dataset
# ===========================================================================
raw = load_raw(RAW)
F["rows"] = int(len(raw))
F["columns"] = list(raw.columns)
F["start"], F["end"] = str(raw.index.min()), str(raw.index.max())
steps = raw.index.to_series().diff().dropna().value_counts()
F["frequency_counts"] = {str(k): int(v) for k, v in steps.items()}
F["n_expected_hours"] = int((raw.index.max() - raw.index.min()) / pd.Timedelta("1h") + 1)

# --- missing values --------------------------------------------------------
miss = raw.isna().sum()
F["missing_per_column"] = {k: int(v) for k, v in miss.items() if v}
F["pm25_missing_pct"] = round(100 * raw["pm25"].isna().mean(), 2)

is_na = raw["pm25"].isna()
run_id = (is_na != is_na.shift()).cumsum()
runs = is_na.groupby(run_id).agg(["first", "size"])
runs = runs[runs["first"]]["size"]
F["gap_runs"] = {"n_gaps": int(len(runs)), "median_len": float(runs.median()),
                 "gaps_le_6h": int((runs <= 6).sum()),
                 "gaps_gt_6h": int((runs > 6).sum()),
                 "gaps_gt_24h": int((runs > 24).sum()),
                 "longest_h": int(runs.max()),
                 "hours_in_gaps_le_6h": int(runs[runs <= 6].sum()),
                 "hours_in_gaps_gt_6h": int(runs[runs > 6].sum())}

by_year = raw["pm25"].isna().groupby(raw.index.year).sum()
by_year.to_csv(f"{TAB}/missing_pm25_by_year.csv", header=["missing_hours"])
F["missing_by_year"] = {int(k): int(v) for k, v in by_year.items()}

fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
ax[0].bar(by_year.index.astype(str), by_year.values, color=BLUE, width=0.55)
ax[0].set_title("Missing PM2.5 hours per year")
ax[0].set_ylabel("hours")
ax[1].hist(runs, bins=[0, 1, 3, 6, 12, 24, 48, 100, 160], color=BLUE,
           edgecolor="white")
ax[1].axvline(MAX_INTERP_GAP, color=ORANGE, lw=1.4)
ax[1].text(MAX_INTERP_GAP + 1, ax[1].get_ylim()[1] * 0.9,
           f"fill limit = {MAX_INTERP_GAP} h", color=INK)
ax[1].set_title("Length of each missing stretch")
ax[1].set_xlabel("consecutive missing hours")
ax[1].set_ylabel("number of stretches")
save(fig, "A1_missing_values")

# --- justify the interpolation limit by simulation ---------------------------
rng = np.random.default_rng(42)
known = raw["pm25"].copy()
sim_rows = []
for gap in [1, 3, 6, 12, 24, 48]:
    errs_i, errs_f, errs_m = [], [], []
    for _ in range(300):
        start = int(rng.integers(100, len(known) - 100 - gap))
        window = known.iloc[start - 1:start + gap + 1]
        if window.isna().any():
            continue
        truth = window.iloc[1:-1].values
        before, after = window.iloc[0], window.iloc[-1]
        interp = np.linspace(before, after, gap + 2)[1:-1]
        errs_i.append(np.mean(np.abs(interp - truth)))
        errs_f.append(np.mean(np.abs(before - truth)))
        errs_m.append(np.mean(np.abs(known.mean() - truth)))
    sim_rows.append({"gap_hours": gap,
                     "MAE_linear_interpolation": np.mean(errs_i),
                     "MAE_forward_fill": np.mean(errs_f),
                     "MAE_global_mean": np.mean(errs_m)})
sim = pd.DataFrame(sim_rows).round(1)
sim.to_csv(f"{TAB}/imputation_simulation.csv", index=False)
F["imputation_simulation"] = sim.to_dict(orient="records")

fig, ax = plt.subplots(figsize=(6, 3.4))
ax.plot(sim.gap_hours, sim.MAE_linear_interpolation, marker="o", color=BLUE,
        label="linear interpolation")
ax.plot(sim.gap_hours, sim.MAE_forward_fill, marker="o", color=ORANGE,
        label="forward fill")
ax.plot(sim.gap_hours, sim.MAE_global_mean, marker="o", color=GREY,
        label="global mean")
ax.set_xlabel("size of artificial gap (hours)")
ax.set_ylabel("mean absolute error (ug/m3)")
ax.set_title("Which fill method recovers hidden values best?")
ax.legend(frameon=False)
save(fig, "A2_imputation_simulation")

# --- impute and persist the clean series ------------------------------------
clean = impute_missing(raw)
clean.to_csv("data/processed/pm25_clean.csv", index_label="datetime")
F["pm25_missing_after_imputation"] = int(clean["pm25"].isna().sum())

# --- summary statistics ----------------------------------------------------
num_cols = ["pm25", "dewp", "temp", "pres", "wind_speed", "snow_hours",
            "rain_hours"]
desc = raw[num_cols].describe().T
desc["skew"] = raw[num_cols].skew()
desc["kurtosis"] = raw[num_cols].kurt()
desc.round(2).to_csv(f"{TAB}/summary_statistics.csv")
F["summary_statistics"] = desc.round(2).to_dict(orient="index")
F["wind_dir_share_pct"] = (raw["wind_dir"].value_counts(normalize=True) * 100).round(1).to_dict()

# --- distributions -----------------------------------------------------------
fig, axes = plt.subplots(2, 4, figsize=(12, 5.2))
for ax, c in zip(axes.ravel(), num_cols):
    ax.hist(raw[c].dropna(), bins=50, color=BLUE, edgecolor="white", lw=0.3)
    ax.set_title(c)
    ax.set_ylabel("hours")
axes.ravel()[-1].axis("off")
save(fig, "A3_distributions")

fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
ax[0].boxplot(raw["pm25"].dropna(), orientation="horizontal", widths=0.5,
              flierprops=dict(marker=".", markersize=2, markerfacecolor=GREY,
                              markeredgecolor=GREY))
ax[0].set_title("PM2.5 outliers (box plot)")
ax[0].set_xlabel("ug/m3")
ax[0].set_yticks([])
ax[1].hist(np.log1p(raw["pm25"].dropna()), bins=50, color=BLUE,
           edgecolor="white", lw=0.3)
ax[1].set_title("log(1 + PM2.5) is closer to bell-shaped")
ax[1].set_xlabel("log(1 + PM2.5)")
save(fig, "A4_pm25_outliers_log")
F["pm25_extreme"] = {
    "above_300": int((raw["pm25"] > 300).sum()),
    "above_500": int((raw["pm25"] > 500).sum()),
    "iqr_upper_fence": float(raw["pm25"].quantile(.75) +
                             1.5 * (raw["pm25"].quantile(.75) - raw["pm25"].quantile(.25))),
    "pct_above_fence": round(100 * (raw["pm25"] > raw["pm25"].quantile(.75) +
                             1.5 * (raw["pm25"].quantile(.75) - raw["pm25"].quantile(.25))).mean(), 2)}

# ===========================================================================
# PART B - analytical questions (all use the imputed series)
# ===========================================================================
d = clean.copy()
d["year"], d["month"], d["hour"] = d.index.year, d.index.month, d.index.hour

# ---- Q1 trend ---------------------------------------------------------------
daily = d["pm25"].resample("D").mean()
ma30 = daily.rolling(30, min_periods=20, center=True).mean()
ma365 = daily.rolling(365, min_periods=300, center=True).mean()
yearly = d.groupby("year")["pm25"].mean().round(1)
x = (daily.dropna().index - daily.dropna().index[0]).days.values
lr = stats.linregress(x, daily.dropna().values)
F["Q1"] = {"yearly_mean": yearly.to_dict(),
           "slope_ug_per_year": round(lr.slope * 365.25, 2),
           "p_value": float(lr.pvalue), "r2": round(lr.rvalue ** 2, 4),
           "hours_above_150_by_year": d[d.pm25 > 150].groupby("year").size().to_dict()}
fig, ax = plt.subplots(figsize=(11, 3.6))
ax.plot(daily.index, daily, color=GREY, lw=0.6, label="daily mean")
ax.plot(ma30.index, ma30, color=BLUE, lw=1.6, label="30-day moving average")
ax.plot(ma365.index, ma365, color=ORANGE, lw=1.8, label="365-day moving average")
ax.set_ylabel("PM2.5 (ug/m3)")
ax.set_title("Q1  Is there a long-term trend in PM2.5?")
ax.legend(frameon=False, ncol=3, loc="upper right")
save(fig, "Q1_trend")

# ---- Q2 seasonality -----------------------------------------------------------
monthly = d.groupby("month")["pm25"].mean().round(1)
F["Q2"] = {"monthly_mean": monthly.to_dict(),
           "winter_djf_mean": round(d[d.month.isin([12, 1, 2])].pm25.mean(), 1),
           "summer_jja_mean": round(d[d.month.isin([6, 7, 8])].pm25.mean(), 1)}
fig, ax = plt.subplots(figsize=(7, 3.4))
ax.bar(monthly.index, monthly.values, color=BLUE, width=0.65)
ax.set_xticks(range(1, 13))
ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                    "Sep", "Oct", "Nov", "Dec"])
ax.set_ylabel("mean PM2.5 (ug/m3)")
ax.set_title("Q2  Is there a seasonal pattern?")
save(fig, "Q2_seasonality")

# ---- Q3 daily cycle --------------------------------------------------------------
winter = d[d.month.isin([12, 1, 2])].groupby("hour")["pm25"].mean()
summer = d[d.month.isin([6, 7, 8])].groupby("hour")["pm25"].mean()
F["Q3"] = {"winter_peak_hour": int(winter.idxmax()), "winter_peak": round(winter.max(), 1),
           "winter_low_hour": int(winter.idxmin()), "winter_low": round(winter.min(), 1),
           "summer_peak_hour": int(summer.idxmax()), "summer_peak": round(summer.max(), 1),
           "summer_low_hour": int(summer.idxmin()), "summer_low": round(summer.min(), 1)}
fig, ax = plt.subplots(figsize=(7, 3.4))
ax.plot(winter.index, winter.values, color=BLUE, marker="o", ms=3, label="winter (Dec-Feb)")
ax.plot(summer.index, summer.values, color=ORANGE, marker="o", ms=3, label="summer (Jun-Aug)")
ax.set_xticks(range(0, 24, 3))
ax.set_xlabel("hour of day")
ax.set_ylabel("mean PM2.5 (ug/m3)")
ax.set_title("Q3  What does a typical day look like?")
ax.legend(frameon=False)
save(fig, "Q3_daily_cycle")

# ---- Q4 weather correlation --------------------------------------------------------
wc = d[["pm25", "dewp", "temp", "pres", "wind_speed", "snow_hours", "rain_hours"]].copy()
pear = wc.corr()
spear = wc.corr(method="spearman")["pm25"].round(2)
F["Q4"] = {"pearson_with_pm25": pear["pm25"].round(2).to_dict(),
           "spearman_with_pm25": spear.to_dict(),
           "mean_by_wind_dir": d.groupby("wind_dir")["pm25"].mean().round(1).to_dict(),
           "median_by_wind_dir": d.groupby("wind_dir")["pm25"].median().round(1).to_dict()}
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
im = ax[0].imshow(pear.values, cmap="RdBu_r", vmin=-1, vmax=1)
ax[0].set_xticks(range(len(pear)))
ax[0].set_yticks(range(len(pear)))
ax[0].set_xticklabels(pear.columns, rotation=45, ha="right")
ax[0].set_yticklabels(pear.columns)
ax[0].grid(False)
for i in range(len(pear)):
    for j in range(len(pear)):
        ax[0].text(j, i, f"{pear.values[i, j]:.2f}", ha="center", va="center",
                   fontsize=7, color="white" if abs(pear.values[i, j]) > 0.6 else INK)
ax[0].set_title("Q4  Correlation between variables")
fig.colorbar(im, ax=ax[0], shrink=0.75)
order = ["cv", "NE", "NW", "SE"]
ax[1].boxplot([d[d.wind_dir == w].pm25.dropna() for w in order], tick_labels=order, showfliers=False,
              widths=0.5)
ax[1].set_ylabel("PM2.5 (ug/m3)")
ax[1].set_xlabel("wind direction (cv = calm / variable)")
ax[1].set_title("PM2.5 by wind direction (outliers hidden)")
save(fig, "Q4_weather_correlation")

# ---- Q5 lag effects (LAGGED FEATURES) -------------------------------------------------
s = d["pm25"]
acf_vals = [s.autocorr(lag=k) for k in range(1, 73)]
F["Q5"] = {"acf_lag1": round(acf_vals[0], 3), "acf_lag2": round(acf_vals[1], 3),
           "acf_lag3": round(acf_vals[2], 3), "acf_lag6": round(acf_vals[5], 3),
           "acf_lag12": round(acf_vals[11], 3), "acf_lag24": round(acf_vals[23], 3),
           "acf_lag48": round(acf_vals[47], 3), "acf_lag72": round(acf_vals[71], 3)}
fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
ax[0].bar(range(1, 73), acf_vals, color=BLUE, width=0.7)
ax[0].axhline(0, color=GREY, lw=0.8)
for lag in (1, 24, 48, 72):
    ax[0].annotate(f"{acf_vals[lag - 1]:.2f}", (lag, acf_vals[lag - 1]),
                   textcoords="offset points", xytext=(0, 4), ha="center", fontsize=7)
ax[0].set_xlabel("lag (hours)")
ax[0].set_ylabel("autocorrelation")
ax[0].set_title("Q5  Autocorrelation of PM2.5")
sample = d.sample(4000, random_state=1)
for a, k, col in ((ax[1], 1, BLUE), (ax[2], 24, ORANGE)):
    lagged = s.shift(k)
    tmp = pd.DataFrame({"now": s, "lag": lagged}).dropna().sample(4000, random_state=1)
    a.scatter(tmp["lag"], tmp["now"], s=3, alpha=0.25, color=col)
    a.set_xlabel(f"PM2.5 {k} h earlier")
    a.set_ylabel("PM2.5 now")
    a.set_title(f"lag {k}:  r = {s.autocorr(k):.2f}")
save(fig, "Q5_lag_effects")

# ---- Q6 moving averages (MOVING AVERAGES) ------------------------------------------------
target_next = s.shift(-HORIZON)
windows = [1, 3, 6, 12, 24, 48, 72, 168]
corr_ma = {}
for w in windows:
    ma = s.rolling(w, min_periods=w).mean()
    corr_ma[w] = round(pd.concat([ma, target_next], axis=1).dropna().corr().iloc[0, 1], 4)
F["Q6"] = {"corr_next_hour_vs_ma_window": corr_ma}
# a month where smoothing is easy to see
zoom = s["2012-01-10":"2012-02-10"]
fig, ax = plt.subplots(1, 2, figsize=(12, 3.6), gridspec_kw={"width_ratios": [1.5, 1]})
ax[0].plot(zoom.index, zoom, color=GREY, lw=0.8, label="hourly")
ax[0].plot(zoom.index, s.rolling(6).mean()[zoom.index], color=BLUE, label="6-hour moving average")
ax[0].plot(zoom.index, s.rolling(24).mean()[zoom.index], color=ORANGE, lw=1.8, label="24-hour moving average")
ax[0].set_ylabel("PM2.5 (ug/m3)")
ax[0].xaxis.set_major_locator(mdates.DayLocator(interval=7))
ax[0].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax[0].set_title("Q6  Moving averages smooth the noise (Jan-Feb 2012)")
ax[0].legend(frameon=False, loc="upper right", fontsize=8)
ax[1].plot(list(corr_ma.keys()), list(corr_ma.values()), marker="o", color=BLUE)
ax[1].set_xscale("log")
ax[1].set_xticks(windows)
ax[1].set_xticklabels([str(w) for w in windows])
ax[1].set_xlabel("moving-average window (hours)")
ax[1].set_ylabel(f"correlation with PM2.5 {HORIZON} h ahead")
ax[1].set_title("Which window predicts best?")
save(fig, "Q6_moving_averages")

# ---- Q7 delayed effect of wind (LAGGED external variable) -----------------------------------
cross = {k: round(d["wind_speed"].shift(k).corr(d["pm25"]), 3) for k in range(0, 49)}
cross_log = {k: round(np.log1p(d["wind_speed"]).shift(k).corr(np.log1p(d["pm25"])), 3)
             for k in range(0, 49)}
bins = [0, 1, 2, 5, 10, 20, 50, 600]
d["wind_bin"] = pd.cut(d["wind_speed"], bins=bins, include_lowest=True)
by_bin = d.groupby("wind_bin", observed=True)["pm25"].mean().round(1)
F["Q7"] = {"corr_wind_lag0": cross[0], "corr_wind_lag6": cross[6],
           "corr_wind_lag12": cross[12], "corr_wind_lag24": cross[24],
           "most_negative_lag": min(cross, key=cross.get),
           "most_negative_value": min(cross.values()),
           "mean_pm25_by_wind_bin": {str(k): float(v) for k, v in by_bin.items()}}
fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
ax[0].bar(list(cross.keys()), list(cross.values()), color=BLUE, width=0.7)
ax[0].axhline(0, color=GREY, lw=0.8)
ax[0].set_xlabel("cumulated wind speed measured k hours EARLIER")
ax[0].set_ylabel("correlation with PM2.5 now")
ax[0].set_title("Q7  Does wind clear the air with a delay?")
ax[1].bar([str(b) for b in by_bin.index], by_bin.values, color=BLUE, width=0.65)
ax[1].set_xlabel("cumulated wind speed Iws (m/s)")
ax[1].set_ylabel("mean PM2.5 (ug/m3)")
ax[1].set_title("Stronger wind, cleaner air")
ax[1].tick_params(axis="x", rotation=30)
save(fig, "Q7_wind_lag")

with open(f"{TAB}/eda_findings.json", "w") as f:
    json.dump(F, f, indent=2, default=str)
print(json.dumps(F, indent=1, default=str))
