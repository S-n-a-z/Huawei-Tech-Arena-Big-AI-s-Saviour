# Model card

## Intended use

The package estimates district-level electricity outage risk for the two Topic Two forecast horizons and applies configurable data-centre power architectures. It is a competition model and engineering decision aid, not an operational protection system.

## Model design

Each forecast task uses a two-stage histogram gradient-boosting model. The classifier estimates the chance of an outage event and the regressor estimates its severity. Their product is blended with current-risk persistence. The same model is shared across districts, with district, network, lead time, weather, seasonal and lagged-risk features supplied explicitly.

## Validation

Rows are split chronologically. The maximum forecast horizon is purged between training and test periods so that overlapping labels do not cross the boundary. Development metrics include MAE, RMSE, high-risk MAE, PR-AUC, ROC-AUC, Brier score, precision, recall and F1. Persistence is reported separately.

## Main limitations

- NaFIRS does not include total customers served by district, so severity uses a documented exposure proxy.
- Hour-ahead weather is based on the latest available hourly observation and is forward-filled to five-minute steps.
- District coordinates represent SSEN operating areas rather than confirmed data-centre sites.
- The committed topology coefficients are illustrative until the assessed configuration is supplied.
- Validation covers SSEN licence areas and should not be read as evidence of performance in other countries or network operators.

## Responsible use

Do not use the output to switch, isolate or dispatch live electrical equipment. A qualified engineer should review the final topology parameters, protection equations and any operational interpretation.
