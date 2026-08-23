# Phase 1 model card

## Intended use

The model forecasts county-level electricity outage ratios for the two Phase 1 horizons in the Huawei Tech Arena 2026 Topic Two challenge. It is a competition prototype, not a control, dispatch or safety system.

## Inputs and outputs

Inputs are 15-minute EAGLE-I outage history, county customer counts, causal lag and rolling features, calendar terms and ECMWF IFS weather. The output is `predicted_x`, the estimated proportion of customers without electricity in a county. Predictions are limited to `[0, 1]`.

The five selected counties are Los Angeles, Miami-Dade, Cook, Harris and King. Selection used only the January–August 2025 period and was based on customer coverage, source-record coverage, event exposure and geographic diversity.

## Forecast availability

Training weather comes from Open-Meteo's historical ECMWF IFS series. Test features use the archived Single Runs API. Each forecast run is initialised six hours before its issue time, which is a conservative allowance for the stated four-to-six-hour ECMWF publication delay. Continuous weather variables are linearly interpolated to 15-minute targets; the hourly precipitation value is carried within its hour.

## Model and validation

Separate histogram gradient-boosting models are fitted for Tasks A and B. A balanced classifier estimates the probability of an outage ratio of at least 0.001. A weighted regressor estimates the transformed outage ratio, giving six times the weight to severe rows. The magnitude estimate is blended with current-risk persistence. The blend is chosen on a chronological 20% hold-out, separated from training by the maximum forecast horizon, and the final model is then refitted on all pre-test data.

The recorded hold-out MAE is 0.000430 for Task A and 0.000371 for Task B. Both improve on persistence (0.000468 and 0.000387 respectively). Weather improves high-risk error in both tasks; the full comparison, including the small unblended average-error trade-off, is in `reports/phase1_results.md`.

## Limitations

- EAGLE-I omits zero-outage rows and does not distinguish them from collection gaps. The pipeline follows the release convention by zero-filling, but retains a source-record coverage feature and audit.
- The denominator is the 2022 county customer count distributed with EAGLE-I. It is declared rather than presented as a current customer census.
- Training weather is a historical IFS proxy, whereas test weather is reconstructed from individual forecast initialisations.
- The county set is deliberately small and should not be treated as a nationally calibrated model.
- The topology and data-centre backup-power calculations are outside Phase 1 scoring and are not applied to `predictions.csv`.

## Responsible use

Do not use these predictions to operate live electrical equipment or to make safety-critical decisions. Operational use would require current utility data, calibration monitoring, site-specific engineering review and formal validation.
