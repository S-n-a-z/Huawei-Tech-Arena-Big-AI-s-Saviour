# Validation record

This repository keeps the checks used for the recorded development run close to the code.

## Data and features

- Source links, licences and download checksums are recorded.
- Weather and outage features use information available at or before the issue time.
- The model uses the 31 districts with a supported SSEN operating-area match.
- NATS and NATSL remain in the audit trail and are not assigned invented coordinates.

## Model evidence

- Training and test rows are separated chronologically with a purge equal to the forecast horizon.
- Persistence is evaluated on the same held-out rows as the learned model.
- MAE, RMSE, high-risk error and rare-event ranking metrics are recorded for both tasks.
- Architecture calculations are controlled by the versioned values in `configs/default.toml`.

## Automated controls

- `python -m pytest` checks configuration, causal features, weather adaptation and export validation.
- `python -m tech_arena validate` checks columns, row keys, forecast leads, architectures and value ranges.
- Every reference CSV has a manifest containing its row count and SHA-256 checksum.
- GitHub Actions runs the complete test suite on pushes and pull requests.
