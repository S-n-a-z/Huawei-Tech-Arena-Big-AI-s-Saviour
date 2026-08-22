# Prediction outputs

The two generated CSV files are compact latest-window inference demonstrations. They are not claimed to match the unpublished official sample-submission schema.

Columns:

- `issue_time`, `target_time`: UTC ISO-8601 timestamps.
- `network`, `district_id`: SSEN region identifiers.
- `lead_minutes`: forecast lead time.
- `architecture_id`, `architecture_name`: one of the four supplied architecture classes.
- `regional_risk_prediction`: learned regional outage-proportion forecast.
- `site_risk_score`: topology-dependent sigmoid transformation.
- `critical_load_coverage_ratio`: placeholder rule-engine result in `[0,1]`.
- `estimated_backup_duration_hours`: placeholder rule-engine result.

Before submission, replace the topology parameters in `configs/default.toml` and adjust `export_submission` to the organiser's exact columns, units, row ordering, and designated test window.

`ssen_individual_substation_coordinates.csv` contains one row per unique SSEN physical coordinate. Coordinates are transformed from EPSG:27700 to WGS84; repeated source records are represented by `source_record_count`.
