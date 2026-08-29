# Data sources, licences and attribution

| Source | Use in Phase 1 | Licence / terms | Access |
|---|---|---|---|
| EAGLE-I Power Outage Data 2025 | Fifteen-minute county outage counts and labels | CC BY 4.0 | https://doi.ccs.ornl.gov/dataset/c09fce3f-5faa-54ef-878a-cb0af6851cb6 |
| EAGLE-I recorded outages 2014–2025, Figshare v4 | Download mirror and accompanying county customer-count file | CC BY 4.0 | https://doi.org/10.6084/m9.figshare.24237376.v4 |
| Open-Meteo Historical Weather API | ECMWF IFS training-weather proxy | API data CC BY 4.0; attribution required | https://open-meteo.com/en/docs/historical-weather-api |
| Open-Meteo Single Runs API | Archived ECMWF IFS forecasts available at issue time | API data CC BY 4.0; attribution required | https://open-meteo.com/en/docs/single-runs-api |
| ECMWF Open Data | Underlying IFS forecast fields | CC BY 4.0 | https://www.ecmwf.int/en/forecasts/datasets/open-data |
| US Census Bureau 2025 Gazetteer Files | Independent county names and centroid checks | US Government work; public domain | https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html |
| Huawei Tech Arena Phase 1 guidelines and administrator FAQs | Tasks, dates, schema and scoring interpretation | Competition material; supplied to participants | https://huawei.agorize.com/en/challenges/2026-nuremberg-tech-arena-digital-power/pages/topic-2?lang=en |

The EAGLE-I files used in the recorded run have these MD5 checksums:

- `eaglei_outages_2025.csv`: `cd2feb1282a42fb048cb6885398bc1cc`
- `MCC.csv`: `7e30d47d44cae46b3342cdabf7c84b7f`

Suggested citations are V. Tansakul *et al.*, “EAGLE-I Power Outage Data 2025,” Oak Ridge National Laboratory, 2026, doi: 10.13139/ORNLNCCS/3012826; S. Tansakul *et al.*, “A dataset of recorded electricity outages by United States county 2014–2022,” *Scientific Data*, vol. 11, art. 271, 2024, doi: 10.1038/s41597-024-03095-5; and P. Zippenfenig, “Open-Meteo.com Weather API,” Zenodo, 2023, doi: 10.5281/zenodo.7970649.

SSEN NaFIRS, SSEN substation data and OpenStreetMap appear only in the retained architecture-aware research code. They do not contribute to the Phase 1 predictions. Their provenance is recorded because the repository deliberately goes beyond the minimum Phase 1 path:

| Extension source | Intended research use | Licence / terms | Access |
|---|---|---|---|
| SSEN Distribution NaFIRS LV Faults | Planned and unplanned low-voltage fault history for later regional modelling | CC BY 4.0 | https://data.ssen.co.uk/@ssen-distribution/nafirs-lv-faults |
| SSEN Distribution Substation Data | Network-area locations and asset context for later spatial coupling | CC BY 4.0 | https://data.ssen.co.uk/@ssen-distribution/ssen-substation-data |
| OpenStreetMap contributors | Optional power-line and substation context | ODbL 1.0; attribution required | https://www.openstreetmap.org/copyright |

These extension datasets were not transferred into the scored US model. The different geography and label definitions prevent them from being treated as direct Phase 1 training observations.

## Recorded Phase 1 retrieval specification

The submitted run used the following fixed inputs and parameters:

- **EAGLE-I outage history:** `eaglei_outages_2025.csv`, downloaded from Figshare file `62164877`. Training labels end at 31 August 2025 23:45 UTC. The dense history used for causal features runs from 1 January to 30 November 2025 at 15-minute intervals.
- **County denominators:** `MCC.csv`, Figshare file `42547708`. The configured FIPS codes are `06037`, `12086`, `17031`, `48201` and `53033`.
- **Training weather:** Open-Meteo Historical Weather API, `https://archive-api.open-meteo.com/v1/archive`, from 1 January to 31 August 2025, model `ecmwf_ifs`, timezone `GMT`.
- **Inference weather:** Open-Meteo Single Runs API, `https://single-runs-api.open-meteo.com/v1/forecast`, model `ecmwf_ifs`, timezone `GMT`, `forecast_hours=60`. Required run initialisations span 31 August 2025 00:00 UTC to 30 November 2025 12:00 UTC. For every forecast issue, the selected model run is exactly six hours earlier.
- **Weather variables:** `temperature_2m`, `relative_humidity_2m`, `precipitation`, `surface_pressure`, `wind_speed_10m` and `wind_gusts_10m` at the five county coordinates recorded in `configs/default.toml`.
- **Test window:** target timestamps from 1 September through 30 November 2025 UTC. Task A uses 48 one-hour leads; Task B uses 24 fifteen-minute leads.

Large public raw files and individual API-response caches are omitted from the repository. The exact engineered inference tables are included because they are compact, remove dependence on mutable external APIs and correspond directly to the frozen submitted models.
