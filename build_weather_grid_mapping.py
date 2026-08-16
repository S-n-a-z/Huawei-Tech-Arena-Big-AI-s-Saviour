from pathlib import Path
import pandas as pd

# Configuration
INPUT_FILE = Path(
    "district_spatial_sampling_test.csv"
)

OUTPUT_MAPPING = Path(
    "district_weather_grid_mapping.csv"
)

OUTPUT_UNIQUE_GRIDS = Path(
    "weather_unique_grids.csv"
)

# Main
def main():

    data = pd.read_csv(INPUT_FILE)

    print("=" * 70)
    print("BUILD WEATHER GRID MAPPING")
    print("=" * 70)

    print(f"Input rows: {len(data)}")
    print()

    # Validate required columns
    required_columns = [
        "network",
        "district_id",
        "point_id",
        "ring_km",
        "direction",
        "requested_latitude",
        "requested_longitude",
        "returned_latitude",
        "returned_longitude",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
        )

    # Check failed mappings
    missing_grid_rows = data[
        data[
            [
                "returned_latitude",
                "returned_longitude",
            ]
        ]
        .isna()
        .any(axis=1)
    ]

    if len(missing_grid_rows) > 0:
        raise ValueError(
            f"Found {len(missing_grid_rows)} "
            f"sampling points without grid mapping."
        )

    # Create globally unique grid table
    unique_grids = (
        data[
            [
                "returned_latitude",
                "returned_longitude",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "returned_latitude",
                "returned_longitude",
            ]
        )
        .reset_index(drop=True)
    )

    unique_grids.insert(
        0,
        "grid_id",
        [
            f"grid_{number:04d}"
            for number in range(
                1,
                len(unique_grids) + 1
            )
        ],
    )

    # Join grid_id back to every sampling location
    mapping = data.merge(
        unique_grids,
        on=[
            "returned_latitude",
            "returned_longitude",
        ],
        how="left",
        validate="many_to_one",
    )

    # Add how many candidate points use each grid within each district
    # This preserves the sampling-location weighting.
    mapping["district_grid_weight_count"] = (
        mapping
        .groupby(
            [
                "network",
                "district_id",
                "grid_id",
            ]
        )["point_id"]
        .transform("count")
    )

    mapping["district_sampling_points"] = (
        mapping
        .groupby(
            [
                "network",
                "district_id",
            ]
        )["point_id"]
        .transform("count")
    )

    mapping["district_grid_weight"] = (
        mapping["district_grid_weight_count"]
        /
        mapping["district_sampling_points"]
    )

    # Useful global grid usage information
    district_grid_links = (
        mapping[
            [
                "network",
                "district_id",
                "grid_id",
            ]
        ]
        .drop_duplicates()
    )

    grid_district_counts = (
        district_grid_links
        .groupby("grid_id")
        .size()
        .rename("district_count")
        .reset_index()
    )

    unique_grids = unique_grids.merge(
        grid_district_counts,
        on="grid_id",
        how="left",
    )

    # Save
    mapping.to_csv(
        OUTPUT_MAPPING,
        index=False,
    )

    unique_grids.to_csv(
        OUTPUT_UNIQUE_GRIDS,
        index=False,
    )

    # Summary
    district_grid_counts = (
        district_grid_links
        .groupby(
            [
                "network",
                "district_id",
            ]
        )["grid_id"]
        .nunique()
    )

    print(
        f"District sampling relationships: "
        f"{len(mapping)}"
    )

    print(
        f"Unique district-grid relationships: "
        f"{len(district_grid_links)}"
    )

    print(
        f"Globally unique Open-Meteo grids: "
        f"{len(unique_grids)}"
    )

    print()

    print(
        f"Minimum grids per district: "
        f"{district_grid_counts.min()}"
    )

    print(
        f"Maximum grids per district: "
        f"{district_grid_counts.max()}"
    )

    print(
        f"Mean grids per district: "
        f"{district_grid_counts.mean():.2f}"
    )

    print()

    print(
        f"Maximum districts sharing one grid: "
        f"{unique_grids['district_count'].max()}"
    )

    print()

    print(
        f"Saved mapping: "
        f"{OUTPUT_MAPPING}"
    )

    print(
        f"Saved unique grids: "
        f"{OUTPUT_UNIQUE_GRIDS}"
    )

    print()

    print("FINAL RESULT: PASS")


if __name__ == "__main__":
    main()