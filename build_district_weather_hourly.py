from pathlib import Path
import math
import numpy as np
import pandas as pd

# Configuration
GRID_FILE = Path("weather_unique_grids.csv")

MAPPING_FILE = Path(
    "district_weather_grid_mapping.csv"
)

RAW_GRID_ROOT = Path(
    "data/raw/weather_grids"
)

OUTPUT_DIR = Path(
    "data/processed/district_weather_hourly_yearly"
)

FINAL_OUTPUT = Path(
    "data/processed/district_weather_hourly.csv.gz"
)

YEARS = list(
    range(2015, 2027)
)

# Variable groups
MEAN_MIN_MAX_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
]

MEAN_MAX_VARIABLES = [
    "precipitation",
    "rain",
    "snowfall",
    "snow_depth",
    "soil_moisture_0_to_7cm",
    "wind_speed_10m",
    "wind_gusts_10m",
]

MEAN_MIN_VARIABLES = [
    "surface_pressure",
]

# Weighted mode helper
def weighted_mode(
    values,
    weights,
):
    weighted_counts = {}

    for value, weight in zip(
        values,
        weights,
    ):

        weighted_counts[value] = (
            weighted_counts.get(
                value,
                0.0,
            )
            + weight
        )

    return max(
        weighted_counts,
        key=weighted_counts.get,
    )

# Load and prepare mapping
def load_mapping():

    mapping = pd.read_csv(
        MAPPING_FILE
    )

    required_columns = {
        "network",
        "district_id",
        "grid_id",
        "district_grid_weight",
    }

    missing = (
        required_columns
        - set(mapping.columns)
    )

    if missing:

        raise ValueError(
            "Mapping file is missing columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    # One row per District × Grid

    # district_weather_grid_mapping.csv contains all 17
    # original sampling locations, so the same grid may appear
    # several times for one district.
    
    # district_grid_weight already stores the weight represented
    # by that grid, so we keep one unique District × Grid row.
    mapping_unique = (
        mapping[
            [
                "network",
                "district_id",
                "grid_id",
                "district_grid_weight",
            ]
        ]
        .drop_duplicates(
            subset=[
                "network",
                "district_id",
                "grid_id",
            ]
        )
        .copy()
    )

    # Metadata
    grid_counts = (
        mapping_unique
        .groupby(
            [
                "network",
                "district_id",
            ]
        )["grid_id"]
        .nunique()
        .rename(
            "weather_grid_count"
        )
        .reset_index()
    )

    sampling_counts = (
        mapping
        .groupby(
            [
                "network",
                "district_id",
            ]
        )
        .size()
        .rename(
            "weather_sampling_point_count"
        )
        .reset_index()
    )

    metadata = grid_counts.merge(
        sampling_counts,
        on=[
            "network",
            "district_id",
        ],
        how="inner",
        validate="one_to_one",
    )

    return (
        mapping_unique,
        metadata,
    )

# Read one year from all required grids
def load_grid_year(
    year,
    grid_ids,
):

    frames = []

    for grid_id in grid_ids:

        file = (
            RAW_GRID_ROOT
            / grid_id
            / f"{year}.csv.gz"
        )

        if not file.exists():

            raise FileNotFoundError(
                f"Missing weather file: "
                f"{file}"
            )

        frame = pd.read_csv(
            file,
            parse_dates=["time_utc"],
        )

        # Keep only columns needed downstream
        frame = frame[
            [
                "grid_id",
                "time_utc",
                "temperature_2m",
                "relative_humidity_2m",
                "dew_point_2m",
                "precipitation",
                "rain",
                "snowfall",
                "snow_depth",
                "weather_code",
                "surface_pressure",
                "soil_moisture_0_to_7cm",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
            ]
        ]

        frames.append(
            frame
        )

    return pd.concat(
        frames,
        ignore_index=True,
    )

# Aggregate one District for one year
def aggregate_district(
    district_weather,
):

    # Weighted continuous means
    for variable in (
        MEAN_MIN_MAX_VARIABLES
        + MEAN_MAX_VARIABLES
        + MEAN_MIN_VARIABLES
    ):

        district_weather[
            f"weighted_{variable}"
        ] = (
            district_weather[variable]
            *
            district_weather[
                "district_grid_weight"
            ]
        )

    # Wind direction: weighted circular mean
    radians = np.deg2rad(
        district_weather[
            "wind_direction_10m"
        ]
    )

    district_weather[
        "wind_direction_sin_weighted"
    ] = (
        np.sin(radians)
        *
        district_weather[
            "district_grid_weight"
        ]
    )

    district_weather[
        "wind_direction_cos_weighted"
    ] = (
        np.cos(radians)
        *
        district_weather[
            "district_grid_weight"
        ]
    )

    # Group by hour
    grouped = (
        district_weather
        .groupby(
            "time_utc",
            sort=True,
        )
    )

    output = pd.DataFrame(
        index=grouped.size().index
    )

    # Mean / min / max variables
    for variable in (
        MEAN_MIN_MAX_VARIABLES
    ):

        output[
            f"{variable}_mean"
        ] = grouped[
            f"weighted_{variable}"
        ].sum()

        output[
            f"{variable}_min"
        ] = grouped[
            variable
        ].min()

        output[
            f"{variable}_max"
        ] = grouped[
            variable
        ].max()

    # Mean / max variables
    for variable in (
        MEAN_MAX_VARIABLES
    ):

        output[
            f"{variable}_mean"
        ] = grouped[
            f"weighted_{variable}"
        ].sum()

        output[
            f"{variable}_max"
        ] = grouped[
            variable
        ].max()

    # Mean / min variables
    for variable in (
        MEAN_MIN_VARIABLES
    ):

        output[
            f"{variable}_mean"
        ] = grouped[
            f"weighted_{variable}"
        ].sum()

        output[
            f"{variable}_min"
        ] = grouped[
            variable
        ].min()

    # Wind direction circular mean
    sin_sum = grouped[
        "wind_direction_sin_weighted"
    ].sum()

    cos_sum = grouped[
        "wind_direction_cos_weighted"
    ].sum()

    direction_radians = np.arctan2(
        sin_sum,
        cos_sum,
    )

    direction_degrees = (
        np.rad2deg(
            direction_radians
        )
        + 360.0
    ) % 360.0

    output[
        "wind_direction_10m_mean"
    ] = direction_degrees

    output[
        "wind_direction_10m_sin"
    ] = np.sin(
        direction_radians
    )

    output[
        "wind_direction_10m_cos"
    ] = np.cos(
        direction_radians
    )

    # Weighted weather-code mode
    weather_modes = []

    for time_utc, group in grouped:

        mode = weighted_mode(
            group[
                "weather_code"
            ].tolist(),
            group[
                "district_grid_weight"
            ].tolist(),
        )

        weather_modes.append(
            (
                time_utc,
                mode,
            )
        )

    weather_mode_series = pd.Series(
        data=[
            value
            for _, value
            in weather_modes
        ],
        index=[
            timestamp
            for timestamp, _
            in weather_modes
        ],
    )

    output[
        "weather_code_mode"
    ] = weather_mode_series

    output = (
        output
        .reset_index()
    )

    return output

# Process one year
def process_year(
    year,
    mapping,
    metadata,
):

    output_file = (
        OUTPUT_DIR
        / f"{year}.csv.gz"
    )

    # Resume support
    if output_file.exists():

        print(
            f"SKIP YEAR: {year} "
            f"already exists."
        )

        return output_file

    print()
    print("=" * 70)
    print(
        f"PROCESSING YEAR {year}"
    )
    print("=" * 70)

    grid_ids = (
        mapping["grid_id"]
        .drop_duplicates()
        .tolist()
    )

    print(
        f"Loading {len(grid_ids)} "
        f"weather grids..."
    )

    weather = load_grid_year(
        year=year,
        grid_ids=grid_ids,
    )

    print(
        f"Loaded rows: "
        f"{len(weather)}"
    )

    # Merge weather with District-grid relationships
    merged = mapping.merge(
        weather,
        on="grid_id",
        how="left",
        validate="many_to_many",
    )

    if merged["time_utc"].isna().any():

        raise ValueError(
            f"{year}: mapping produced "
            f"missing weather records."
        )

    # Aggregate District by District
    district_frames = []

    district_groups = (
        merged.groupby(
            [
                "network",
                "district_id",
            ],
            sort=True,
        )
    )

    print(
        f"Aggregating "
        f"{district_groups.ngroups} "
        f"districts..."
    )

    for (
        network,
        district_id,
    ), district_weather in district_groups:

        print(
            f"  {network} "
            f"{district_id}"
        )

        district_output = (
            aggregate_district(
                district_weather.copy()
            )
        )

        district_output.insert(
            0,
            "network",
            network,
        )

        district_output.insert(
            1,
            "district_id",
            district_id,
        )

        district_frames.append(
            district_output
        )

    year_output = pd.concat(
        district_frames,
        ignore_index=True,
    )

    # Add metadata
    year_output = year_output.merge(
        metadata,
        on=[
            "network",
            "district_id",
        ],
        how="left",
        validate="many_to_one",
    )

    # Sort
    year_output = (
        year_output
        .sort_values(
            [
                "network",
                "district_id",
                "time_utc",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # Validation
    district_count = (
        year_output[
            [
                "network",
                "district_id",
            ]
        ]
        .drop_duplicates()
        .shape[0]
    )

    duplicate_count = (
        year_output[
            [
                "network",
                "district_id",
                "time_utc",
            ]
        ]
        .duplicated()
        .sum()
    )

    missing_values = (
        year_output
        .isna()
        .sum()
        .sum()
    )

    if district_count != 31:

        raise ValueError(
            f"{year}: expected "
            f"31 districts, "
            f"found {district_count}."
        )

    if duplicate_count != 0:

        raise ValueError(
            f"{year}: found "
            f"{duplicate_count} "
            f"duplicate district-hours."
        )

    if missing_values != 0:

        raise ValueError(
            f"{year}: found "
            f"{missing_values} "
            f"missing values."
        )

    # Save year
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    year_output.to_csv(
        output_file,
        index=False,
        compression="gzip",
    )

    print()
    print(
        f"Saved: {output_file}"
    )

    print(
        f"Rows: {len(year_output)}"
    )

    print(
        f"Districts: "
        f"{district_count}"
    )

    print(
        f"Duplicates: "
        f"{duplicate_count}"
    )

    print(
        f"Missing values: "
        f"{missing_values}"
    )

    return output_file

# Build final combined output
def build_final_output(
    year_files,
):

    print()
    print("=" * 70)
    print(
        "BUILDING FINAL DISTRICT "
        "WEATHER FILE"
    )
    print("=" * 70)

    frames = []

    for file in year_files:

        print(
            f"Reading {file}"
        )

        frame = pd.read_csv(
            file,
            parse_dates=[
                "time_utc"
            ],
        )

        frames.append(
            frame
        )

    final = pd.concat(
        frames,
        ignore_index=True,
    )

    final = final.sort_values(
        [
            "network",
            "district_id",
            "time_utc",
        ]
    ).reset_index(
        drop=True
    )

    # Final validation
    expected_rows = (
        31 * 99744
    )

    duplicate_count = (
        final[
            [
                "network",
                "district_id",
                "time_utc",
            ]
        ]
        .duplicated()
        .sum()
    )

    missing_values = (
        final
        .isna()
        .sum()
        .sum()
    )

    district_count = (
        final[
            [
                "network",
                "district_id",
            ]
        ]
        .drop_duplicates()
        .shape[0]
    )

    print()
    print(
        f"Rows: {len(final)}"
    )

    print(
        f"Expected rows: "
        f"{expected_rows}"
    )

    print(
        f"Districts: "
        f"{district_count}"
    )

    print(
        f"Duplicates: "
        f"{duplicate_count}"
    )

    print(
        f"Missing values: "
        f"{missing_values}"
    )

    if len(final) != expected_rows:

        raise ValueError(
            f"Expected "
            f"{expected_rows} rows, "
            f"found {len(final)}."
        )

    if district_count != 31:

        raise ValueError(
            f"Expected 31 districts, "
            f"found {district_count}."
        )

    if duplicate_count != 0:

        raise ValueError(
            f"Found "
            f"{duplicate_count} "
            f"duplicate district-hours."
        )

    if missing_values != 0:

        raise ValueError(
            f"Found "
            f"{missing_values} "
            f"missing values."
        )

    FINAL_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    final.to_csv(
        FINAL_OUTPUT,
        index=False,
        compression="gzip",
    )

    print()
    print(
        f"Saved final file: "
        f"{FINAL_OUTPUT}"
    )

    print()
    print(
        "FINAL RESULT: PASS"
    )

# Main
def main():

    print("=" * 70)
    print(
        "BUILD DISTRICT HOURLY WEATHER"
    )
    print("=" * 70)

    mapping, metadata = (
        load_mapping()
    )

    print(
        f"Unique district-grid "
        f"relationships: "
        f"{len(mapping)}"
    )

    print(
        f"Districts: "
        f"{len(metadata)}"
    )

    print()

    year_files = []

    for year in YEARS:

        file = process_year(
            year=year,
            mapping=mapping,
            metadata=metadata,
        )

        year_files.append(
            file
        )

    build_final_output(
        year_files
    )


if __name__ == "__main__":
    main()