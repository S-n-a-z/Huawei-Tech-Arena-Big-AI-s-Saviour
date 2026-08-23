# Huawei Tech Arena 2026 — Topic Two, Phase 1

This repository contains our Phase 1 entry for the AI data-centre power-supply risk forecasting challenge. The submission predicts the proportion of customers without electricity (`predicted_x`) in five US counties for both required horizons:

- **Task A:** 48 hourly forecasts, issued once per calendar day;
- **Task B:** 24 forecasts at 15-minute intervals, covering the next six hours and issued every six hours.

The submitted county set is Los Angeles (California), Miami-Dade (Florida), Cook (Illinois), Harris (Texas) and King (Washington). It was fixed using January–August 2025 data only. The counties give broad customer coverage and expose the model to distinct tropical, convective, wind, winter, heat and wildfire-related weather regimes.

## What is currently available

- `outputs/predictions.csv.zip` contains the final `predictions.csv`, which follows the organiser's seven-column template exactly. Extract it before uploading to Agorize.
- It contains both tasks, all five counties and every complete rolling forecast batch.
- FIPS codes retain their leading zero and all times use ISO 8601 UTC.
- `predicted_x` is the customer outage ratio, clipped to `[0, 1]`.
- `outputs/predictions_manifest.json` records the row counts, validation result and SHA-256 checksum.
- Automated tests cover schedules, feature causality and submission validation.

The older UK NaFIRS and topology work remains in the codebase as Phase 2 research. It is not used by `predictions.csv`, because the Phase 1 administrator clarified that scoring uses EAGLE-I county FIPS codes and does not include topology coupling.

## Method in brief

The data preparation builds a complete 15-minute grid from EAGLE-I. The source omits zero-outage rows and cannot distinguish those omissions from collection gaps, so absent rows are set to zero while `record_present` is retained as a missingness feature. The denominator is the official county customer count supplied with the EAGLE-I release.

Each model uses only outage history available before its issue time. Features include current risk, 1/6/24/168-hour lags, causal rolling statistics, data coverage, calendar terms, lead time and ECMWF IFS weather. Historical IFS weather is used for training. Test-period weather comes from Open-Meteo's archived **Single Runs** endpoint, with the model initialisation fixed six hours before the issue time. This conservative delay prevents forecast-availability leakage.

Histogram gradient boosting estimates severe-event probability and outage magnitude. The final magnitude forecast is blended with persistence using a weight selected on a chronological hold-out period. Full validation figures and the weather ablation are in `reports/phase1_results.md`.

## Reproduce the entry

Python 3.12 is recommended. From Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m tech_arena phase1-run-all
.\.venv\Scripts\python.exe -m pytest --basetemp .test-tmp
.\.venv\Scripts\python.exe -m tech_arena validate-phase1
```

The first run downloads roughly 1.4 GB of EAGLE-I data and 366 archived forecast initialisations. On a normal broadband connection and laptop, allow about 15–30 minutes. Later runs reuse the local cache.

The same workflow can be run step by step:

```powershell
.\.venv\Scripts\python.exe -m tech_arena download-phase1-data
.\.venv\Scripts\python.exe -m tech_arena prepare-phase1-data
.\.venv\Scripts\python.exe -m tech_arena download-phase1-weather
.\.venv\Scripts\python.exe -m tech_arena build-phase1-features --purpose training
.\.venv\Scripts\python.exe -m tech_arena train-phase1
.\.venv\Scripts\python.exe -m tech_arena build-phase1-features --purpose test
.\.venv\Scripts\python.exe -m tech_arena export-phase1
.\.venv\Scripts\python.exe -m tech_arena validate-phase1
```

Raw data, cached API responses, feature tables and trained models are deliberately excluded from Git. Source links, licences, checksums and attribution are recorded in `SOURCES.md`.
