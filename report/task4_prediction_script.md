# Task 4: Prediction/forecast script (results come from runs against the full dataset loaded into MySQL and MongoDB)

Author: Nick Singizwa. Code: `scripts/predict.py` (forecast script) and `scripts/check_predict.py` (consistency check), documented in the README section "Forecast script (Task 4)".

## A. Purpose
The script ties the earlier tasks together. It fetches hourly readings from the Task 3 API, applies the same preprocessing as the Task 1 training pipeline, loads the trained model and forecasts PM2.5 six hours ahead. It works with either database: `--db mongo` (the default) or `--db sql`.

## B. Pipeline
**1. Fetch from the API.** `GET /{db}/readings/latest` returns the newest reading. Its timestamp becomes the forecast origin, unless `--at` names an earlier hour. `GET /{db}/readings/range` then returns the 96 hours ending at the origin. The features need 72 hours of history (the longest window is the 72 h moving average). The extra 24 hours mean that a short gap at the start of the window can still be filled from earlier readings. The range endpoint returns at most 1,000 rows per page, so the script follows the `limit`/`offset` pagination until it has every row. HTTP calls use only the Python standard library, so the project needs no extra dependency.

**2. Preprocess the same way as Task 1.** The API's JSON (`weather.dew_point`, `precipitation.rain_hours`, ...) is flattened back into the Task 1 column names (`dewp`, `rain_hours`, ...) and placed on a regular hourly index, so an hour absent from the database shows up as a missing row. Missing PM2.5 values are then forward-filled for at most 6 hours, the same rule `scripts/02_train_models.py` used for the training features. Forward fill only uses past values. We deliberately did not use the interpolation from the EDA (`impute_missing`), because it fills a gap using readings after it, which the model never had at training time and could not have at a real forecast time. Absent weather hours are filled the same way. Features are built by `src.preprocessing.build_features`, the same function used in training, so all 32 inputs (current conditions, PM2.5 lags of 1-24 h, moving averages of 3-72 h, 24 h standard deviation, rolling weather, cyclical hour/month, weekend flag and one-hot wind direction) are computed identically. The columns are reordered to match `feature_columns` in `models/model_metadata.json`.

**3. Load the trained model.** `models/pm25_model.joblib` is the tuned Random Forest selected in Task 1 (Exp3_RandomForest_all_features: 100 trees, max_depth 20, min_samples_leaf 20, max_features 0.6; 2014 test RMSE 53.96, MAE 34.82, R2 0.671). Before predicting, the script checks that the horizon stored in the metadata (6 h) matches `HORIZON` in the preprocessing code. This stops a model trained for a different horizon from being used by mistake.

**4. Forecast.** The model predicts PM2.5 at origin + 6 h. When the origin is in the past, the script also fetches the reading for the forecast hour from the API and prints the actual value and the error. `--json` prints the result as JSON, including a data-quality report (hours absent, PM2.5 gaps, gaps left unfilled).

## C. Results
Forecast from a past origin with a known outcome (`python scripts/predict.py --at 2014-06-15T12:00:00`):

```text
Database:          mongo
Model:             Exp3_RandomForest_all_features
Records fetched:   96 (0 of 96 hours absent, 0 PM2.5 gaps, 0 left unfilled)
Forecast origin:   2014-06-15T12:00:00
  PM2.5 now:       89.0 ug/m3
  24 h average:    95.2 ug/m3
Forecast for:      2014-06-15T18:00:00 (+6 h)
  Predicted PM2.5: 93.0 ug/m3
  Actual PM2.5:    100.0 ug/m3 (error -7.0)
```

* `--db sql` gives the identical result (predicted 93.0, actual 100.0).
* From the latest reading (2014-12-31 23:00, PM2.5 12.0, 24 h average 10.0), both databases forecast 13.5 ug/m3 for 2015-01-01 05:00. The dataset ends before that hour, so there is no actual value to compare.
* The forecast is not always this close. At 2012-10-25 12:00 the model predicted 187.3 against an actual 331.0 (error -143.7). This matches the Task 1 finding that errors grow with the pollution level (MAE 90.0 above 250 ug/m3), because sharp pollution build-ups are hard to anticipate six hours ahead.

## D. Verification
**Serving matches training.** `scripts/check_predict.py` samples forecast origins from the raw CSV. Half are random and half are the first observed hour after a real PM2.5 gap, so gap filling is tested too. For each origin it compares the prediction the training pipeline makes directly from the CSV with the prediction `predict.py` makes from API records. With the default settings (10 origins on both databases), all 20 comparisons matched exactly. An extra MySQL-only run with another seed matched 4/4. This shows the conversion from database records back to model inputs adds no difference, whether the data comes from MySQL or MongoDB.

**Error handling.** If the 72 hours before the origin contain a PM2.5 gap longer than 6 hours, the features cannot be computed honestly. The script then stops with exit code 1 and names the missing features, rather than predicting from made-up inputs. For example, `--at 2010-08-15T12:00:00` lies inside a real 68-hour outage (41 of the 96 fetched hours had no PM2.5). The script also exits with a clear message if the API cannot be reached or returns an error, and if the model files are missing.

## E. Individual contribution (Nick Singizwa)
Designed and implemented Task 4: the forecast script, the training-vs-serving consistency check and the README documentation. Tested both against the full dataset loaded into MySQL (via the group's `schema.sql`/`seed.sql`) and MongoDB (via `load_mongo.py`), served by the group's API. Commits on branch `task-4`: `initial predict.py`, `help text fix`, `comparing API forecasts`, `sanity check`.
