# Submission checklist

Use this checklist after the organising committee supplies the assessment inputs.

## Inputs

- [ ] Replace every illustrative topology value in `configs/default.toml`.
- [ ] Confirm the site, district and timestamp identifiers against the official test file.
- [ ] Confirm whether forecast weather is available at the issue time.
- [ ] Record the final source versions, licences and checksums.

## Pipeline

- [ ] Run both forecast tasks from a clean environment.
- [ ] Check that no feature uses information published after the issue time.
- [ ] Review chronological, district and extreme-event validation.
- [ ] Compare the selected model with persistence and the reported ablations.
- [ ] Run `python -m pytest` and `python -m tech_arena validate`.

## Deliverables

- [ ] Adapt the exporter to the official sample CSV exactly.
- [ ] Check row order, column names, units, timestamps and decimal formatting.
- [ ] Check for missing values, duplicates and out-of-range probabilities.
- [ ] Update the Word report with the final parameter table and scored result.
- [ ] Include the complete codebase and fresh-start instructions.
- [ ] Open each uploaded deliverable once from the competition portal before submitting.
