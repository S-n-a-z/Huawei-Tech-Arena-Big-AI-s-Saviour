# Running the location code

Use Python 3.11 or newer. From the repository folder:

```bash
python -m venv .venv
```

Activate the environment, then install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Download the current SSEN source and rebuild the individual-coordinate file:

```bash
python locations.py export-substations
```

If you already have the SSEN CSV, you can avoid downloading it again:

```bash
python locations.py export-substations --source path/to/substations.csv
```

The output is `ssen_individual_substation_coordinates.csv` in the repository folder. It is deduplicated by network, easting and northing. The original source rows are not thrown away silently: their count is kept in `source_record_count`.

District representatives need the normalized NaFIRS incident file as well:

```bash
python locations.py prepare-locations --incidents path/to/nafirs_incidents.csv.gz
```

That command also writes `excluded_unmatched_districts.csv`. At the moment NATS and NATSL are excluded because we do not have a defensible SSEN operating-area match for them.
