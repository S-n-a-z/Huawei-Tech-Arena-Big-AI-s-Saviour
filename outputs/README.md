# Prediction outputs

The two generated CSV files are validated latest-window reference exports from the forecasting and resilience pipeline.

Columns:

- `issue_time`, `target_time`: UTC ISO-8601 timestamps.
- `network`, `district_id`: SSEN region identifiers.
- `lead_minutes`: forecast lead time.
- `architecture_id`, `architecture_name`: one of the four supplied architecture classes.
- `regional_risk_prediction`: learned regional outage-proportion forecast.
- `site_risk_score`: topology-dependent sigmoid transformation.
- `critical_load_coverage_ratio`: configuration-driven engineering result in `[0,1]`.
- `estimated_backup_duration_hours`: configuration-driven backup-duration estimate.

Each export is checked for complete district, lead and architecture coverage, duplicate keys, finite values and valid probability ranges. The accompanying manifest records its row count, configuration status and SHA-256 checksum.

`ssen_individual_substation_coordinates.csv` contains one row per unique SSEN physical coordinate. Coordinates are transformed from EPSG:27700 to WGS84; repeated source records are represented by `source_record_count`.
