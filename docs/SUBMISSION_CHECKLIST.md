# Phase 1 submission record

## Required deliverables

- [x] A 3–8 page technical report has been prepared locally in Word.
- [x] A combined `predictions.csv` contains Tasks A and B.
- [x] Complete source code and a reproducibility guide are present in the repository.
- [x] All data sources and licences are declared in `SOURCES.md` and in the report.

## Prediction checks

- [x] The column order is identical to the organiser's template.
- [x] Five EAGLE-I counties are used and justified without test-period selection leakage.
- [x] FIPS codes are five-character strings, including `06037`.
- [x] Task A has 48 hourly targets in every county/issue batch.
- [x] Task B has 24 fifteen-minute targets in every county/issue batch.
- [x] Rolling issues cover every scoring timestamp from 1 September to 30 November 2025 UTC.
- [x] All times are ISO 8601 UTC and all predictions are finite values in `[0, 1]`.
- [x] The file has no duplicate forecast keys or missing values.
- [x] The generated file contains 65,880 rows and passes `validate-phase1`.

## Leakage and reproducibility checks

- [x] Outage history ends 15 minutes before each issue time.
- [x] The model-selection split is chronological and purged by the task horizon.
- [x] Test weather uses individual ECMWF IFS forecast runs initialised six hours before issue time.
- [x] The EAGLE-I source checksums are verified before preparation.
- [x] Random seeds, county coordinates, customer denominators and forecast schedules are versioned.
- [x] Raw data, API caches, trained artefacts and the local Word report are excluded from Git.

The final upload should contain the report PDF, `predictions.csv`, and the repository source/reproducibility material. Do not substitute either of the older UK/topology output files.

