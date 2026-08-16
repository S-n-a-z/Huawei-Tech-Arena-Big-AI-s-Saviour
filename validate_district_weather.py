from pathlib import Path
import numpy as np
import pandas as pd


INPUT_FILE = Path(
    "data/processed/district_weather_hourly.csv.gz"
)

REPORT_DIR = Path(
    "data/processed/weather_validation"
)

EXPECTED_DISTRICTS = 31
EXPECTED_ROWS = 3_092_064

REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def main():

    print("=" * 70)
    print("DISTRICT WEATHER QUALITY VALIDATION")
    print("=" * 70)

    print(f"\nReading: {INPUT_FILE}")

    df = pd.read_csv(
        INPUT_FILE,
        parse_dates=["time_utc"],
    )

    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    # Structural validation
    print("\n" + "=" * 70)
    print("1. STRUCTURAL VALIDATION")
    print("=" * 70)

    districts = (
        df[
            ["network", "district_id"]
        ]
        .drop_duplicates()
    )

    district_count = len(districts)

    duplicates = (
        df[
            [
                "network",
                "district_id",
                "time_utc",
            ]
        ]
        .duplicated()
        .sum()
    )

    missing = df.isna().sum().sum()

    print(f"Districts: {district_count}")
    print(f"Expected districts: {EXPECTED_DISTRICTS}")

    print(f"Rows: {len(df):,}")
    print(f"Expected rows: {EXPECTED_ROWS:,}")

    print(f"Duplicate district-hours: {duplicates}")
    print(f"Missing values: {missing}")

    structural_pass = (
        district_count == EXPECTED_DISTRICTS
        and len(df) == EXPECTED_ROWS
        and duplicates == 0
        and missing == 0
    )

    print(
        "Structural result:",
        "PASS" if structural_pass else "FAIL"
    )

    # Time range
    print("\n" + "=" * 70)
    print("2. TIME RANGE")
    print("=" * 70)

    print("Start:", df["time_utc"].min())
    print("End:", df["time_utc"].max())

    # District row counts
    print("\n" + "=" * 70)
    print("3. DISTRICT ROW COUNTS")
    print("=" * 70)

    district_rows = (
        df.groupby(
            ["network", "district_id"]
        )
        .size()
        .rename("rows")
        .reset_index()
    )

    print(district_rows.to_string(index=False))

    district_rows.to_csv(
        REPORT_DIR / "district_row_counts.csv",
        index=False,
    )

    # Numeric distribution
    print("\n" + "=" * 70)
    print("4. WEATHER VARIABLE DISTRIBUTIONS")
    print("=" * 70)

    weather_columns = [
        c for c in df.columns
        if c not in {
            "network",
            "district_id",
            "time_utc",
            "weather_sampling_point_count",
            "weather_grid_count",
        }
        and pd.api.types.is_numeric_dtype(df[c])
    ]

    quantiles = [
        0.00,
        0.001,
        0.01,
        0.05,
        0.50,
        0.95,
        0.99,
        0.999,
        1.00,
    ]

    rows = []

    for col in weather_columns:

        x = df[col]

        q = x.quantile(quantiles)

        row = {
            "variable": col,
            "mean": x.mean(),
            "std": x.std(),
            "min": q.loc[0.00],
            "p0_1": q.loc[0.001],
            "p1": q.loc[0.01],
            "p5": q.loc[0.05],
            "median": q.loc[0.50],
            "p95": q.loc[0.95],
            "p99": q.loc[0.99],
            "p99_9": q.loc[0.999],
            "max": q.loc[1.00],
        }

        rows.append(row)

    distribution = pd.DataFrame(rows)

    print(
        distribution.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    distribution.to_csv(
        REPORT_DIR / "weather_variable_distribution.csv",
        index=False,
    )

    # Basic physical sanity checks
    print("\n" + "=" * 70)
    print("5. BASIC PHYSICAL SANITY CHECKS")
    print("=" * 70)

    checks = []

    def add_check(name, mask):

        count = int(mask.sum())

        checks.append(
            {
                "check": name,
                "violations": count,
            }
        )

        print(
            f"{name}: "
            f"{count:,} violation(s)"
        )

    if "relative_humidity_2m_mean" in df:

        add_check(
            "humidity_mean < 0",
            df["relative_humidity_2m_mean"] < 0,
        )

        add_check(
            "humidity_mean > 100",
            df["relative_humidity_2m_mean"] > 100,
        )

    if "precipitation_mean" in df:

        add_check(
            "precipitation_mean < 0",
            df["precipitation_mean"] < 0,
        )

    if "precipitation_max" in df:

        add_check(
            "precipitation_max < 0",
            df["precipitation_max"] < 0,
        )

    if "rain_mean" in df:

        add_check(
            "rain_mean < 0",
            df["rain_mean"] < 0,
        )

    if "snowfall_mean" in df:

        add_check(
            "snowfall_mean < 0",
            df["snowfall_mean"] < 0,
        )

    if "snow_depth_mean" in df:

        add_check(
            "snow_depth_mean < 0",
            df["snow_depth_mean"] < 0,
        )

    if "wind_speed_10m_mean" in df:

        add_check(
            "wind_speed_mean < 0",
            df["wind_speed_10m_mean"] < 0,
        )

    if "wind_gusts_10m_mean" in df:

        add_check(
            "wind_gust_mean < 0",
            df["wind_gusts_10m_mean"] < 0,
        )

    if "surface_pressure_mean" in df:

        add_check(
            "surface_pressure_mean <= 0",
            df["surface_pressure_mean"] <= 0,
        )

    checks_df = pd.DataFrame(checks)

    checks_df.to_csv(
        REPORT_DIR / "physical_sanity_checks.csv",
        index=False,
    )

    # Extreme weather by district
    print("\n" + "=" * 70)
    print("6. EXTREME WEATHER BY DISTRICT")
    print("=" * 70)

    extreme_columns = [
        c for c in [
            "temperature_2m_min",
            "temperature_2m_max",
            "precipitation_max",
            "rain_max",
            "snowfall_max",
            "snow_depth_max",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "surface_pressure_min",
        ]
        if c in df.columns
    ]

    district_extremes = (
        df.groupby(
            ["network", "district_id"]
        )[extreme_columns]
        .agg(["min", "max"])
    )

    district_extremes.columns = [
        f"{variable}_{stat}"
        for variable, stat
        in district_extremes.columns
    ]

    district_extremes = (
        district_extremes
        .reset_index()
    )

    print(
        district_extremes.to_string(
            index=False
        )
    )

    district_extremes.to_csv(
        REPORT_DIR / "district_weather_extremes.csv",
        index=False,
    )

    # Top extreme wind-gust hours
    if "wind_gusts_10m_max" in df.columns:

        print("\n" + "=" * 70)
        print("7. TOP 50 WIND-GUST HOURS")
        print("=" * 70)

        top_wind = (
            df.nlargest(
                50,
                "wind_gusts_10m_max",
            )[
                [
                    "network",
                    "district_id",
                    "time_utc",
                    "wind_gusts_10m_mean",
                    "wind_gusts_10m_max",
                    "wind_speed_10m_mean",
                    "wind_speed_10m_max",
                ]
            ]
        )

        print(top_wind.to_string(index=False))

        top_wind.to_csv(
            REPORT_DIR / "top_50_wind_gust_hours.csv",
            index=False,
        )

    # Top precipitation hours
    if "precipitation_max" in df.columns:

        print("\n" + "=" * 70)
        print("8. TOP 50 PRECIPITATION HOURS")
        print("=" * 70)

        top_precip = (
            df.nlargest(
                50,
                "precipitation_max",
            )[
                [
                    "network",
                    "district_id",
                    "time_utc",
                    "precipitation_mean",
                    "precipitation_max",
                    "rain_mean",
                    "rain_max",
                ]
            ]
        )

        print(top_precip.to_string(index=False))

        top_precip.to_csv(
            REPORT_DIR / "top_50_precipitation_hours.csv",
            index=False,
        )

    # Spatial spread
    print("\n" + "=" * 70)
    print("9. SPATIAL SPREAD CHECK")
    print("=" * 70)

    spread_pairs = [
        (
            "temperature_2m",
            "temperature_2m_min",
            "temperature_2m_max",
        ),
        (
            "relative_humidity_2m",
            "relative_humidity_2m_min",
            "relative_humidity_2m_max",
        ),
    ]

    spread_rows = []

    for name, min_col, max_col in spread_pairs:

        if (
            min_col in df.columns
            and max_col in df.columns
        ):

            spread = (
                df[max_col]
                - df[min_col]
            )

            spread_rows.append(
                {
                    "variable": name,
                    "mean_spread": spread.mean(),
                    "p95_spread": spread.quantile(0.95),
                    "p99_spread": spread.quantile(0.99),
                    "max_spread": spread.max(),
                }
            )

    spread_df = pd.DataFrame(
        spread_rows
    )

    print(
        spread_df.to_string(
            index=False
        )
    )

    spread_df.to_csv(
        REPORT_DIR / "spatial_spread_summary.csv",
        index=False,
    )

    # Sampling/grid metadata
    print("\n" + "=" * 70)
    print("10. DISTRICT SPATIAL METADATA")
    print("=" * 70)

    spatial_metadata = (
        df[
            [
                "network",
                "district_id",
                "weather_sampling_point_count",
                "weather_grid_count",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            ["network", "district_id"]
        )
    )

    print(
        spatial_metadata.to_string(
            index=False
        )
    )

    spatial_metadata.to_csv(
        REPORT_DIR / "district_spatial_metadata.csv",
        index=False,
    )

    # Final result
    physical_violations = (
        checks_df["violations"].sum()
        if len(checks_df)
        else 0
    )

    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    print(
        "Structural validation:",
        "PASS" if structural_pass else "FAIL"
    )

    print(
        "Physical sanity violations:",
        int(physical_violations)
    )

    if (
        structural_pass
        and physical_violations == 0
    ):

        print("\nFINAL RESULT: PASS")

    else:

        print(
            "\nFINAL RESULT: REVIEW REQUIRED"
        )

    print(
        "\nReports saved to:",
        REPORT_DIR,
    )


if __name__ == "__main__":
    main()