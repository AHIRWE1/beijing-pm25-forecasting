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
