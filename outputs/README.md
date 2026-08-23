# Phase 1 prediction output

`predictions.csv` is the single combined prediction file for submission. Its columns match the organiser's template exactly:

`task_id,fips_code,county,state,issue_time,target_time,predicted_x`

The validated file contains 65,880 rows: 22,080 for Task A and 43,800 for Task B. It covers five counties, 92 daily Task A issues and 365 six-hourly Task B issues. Every county/issue batch contains the complete required horizon.

`predictions_manifest.json` records the validation summary and SHA-256 checksum. Re-run `python -m tech_arena validate-phase1` after any change to the CSV.

The earlier SSEN/topology exports are Phase 2 development artefacts and are not part of the Phase 1 submission.

