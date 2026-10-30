# Beijing PM2.5 Forecasting

Time-series exploratory analysis and six-hour-ahead PM2.5 forecasting using
hourly observations from Beijing, 2010–2014. The repository includes the Task 1
notebook, reusable preprocessing code, EDA and model-training scripts, saved
figures and tables, and a trained model artifact.

## Dataset

The analysis expects the Beijing PM2.5 CSV at:

```text
data/raw/PRSA_data_2010.1.1-2014.12.31.csv
```

The raw dataset is not included in this repository. Obtain the source data
separately and place the CSV at the path above. Check the dataset source's terms
before redistributing a copy.

## Setup

From the repository root, create and activate a virtual environment, then
install the project dependencies.

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS or Linux, replace the activation command with:

```sh
source .venv/bin/activate
```

## Run the analysis

Run the scripts from the repository root:

```sh
python scripts/01_eda.py
python scripts/02_train_models.py
```

The EDA script produces the cleaned hourly series and analysis outputs.
The model-training script performs time-series hyperparameter tuning, compares
the experiments, selects a model using validation data, refits it, and evaluates
it on the held-out 2014 period. Model tuning may take several minutes.

To explore the analysis interactively, open
`notebooks/Task1_Time_Series_PM25_Notebook.ipynb` in Jupyter or VS Code, select
the project's `.venv` Python environment as the kernel, and run the notebook
from top to bottom.

## Outputs

- `outputs/figures/` - EDA, analytical-question, and model-evaluation figures.
- `outputs/tables/` - EDA summaries, experiment comparisons, tuning results,
  feature importance, and error breakdowns.
- `data/processed/pm25_clean.csv` - regenerated EDA-cleaned hourly series.
- `models/pm25_model.joblib` - final fitted forecasting model.
- `models/model_metadata.json` - model features, forecast horizon, parameters,
  and test metrics.
- `report/task1_findings.md` - written summary of Task 1 results.

The raw and processed CSV files are excluded by `.gitignore`; scripts regenerate
the processed series from the locally supplied raw dataset.

## REST API (Task 3)

The `api/` package is a FastAPI service that exposes the same endpoints for both
databases:

- MySQL at `/sql/readings`, backed by `weather_readings` and
  `pm25_measurements` (see `sql/schema.sql`).
- MongoDB at `/mongo/readings`, backed by the `air_quality_readings` collection
  (see `mongodb/collection_design.js`).

### Configure

From the repository root, install the API dependencies and create a local
settings file from the template:

```powershell
python -m pip install -r api/requirements.txt
Copy-Item api/.env.example api/.env
```

On macOS or Linux, use `cp api/.env.example api/.env` for the second command.
Then set your connection details in `api/.env`, which is excluded by
`.gitignore`:

| Variable | Default |
|---|---|
| `MYSQL_HOST` | `localhost` |
| `MYSQL_PORT` | `3306` |
| `MYSQL_USER` | `root` |
| `MYSQL_PASSWORD` | empty |
| `MYSQL_DATABASE` | `beijing_air_quality` |
| `DEFAULT_STATION_ID` | `1` |
| `MONGO_URI` | `mongodb://localhost:27017` |
| `MONGO_DB` | `beijing_air_quality` |
| `MONGO_COLLECTION` | `air_quality_readings` |

`DEFAULT_STATION_ID` is the station that readings created through
`POST /sql/readings` are linked to.

### Load the data

MySQL: run `sql/schema.sql`, then `sql/seed.sql`. The seed script creates
station 1 and loads the CSV.

MongoDB:

```sh
python scripts/load_mongo.py
```

The loader reads the CSV from `data/raw/`, inserts one document per hour in
batches of 1,000, stores missing PM2.5 values (`NA`) as `null`, and creates
indexes on `timestamp`, `pm25` and `weather.wind_dir`. If the collection already
has documents, the script stops without loading. Run it with `--drop` to clear
the collection and reload. `--csv` and `--batch-size` override the defaults.

### Run the server

```sh
uvicorn api.main:app --reload
```

Run it from the repository root. The API listens on `http://127.0.0.1:8000`,
and interactive documentation is at `http://127.0.0.1:8000/docs`.

### Endpoints

Replace `{db}` with `sql` or `mongo`.

| Method | Path | Success | Errors |
|---|---|---|---|
| `POST` | `/{db}/readings` | 201, created reading | 409, 422 |
| `GET` | `/{db}/readings/latest` | 200, most recent reading by timestamp | 404 if there are no readings |
| `GET` | `/{db}/readings/range` | 200, page of readings | 400 if `start` is after `end`, 422 |
| `GET` | `/{db}/readings/{id}` | 200, reading | 404 |
| `PUT` | `/{db}/readings/{id}` | 200, updated reading | 404, 409, 422 |
| `DELETE` | `/{db}/readings/{id}` | 204, no body | 404 |

- 409 is returned by the SQL endpoints only, when a reading already exists for
  that station and hour.
- 422 means the request body or query parameters failed validation.
- SQL ids are integers (`reading_id`). MongoDB ids are the document `_id`, a
  24-character hex string.
- On the SQL side, `POST` inserts into `weather_readings` and then
  `pm25_measurements` in one transaction, `GET` joins the two tables, `PUT`
  updates both in one transaction, and `DELETE` removes the
  `pm25_measurements` row before the `weather_readings` row.

### Request body

`POST` and `PUT` take the same body. `PUT` replaces the whole reading.

```json
{
  "timestamp": "2014-12-31T23:00:00",
  "pm25": 171,
  "weather": {
    "dew_point": -18,
    "temperature": -4,
    "pressure": 1034,
    "wind_dir": "NW",
    "wind_speed": 16.1
  },
  "precipitation": {
    "snow_hours": 0,
    "rain_hours": 0
  }
}
```

- `pm25` can be `null` for hours without a measurement.
- `wind_dir` must be `NE`, `NW`, `SE` or `cv`.
- `precipitation` is optional and defaults to zero for both fields.
- `year`, `month`, `day` and `hour` are derived from `timestamp`.
- Timestamps are truncated to the hour. Send Beijing local time without a UTC
  offset, as in the dataset. A timestamp that includes an offset is converted
  to UTC before it is stored.

Responses contain the same fields plus `id`, `year`, `month`, `day` and `hour`.
SQL responses also include `measurement_id` and `station_id`, and MongoDB
responses include `station`.

### Date range queries

`GET /{db}/readings/range` accepts these query parameters:

| Parameter | Default | Description |
|---|---|---|
| `start` | required | ISO 8601 datetime, inclusive |
| `end` | required | ISO 8601 datetime, inclusive |
| `limit` | `100` | Readings per page, from 1 to 1000 |
| `offset` | `0` | Readings to skip |

A date without a time, such as `2013-01-31`, means midnight at the start of that
day. Use `2013-01-31T23:00:00` to include the whole day.

The response is a JSON object with `total` (the number of readings in the
range), `limit`, `offset` and `items` (the readings on this page, oldest first).

### Examples

```sh
curl http://127.0.0.1:8000/sql/readings/latest
curl "http://127.0.0.1:8000/mongo/readings/range?start=2013-01-01T00:00:00&end=2013-01-31T23:00:00&limit=50&offset=50"
curl http://127.0.0.1:8000/sql/readings/1
curl -X POST http://127.0.0.1:8000/mongo/readings -H "Content-Type: application/json" -d '{"timestamp": "2015-01-01T00:00:00", "pm25": null, "weather": {"dew_point": -19, "temperature": -5, "pressure": 1035, "wind_dir": "NW", "wind_speed": 4.02}}'
```

In Windows PowerShell, type `curl.exe` instead of `curl`. The `POST` example is
easiest to run from Git Bash or from the `/docs` page.

## Forecast script (Task 4)

`scripts/predict.py` connects the earlier tasks. It fetches readings from the
API, preprocesses them the same way as in training, loads the trained model and
forecasts PM2.5 six hours ahead.

1. **Fetch.** `GET /{db}/readings/latest` sets the forecast origin. Then
   `GET /{db}/readings/range` returns the 96 hours up to and including the
   origin, following pagination. The features need 72 hours of history, and
   the extra 24 hours let gaps at the start of the window be filled.
2. **Preprocess.** The script converts the API JSON to the Task 1 column names
   and builds a regular hourly index. Like `scripts/02_train_models.py`, it
   forward-fills PM2.5 for at most 6 hours, using only past values. Absent
   hours of weather are filled the same way. It then calls
   `src.preprocessing.build_features`, the same function used in training, to
   create the lag, moving-average, calendar and wind-direction features.
3. **Load.** It loads `models/pm25_model.joblib` and checks that the horizon in
   `models/model_metadata.json` matches the preprocessing code.
4. **Predict.** It forecasts PM2.5 at origin + 6 h. If the API already has the
   reading for that hour, the script also prints the actual value and the
   error.

Start the API (see above), then from the repository root:

```sh
python scripts/predict.py                              # latest MongoDB reading
python scripts/predict.py --db sql                     # latest MySQL reading
python scripts/predict.py --at 2014-06-15T12:00:00     # a past origin, compared with the actual value
python scripts/predict.py --json                       # machine-readable output
```

| Option | Default | Description |
|---|---|---|
| `--db` | `mongo` | Read from the `mongo` or `sql` endpoints |
| `--at` | latest reading | Forecast origin, ISO 8601 |
| `--api-url` | `http://127.0.0.1:8000`, or the `API_URL` environment variable | Base URL of the API |
| `--model`, `--metadata` | `models/pm25_model.joblib`, `models/model_metadata.json` | Model files |
| `--json` | off | Print the result as JSON |

Example output with the full dataset loaded, for a past origin
(`--at 2014-06-15T12:00:00`). `--db sql` gives the same result:

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

Without `--at`, the origin is the last reading in the dataset
(2014-12-31 23:00), and the script forecasts 13.5 ug/m3 for 2015-01-01 05:00.
No actual value is printed because the dataset ends before that hour.

If the 72 hours before the origin contain a gap longer than 6 hours, the model's
features can't be computed. The script then stops, names the missing features
and asks for a different `--at`. It also exits with a message if the API can't
be reached. The model was saved with scikit-learn 1.9.1, so use that version, or
retrain with `scripts/02_train_models.py`, to avoid version warnings.

### Checking the forecast against training

`scripts/check_predict.py` checks that serving matches training. It samples
forecast origins from the CSV, half of them in the first hour after a PM2.5
gap. For each origin, it compares the training pipeline's prediction from the
raw CSV with the prediction `predict.py` makes from the API:

```sh
python scripts/check_predict.py                  # 10 origins, both databases
python scripts/check_predict.py --n 20 --db sql
```

It prints one line per origin and database, ends with the number of matches,
and exits with code 1 if any prediction differs. With the full dataset loaded,
all 20 default checks match on both databases.
