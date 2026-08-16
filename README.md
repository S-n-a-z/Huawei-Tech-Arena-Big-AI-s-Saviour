# Huawei Tech Arena Topic Two — location data

This repo holds the work for our Topic Two model.

## Included files

- `locations.py` downloads the official SSEN substation source, removes repeated physical locations and converts British National Grid coordinates to WGS84 latitude/longitude.
- `ssen_individual_substation_coordinates.csv` contains 124,950 unique locations. `source_record_count` shows how many original records shared each physical point.
- `district_locations.csv` contains the 31 district representatives that could be matched to an SSEN operating area.
- `excluded_unmatched_districts.csv` records NATS and NATSL as excluded because there is no supported operating-area match. We do not assign them the median of the whole network.
- `LOCATION_SETUP.md` has the commands needed to reproduce the files.
- `plot_district_substation_map.py` creates an interactive map of the district representative points and substations.

The 6 km value in the district file is a working midpoint within Huawei's stated 3–9 km weather radius. It is not a prescribed value. The individual substation CSV contains point coordinates and does not use that radius.

## Interactive map

`plot_district_substation_map.py` creates an interactive map of district representative points and substations.

```bash
python -m pip install -r requirements.txt
python plot_district_substation_map.py
```
When `Map saved to district_substation_map.html` appears in the terminal, open `district_substation_map.html` in a browser.

Hover over a district to highlight its associated substations. The 3/6/9 km radius layers can also be switched on and off.

## NaFIRS LV Faults

`python -c "from nafirs import NaFIRSLoader; loader = NaFIRSLoader(); incidents = loader.load(); print(f'Loaded {len(incidents)} incidents'); print(incidents.head())"` Load and explore data:

`python -c "from nafirs import NaFIRSLoader, NaFIRSProcessor; loader = NaFIRSLoader(); processor = NaFIRSProcessor(loader.load()); print(processor.regional_outage_proportion('D').head())"` Get regional outage proportion

`python -c "from nafirs import NaFIRSLoader, NaFIRSProcessor, NaFIRSFeatureEngine; loader = NaFIRSLoader(); processor = NaFIRSProcessor(loader.load()); engine = NaFIRSFeatureEngine(processor); print(engine.create_district_features().head())"` Extract district features:

## Weather Data

The weather pipeline converts Open-Meteo weather data into hourly district-level weather data for the 31 supported SEPD and SHEPD districts. Each district uses 17 spatial sampling locations within the selected 9 km sampling scheme. Sampling locations are mapped to the actual Open-Meteo weather grids, shared grids are downloaded only once, and the grid values are aggregated back to district level.

- `data/processed/district_weather_hourly.csv.gz` is the main weather dataset for downstream use. It contains 3,092,064 district-hour records, 34 columns, 31 districts, and hourly data from `2015-03-28 00:00:00` to `2026-08-12 23:00:00` UTC. There are no duplicate district-hours or missing values.

- `data/processed/district_weather_hourly_yearly/` contains the same district-level weather data split into yearly compressed CSV files from 2015 to 2026 for easier loading.

- `district_weather_grid_mapping.csv` records how the 17 sampling locations for each district map to the actual Open-Meteo weather grids used for district aggregation.

- `weather_unique_grids.csv` contains the 159 unique Open-Meteo grids used by all districts after shared grids are deduplicated.

- `data/raw/weather_grids/` contains the downloaded hourly weather data for the 159 unique Open-Meteo grids.

- `data/processed/weather_validation/` contains district-level quality-control reports covering row counts, spatial metadata, physical sanity checks, variable distributions, spatial spread, and extreme weather observations.

- `data/raw/weather_grid_validation_report.csv` contains the raw-grid validation results. All 159 grids passed validation with no duplicate timestamps, missing hours, missing values, or coordinate errors.

- `build_district_weather_hourly.py` builds the final district-level hourly weather dataset from the downloaded grid data and the district-to-grid mapping.

- `validate_weather_grids.py` validates the raw Open-Meteo grid data for completeness, hourly continuity, duplicate timestamps, missing values, and coordinate consistency.

- `validate_district_weather.py` validates the final district-level weather dataset for structural consistency and basic physical sanity.

The main dataset includes temperature, relative humidity, dew point, precipitation, rain, snowfall, snow depth, soil moisture, wind speed, wind gusts, surface pressure, wind direction, weather code, and spatial sampling metadata. Continuous weather variables are represented using appropriate district-level spatial statistics such as mean, minimum, and maximum.

For downstream work, use `data/processed/district_weather_hourly.csv.gz` as the primary weather input. 

The compressed weather datasets are stored with Git LFS because of their file size. Install Git LFS before cloning or pulling the repository (`git lfs install`) so the full weather data files are downloaded correctly.

