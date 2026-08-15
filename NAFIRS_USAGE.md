# Quick NaFIRS Usage Guide

## Run in Python Terminal

```python
# Import the module
from nafirs import NaFIRSLoader, NaFIRSProcessor, NaFIRSFeatureEngine

# Load the data
loader = NaFIRSLoader()
incidents = loader.load()
print(f"Loaded {len(incidents)} incidents")
print(f"Networks: {incidents['NETWORK'].unique()}")

# Process the data
processor = NaFIRSProcessor(incidents)

# Get daily regional outage proportion (% of districts with faults)
regional_daily = processor.regional_outage_proportion("D")
print(regional_daily.head())

# Get hourly aggregation
hourly_agg = processor.aggregate_by_district_time("H")
print(hourly_agg.head())

# Extract features for modeling
engine = NaFIRSFeatureEngine(processor)
district_features = engine.create_district_features(lookback_days=365)
print(f"District features: {len(district_features)} districts")
print(district_features.head())
```

## Or: Run a Simple Script

```bash
python -c "
from nafirs import NaFIRSLoader, NaFIRSProcessor

loader = NaFIRSLoader()
incidents = loader.load()
processor = NaFIRSProcessor(incidents)
regional = processor.regional_outage_proportion('D')
print(f'Regional outage proportion (daily):')
print(regional.head(10))
"
```

## Key Outputs

**Regional Outage Proportion** (input to risk models):
```
NETWORK  TIME_PERIOD  OUTAGE_PROPORTION
SEPD     2024-01-01   0.032  (3.2% of districts)
SEPD     2024-01-02   0.065  (6.5% of districts)
```

**District Features** (vulnerability metrics):
```
NETWORK  DISTRICT_ID  FAULT_COUNT  CUSTOMERS_AFFECTED  OUTAGE_DURATION_MIN
SHEPD    HIGH         1399         25000               248.5
SHEPD    TAYCEN       1206         18000               267.3
```

## One-Liner Usage

```python
from nafirs import load_and_process_nafirs
result = load_and_process_nafirs()
# Access: result["incidents"], result["processor"], result["regional_outage_proportion"], result["district_features"]
```
