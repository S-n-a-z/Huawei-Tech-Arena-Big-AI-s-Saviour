# Topic Two development results

> Status: reproducible engineering baseline. Architecture calculations use the
> versioned configuration recorded in `configs/default.toml`.

## Data snapshot

- Normalized NaFIRS incidents: 220,715
- Time range: 2015-04-01 01:15:00+00:00 to 2026-08-04 01:36:00+00:00
- Districts: 33
- Spatially matched districts used by the model: 31
- Excluded from spatial modelling: SEPD NATS and NATSL (no supported operating-area match)
- Networks: {'SEPD': 179591, 'SHEPD': 41124}
- Planned fraction: 0.000%

## Validation

Validation is chronological and purged by the maximum task horizon. Metrics below
are chronological hold-out diagnostics on the sampled modelling table.

| Task | Train rows | Test rows | MAE | RMSE | High-risk MAE | PR-AUC | Event recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Day Ahead | 710,508 | 179,836 | 0.02871 | 0.07604 | 0.12976 | 0.30313 | 0.44450 |
| Hour Ahead | 540,383 | 127,785 | 0.02943 | 0.07908 | 0.13326 | 0.63017 | 0.73844 |

## Persistence ablation

| Task | Persistence MAE | Hurdle MAE | MAE change | Persistence RMSE | Hurdle RMSE | Persistence PR-AUC | Hurdle PR-AUC |
|---|---:|---:|---:|---:|---:|---:|---:|
| Day Ahead | 0.03457 | 0.02871 | -16.95% | 0.11388 | 0.07604 | 0.18897 | 0.30313 |
| Hour Ahead | 0.02636 | 0.02943 | +11.66% | 0.09827 | 0.07908 | 0.42455 | 0.63017 |

The day-ahead model improves both average error and rare-event discrimination.
For hour-ahead prediction it improves RMSE and PR-AUC but gives up some MAE to
persistence. This metric trade-off is retained in the recorded evidence rather
than hidden behind a single summary value.

## Implemented ablation path

1. Current-risk persistence is blended into every forecast.
2. The hurdle model adds causal risk lags and weather variables.
3. The deterministic topology layer maps regional predictions to site risk.
4. OSM network features can be enabled and evaluated separately.

## Known limitations

- Regional outage proportion uses a documented train-data exposure proxy because
  total customers per district are not present in the NaFIRS resource.
- District weather coordinates are median SSEN substation locations, not asserted
  AIDC site locations.
- NaFIRS incident duration and customers affected are used only to construct labels;
  post-event cause and duration fields are not forecasting inputs.
- Architecture calculations use versioned engineering assumptions and are not
  a substitute for site-specific protection studies or equipment certification.
- Output CSVs are latest-window reference exports from the recorded model run.
