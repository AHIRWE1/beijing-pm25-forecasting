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
