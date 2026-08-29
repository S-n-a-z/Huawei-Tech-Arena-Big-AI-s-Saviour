# Huawei Tech Arena 2026 — Topic Two, Phase 1

This repository contains Big AI's Saviour's Phase 1 entry for the AI data-centre power-supply risk forecasting challenge. The administrator confirmed that the preliminary-round deadline is **31 August 2026**.

The submission forecasts the proportion of customers without electricity (`predicted_x`) in five US counties:

- **Task A:** 48 hourly forecasts, with at least one issue per calendar day;
- **Task B:** 24 forecasts at 15-minute intervals, covering six hours and issued at least every six hours.

The selected counties are Los Angeles (California), Miami-Dade (Florida), Cook (Illinois), Harris (Texas) and King (Washington). They were fixed using January–August 2025 data only, before the scoring period was examined.

## Exact submission artefacts

The files needed to reproduce the submitted prediction file are now included:

- `artifacts/phase1/A/model.joblib` and `artifacts/phase1/B/model.joblib` are the exact fitted models used for the submission. Each file contains the fitted imputer, county encoder, classifier, regressor, feature list and selected persistence weight.
- `data/processed/phase1_A_test.csv.gz` and `data/processed/phase1_B_test.csv.gz` are the frozen engineered inference inputs used for the final run. They include the archived forecast-weather fields and therefore remove any live API dependency from inference.
- `artifacts/phase1/inference_manifest.json` records the expected file sizes, environment versions and checksums for the frozen artefacts.
- `outputs/predictions.csv` is the submitted file. It contains 65,880 rows across both tasks, five counties and 2,285 complete county/issue batches.

The repository does not need separate scaler or encoder files: those fitted objects are part of the two serialised scikit-learn pipelines.

## Reproduce the submitted CSV without training

Python 3.12.13 and the pinned package versions in `requirements-lock.txt` reproduce the recorded run. The organiser permits Python 3.9 or later; this project states the exact interpreter used so that the submitted serialised models can be loaded consistently.

From the repository root in Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m tech_arena infer-phase1
.\.venv\Scripts\python.exe validate_submission.py outputs\reproduced_predictions.csv
```

On Linux or macOS, use the equivalent commands:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m tech_arena infer-phase1
.venv/bin/python validate_submission.py outputs/reproduced_predictions.csv
```

`infer-phase1` only loads the frozen models and frozen test feature tables. It does not download data, call an API or refit a model. The command writes `outputs/reproduced_predictions.csv` and checks that it is byte-for-byte identical to the submitted `outputs/predictions.csv`.

Approximate timings on a normal four-core laptop are:

- environment setup: 3–8 minutes;
- frozen inference: 30–90 seconds;
- submission validation: under 15 seconds;
- complete automated test suite: 1–2 minutes.

Run the tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .test-tmp
```

Use `.venv/bin/python -m pytest --basetemp .test-tmp` on Linux or macOS. The same test suite also runs on Ubuntu through GitHub Actions.

## Method in brief

The preparation stage builds a complete 15-minute grid from EAGLE-I. The source omits zero-outage rows and cannot distinguish those omissions from collection gaps, so absent rows are set to zero while `record_present` is retained as a missingness feature. The denominator is the official county customer count supplied with the EAGLE-I release.

Every model feature is available before the forecast issue time. Inputs include current risk, 1/6/24/168-hour lags, causal rolling statistics, data coverage, calendar terms, lead time and ECMWF IFS weather. Training uses historical ECMWF IFS fields. The test-period weather was taken from archived Open-Meteo Single Runs, with each model run fixed six hours before the corresponding issue time.

Separate histogram-gradient-boosting models estimate outage magnitude for Tasks A and B. Their outputs are blended with persistence using weights chosen on chronological hold-out data. The classifier stored in each fitted pipeline is used for event diagnostics; the submitted magnitude is produced by the regressor and persistence blend.

The command below exports a transparent breakdown by lead-time band and county from the recorded chronological hold-outs:

```powershell
.\.venv\Scripts\python.exe -m tech_arena diagnose-phase1
```

The command summarises the committed row-level diagnostic records without needing the full training cache. Add `--rebuild` after a full training run to reconstruct those records from the training features and recorded validation predictions. The committed summary is in `reports/phase1_diagnostics.json`. Task A improves on persistence in every reported lead band and county. Task B improves from 105 minutes onwards; for 15–90 minutes, persistence remains 2.9% better. This local weakness is reported rather than hidden, and is a natural target for a future lead-dependent blend.

### Task A aggregation choice

The administrator suggested hourly mean aggregation for Task A but did not make it mandatory. The frozen model predicts the EAGLE-I ratio at each exact hourly `target_time`; it does not average the preceding hour. This preserves a direct one-to-one relationship between each CSV row and its stated target timestamp. We have retained that choice so the code, frozen models and submitted predictions remain consistent.

## Why large raw caches are not included

The latest administrator clarification says that complete EAGLE-I files, weather archives and other large public sources do not need to be packaged when they can be reconstructed from the submitted code and source declaration. The repository therefore includes the compact frozen inference tables but not the 1.4 GB EAGLE-I source file or hundreds of raw API responses.

`SOURCES.md` records the exact releases, date ranges, variables, API endpoints, model/run restrictions and retrieval parameters. The acquisition and preprocessing modules rebuild the raw-to-feature pipeline when an audit from source is required.

## Full rebuild and retraining — audit route only

The following route downloads the public sources, rebuilds both feature sets, trains new models and exports a new CSV:

```powershell
.\.venv\Scripts\python.exe -m tech_arena phase1-run-all
```

Allow roughly 35–100 minutes for an uncached run, depending mainly on network and API response times. This route is provided for methodology review; it is **not** the command for reproducing the submitted file, because it deliberately retrains the models. Use `infer-phase1` for submission reproduction.

The older NaFIRS and topology code remains as an architecture-aware extension for later phases. It does not contribute to Phase 1 predictions, because Phase 1 is scored against EAGLE-I county data without topology coupling. `docs/TOPOLOGY_EXTENSION.md` explains the boundary between the scored path and this forward-looking work, including the site inputs that must be validated before operational use.

Some historic GitHub paths may appear as Git LFS pointer files when the public raw caches have not been fetched. They are not inputs to frozen Phase 1 inference. The submission ZIP excludes those pointer-only cache entries while retaining the acquisition code, source declarations and compact frozen inference artefacts.

The technical report is maintained and submitted separately, so its editable Word source is not stored in this repository.
