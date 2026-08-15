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

