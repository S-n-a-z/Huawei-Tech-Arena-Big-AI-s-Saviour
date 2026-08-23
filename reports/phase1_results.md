# Phase 1 development results

## Data and split

The training period runs from 1 January to 31 August 2025. The first seven days supply the longest causal lag, so supervised rows begin on 8 January. Task A contains 56,160 rows from 234 daily issues; Task B contains 113,160 rows from 943 six-hourly issues. Model selection uses the last 20% of issue times as a chronological hold-out, with a purge equal to the task horizon.

The severe-event threshold is an outage ratio of 0.001. The validation event rate is 8.90% for Task A and 8.96% for Task B.

## Recorded validation

| Task | Selected blend MAE | Persistence MAE | Selected RMSE | Persistence RMSE | High-risk MAE | Event PR-AUC |
|---|---:|---:|---:|---:|---:|---:|
| A — 48 hours | 0.000430 | 0.000468 | 0.001215 | 0.001247 | 0.002149 | 0.2187 |
| B — 6 hours | 0.000371 | 0.000387 | 0.001080 | 0.001136 | 0.001571 | 0.4102 |

The selected persistence weights are 0.60 for Task A and 0.70 for Task B. Both selected blends improve MAE and RMSE over persistence on the same hold-out rows.

## Weather ablation

| Task | Full weather model MAE | History-only MAE | Full high-risk MAE | History-only high-risk MAE |
|---|---:|---:|---:|---:|
| A | 0.000465 | 0.000450 | 0.002107 | 0.002170 |
| B | 0.000420 | 0.000416 | 0.001509 | 0.001535 |

Weather improves high-risk error in both tasks and gives the clearest benefit for Task A. The small average-error trade-off in the unblended model is controlled by the validation-selected persistence blend. On that evidence, archived forecast weather remains in the final pipeline.

## Final prediction file

The export contains 65,880 rows: 22,080 for Task A and 43,800 for Task B. It includes 2,285 complete county/issue batches and passes the schema, range, duplicate, horizon and scoring-window coverage checks. The recorded SHA-256 checksum is `17b1fb4350967ced1cab1ff8ee7108e31a05573ab9a13d7aba0977803b100e04`.

