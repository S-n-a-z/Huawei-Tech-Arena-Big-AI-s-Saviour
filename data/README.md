# Data policy

Third-party data are downloaded locally and are not committed.

- `raw/` holds the original EAGLE-I files, Gazetteer download and cached Open-Meteo responses.
- `interim/` holds the dense fifteen-minute outage grid and normalised weather tables.
- `processed/` holds supervised feature tables and audit summaries.

Run `python -m tech_arena download-phase1-data` to acquire the EAGLE-I outage file, the accompanying county customer counts and the US Census Gazetteer. The downloader verifies both EAGLE-I checksums. Run `python -m tech_arena download-phase1-weather` to acquire the training weather and the archived forecast initialisations used in the test simulation.

EAGLE-I and Open-Meteo data are CC BY 4.0. Full links, licence notes and attribution are in `SOURCES.md`.

The older NaFIRS, SSEN and OpenStreetMap adapters are retained for Phase 2 research. They are not part of the Phase 1 data path.

