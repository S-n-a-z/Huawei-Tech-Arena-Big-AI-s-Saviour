# Huawei Tech Arena Topic Two — location data

This repo holds the work for our Topic Two model.

## Included files

- `locations.py` downloads the official SSEN substation source, removes repeated physical locations and converts British National Grid coordinates to WGS84 latitude/longitude.
- `ssen_individual_substation_coordinates.csv` contains 124,950 unique locations. `source_record_count` shows how many original records shared each physical point.
- `district_locations.csv` contains the 31 district representatives that could be matched to an SSEN operating area.
- `excluded_unmatched_districts.csv` records NATS and NATSL as excluded because there is no supported operating-area match. We do not assign them the median of the whole network.
- `LOCATION_SETUP.md` has the commands needed to reproduce the files.

The 6 km value in the district file is a working midpoint within Huawei's stated 3–9 km weather radius. It is not a prescribed value. The individual substation CSV contains point coordinates and does not use that radius.
