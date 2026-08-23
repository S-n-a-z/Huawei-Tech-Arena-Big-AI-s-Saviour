# Working together

Please keep changes small enough to review and explain the reason for them in the commit message. Phase 1 code lives under `src/tech_arena/phase1/`; the older UK outage and topology modules are retained separately for later work.

Before opening a pull request:

1. Run `python -m pytest --basetemp .test-tmp`.
2. If modelling code changed, rebuild the affected task and record the new chronological validation result in `reports/phase1_results.md`.
3. Run `python -m tech_arena validate-phase1` after exporting predictions.
4. Confirm that `outputs/predictions_manifest.json` contains the new checksum.
5. Update the local technical report if a metric, data source, assumption or limitation changed.
6. Do not commit raw downloads, cached API responses, trained models, credentials or the Word/PDF report.

Cite source licences, and never describe a development metric as an organiser leaderboard score.

