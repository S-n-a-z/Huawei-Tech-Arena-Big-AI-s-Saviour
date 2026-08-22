# Huawei Tech Arena 2026 - Topic Two

This repository contains our work on predicting the continuity of power supplied to AI data centres during severe weather. It brings together the team's location, outage and weather preparation with a reproducible forecasting pipeline and a transparent power-architecture layer.

The statistical model estimates district-level grid risk. A separate engineering calculation then applies the four architecture configurations described in the challenge. Keeping these stages separate makes the assumptions easy to inspect and lets us replace the final Huawei parameters without retraining the regional model.

## What is included

- SSEN substation locations converted from British National Grid coordinates to WGS84.
- NaFIRS low-voltage incident preparation for the SEPD and SHEPD licence areas.
- District-level Open-Meteo history, with spatial sampling and validation reports.
- Causal risk, weather and seasonal features for both forecast horizons.
- Chronologically purged validation and a persistence baseline.
- A two-stage model for rare outage events and conditional severity.
- Configurable calculations for UPS 2N, distributed redundancy, HVDC 2N and direct utility 2N.
- Optional OpenStreetMap infrastructure features.
- Automated tests, output validation, prediction manifests and a technical report draft.

## Current evidence

The recorded development run begins with 220,715 NaFIRS incidents across 33 district codes. The model uses the 31 districts with a supported SSEN operating-area match; NATS and NATSL remain in the audit file but are not silently assigned invented coordinates. On the held-out period, the day-ahead model improves MAE from 0.03457 to 0.02871 and PR-AUC from 0.18897 to 0.30313. The hour-ahead model improves RMSE from 0.09827 to 0.07908 and PR-AUC from 0.42455 to 0.63017, although persistence remains better on MAE. Full figures and limitations are in `reports/technical_report.docx` and `reports/mvp_results.md`.

## Important final-input note

The architecture coefficients in `configs/default.toml` are marked as illustrative engineering defaults. They must be replaced by the topology type, sigmoid coefficients, load, storage and generator parameters supplied for the assessed test case. The public brief does not include the final scoring metric or sample-submission schema, so the output adapter is kept in `src/tech_arena/resilience.py` and can be changed without retraining.

## Set-up on Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

For the exact environment used for the recorded results:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

## Run the complete pipeline

```powershell
.\.venv\Scripts\python.exe -m tech_arena run-all
```

This performs data acquisition, normalisation, weather download, both feature builds, both training runs, prediction export, validation and results-summary generation. Raw third-party data stay under `data/raw/` and are ignored by Git.

Optional OSM augmentation:

```powershell
.\.venv\Scripts\python.exe -m tech_arena download-osm
.\.venv\Scripts\python.exe -m tech_arena build-features --include-osm
.\.venv\Scripts\python.exe -m tech_arena train
```

If public Overpass instances are throttled, preserve the completed cache and build a feature table with explicit missingness instead of retrying aggressively:

```powershell
.\.venv\Scripts\python.exe -m tech_arena download-osm --cached-only
```

Run the tests and validate the generated outputs:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m tech_arena validate
```

## Step-by-step execution

```powershell
.\.venv\Scripts\python.exe -m tech_arena download-nafirs
.\.venv\Scripts\python.exe -m tech_arena prepare-nafirs
.\.venv\Scripts\python.exe -m tech_arena prepare-locations
.\.venv\Scripts\python.exe -m tech_arena download-weather
.\.venv\Scripts\python.exe -m tech_arena build-features
.\.venv\Scripts\python.exe -m tech_arena train
.\.venv\Scripts\python.exe -m tech_arena baseline
.\.venv\Scripts\python.exe -m tech_arena export
.\.venv\Scripts\python.exe -m tech_arena report
```

## Main outputs

- `artifacts/day_ahead/` and `artifacts/hour_ahead/`: trained model, validation metrics, and validation predictions.
- `outputs/day_ahead_predictions.csv`: architecture-expanded, 48-step forecast for each district.
- `outputs/hour_ahead_predictions.csv`: architecture-expanded, 72-step forecast for each district.
- `outputs/*_manifest.json`: row counts, checksums and validation information.
- `reports/mvp_results.md`: generated data and validation summary.
- `reports/technical_report.docx`: Word report prepared for the competition submission.

The output CSVs use the latest available feature row for each district and horizon as a compact inference demonstration. Replace their column adapter and time window when the official sample-submission file is released.

## Before the assessed submission

1. Replace the illustrative topology values with the parameters supplied by the organising committee.
2. Match `export_submission` to the official sample CSV, including column names, units, row order and test window.
3. Replace the empirical exposure proxy if an official regional-risk target or district customer totals are supplied.
4. Confirm whether forecast weather is an allowed known covariate and use only forecasts issued by the prediction time.
5. Run the pipeline from a clean environment, review both manifests, and update the final report with the scored result.

## Data sources

The core sources are SSEN NaFIRS LV Faults, SSEN Substation Data and Open-Meteo. OpenStreetMap is optional and is excluded from the core results unless its held-out ablation is beneficial. Source links, licences and attribution requirements are recorded in `SOURCES.md`.
