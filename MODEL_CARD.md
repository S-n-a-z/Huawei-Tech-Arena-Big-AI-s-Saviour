# Phase 1 model card

## Intended use

The model forecasts county-level electricity outage ratios for the two Phase 1 horizons in the Huawei Tech Arena 2026 Topic Two challenge. It is a competition prototype, not a control, dispatch or safety system.

## Inputs and outputs

Inputs are 15-minute EAGLE-I outage history, county customer counts, causal lag and rolling features, calendar terms and ECMWF IFS weather. The output is `predicted_x`, the estimated proportion of customers without electricity in a county. Predictions are limited to `[0, 1]`.

The five selected counties are Los Angeles, Miami-Dade, Cook, Harris and King. Selection used only the January–August 2025 period and was based on customer coverage, source-record coverage, event exposure and geographic diversity.

## Forecast availability

Training weather comes from Open-Meteo's historical ECMWF IFS series. Test features use the archived Single Runs API. Each forecast run is initialised six hours before its issue time, which is a conservative allowance for the stated four-to-six-hour ECMWF publication delay. Continuous weather variables are linearly interpolated to 15-minute targets; the hourly precipitation value is carried within its hour.

For Task A, the target is the EAGLE-I ratio at each exact hourly target timestamp. The administrator described hourly mean aggregation as a suggestion rather than a fixed Phase 1 rule. We retained point targets so that every prediction maps directly to its stated `target_time`, and we did not alter the frozen model after generating the submitted CSV.

## Model and validation

Separate histogram gradient-boosting models are fitted for Tasks A and B. A balanced classifier estimates the probability of an outage ratio of at least 0.001. A weighted regressor estimates the transformed outage ratio, giving six times the weight to severe rows. The magnitude estimate is blended with current-risk persistence. The blend is chosen on a chronological 20% hold-out, separated from training by the maximum forecast horizon, and the final model is then refitted on all pre-test data.

The recorded hold-out MAE is 0.000430 for Task A and 0.000371 for Task B. Both improve on persistence (0.000468 and 0.000387 respectively). Weather improves high-risk error in both tasks; the full comparison, including the small unblended average-error trade-off, is in `reports/phase1_results.md`.

## Explainability and error slices

`python -m tech_arena diagnose-phase1` recreates the committed lead-time and county error summaries from the recorded hold-out predictions. Task A improves on persistence in all four lead bands, from 4.7% at 13–24 hours to 13.7% at 1–12 hours. It also improves in every county, although Cook County has the smallest margin (0.6%).

Task B improves in every county and in the three lead bands from 105 minutes to six hours. At 15–90 minutes the selected global blend is 2.9% worse than persistence. This is a known local limitation: a lead-dependent blend may improve it, but it has not been substituted into the frozen submission without a complete retraining and validation run. Detailed figures are stored in `reports/phase1_diagnostics.json`; row-level absolute errors are in `artifacts/phase1/*/validation_diagnostics.csv.gz`.

## Architecture-aware extension

The retained topology module is a deliberately separate research layer. It can translate a regional outage forecast into site-level indicators once a team supplies reviewed architecture parameters, including critical load, usable stored energy, generator endurance, redundancy and transfer behaviour. The present defaults are illustrative engineering baselines, not measured data-centre configurations. They do not affect `outputs/predictions.csv` and must not be used for operational decisions without site-specific calibration. The interface and validation gates are documented in `docs/TOPOLOGY_EXTENSION.md` and `configs/site_architecture.schema.json`.

## Frozen inference record

The exact Task A and Task B estimators are stored in `artifacts/phase1`. Each serialised `Phase1Forecaster` contains its fitted imputer, ordinal county encoder, gradient-boosting classifier, gradient-boosting regressor, selected feature columns and persistence weight. No separate preprocessing object is required.

The two compressed tables in `data/processed/phase1_*_test.csv.gz` are the exact engineered inputs used for the submission. They freeze the historical outage state and archived ECMWF IFS forecast values, so the submitted CSV can be reproduced without an external API call. `artifacts/phase1/inference_manifest.json` verifies all four files before inference. The command `python -m tech_arena infer-phase1` loads these artefacts without retraining and checks that the generated CSV matches the submitted file exactly.

## Limitations

- EAGLE-I omits zero-outage rows and does not distinguish them from collection gaps. The pipeline follows the release convention by zero-filling, but retains a source-record coverage feature and audit.
- The denominator is the 2022 county customer count distributed with EAGLE-I. It is declared rather than presented as a current customer census.
- Training weather is a historical IFS proxy, whereas test weather is reconstructed from individual forecast initialisations.
- The county set is deliberately small and should not be treated as a nationally calibrated model.
- The topology and data-centre backup-power calculations are outside Phase 1 scoring and are not applied to `predictions.csv`.
- The selected Task B blend does not beat persistence in the shortest 15–90-minute diagnostic band, even though it improves overall hold-out MAE.

## Responsible use

Do not use these predictions to operate live electrical equipment or to make safety-critical decisions. Operational use would require current utility data, calibration monitoring, site-specific engineering review and formal validation.
