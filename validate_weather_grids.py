from pathlib import Path
import pandas as pd

# Configuration
GRID_FILE = Path("weather_unique_grids.csv")

WEATHER_ROOT = Path(
    "data/raw/weather_grids"
)

REPORT_FILE = Path(
    "data/raw/weather_grid_validation_report.csv"
)

START_TIME = pd.Timestamp(
    "2015-03-28 00:00:00"
)

END_TIME = pd.Timestamp(
    "2026-08-12 23:00:00"
)

EXPECTED_YEARS = list(
    range(2015, 2027)
)

COORDINATE_TOLERANCE = 0.0001

# Expected complete hourly timeline
EXPECTED_TIMES = pd.date_range(
    start=START_TIME,
    end=END_TIME,
    freq="h",
)

EXPECTED_ROWS_PER_GRID = len(
    EXPECTED_TIMES
)

# Validate one grid
def validate_grid(
    grid_id,
    expected_latitude,
    expected_longitude,
):

    grid_dir = (
        WEATHER_ROOT / grid_id
    )

    problems = []

    # Check directory
    if not grid_dir.exists():

        return {
            "grid_id": grid_id,
            "status": "FAIL",
            "files": 0,
            "rows": 0,
            "duplicates": 0,
            "gaps": 0,
            "missing_values": 0,
            "coordinate_errors": 0,
            "problems": "Grid directory missing",
        }

    # Check expected yearly files
    expected_files = [
        grid_dir / f"{year}.csv.gz"
        for year in EXPECTED_YEARS
    ]

    existing_expected_files = [
        file
        for file in expected_files
        if file.exists()
    ]

    missing_files = [
        file.name
        for file in expected_files
        if not file.exists()
    ]

    if missing_files:

        problems.append(
            "Missing files: "
            + ", ".join(missing_files)
        )

    # Check for unexpected CSV.GZ files too
    actual_files = sorted(
        grid_dir.glob("*.csv.gz")
    )

    unexpected_files = [
        file.name
        for file in actual_files
        if file not in expected_files
    ]

    if unexpected_files:

        problems.append(
            "Unexpected files: "
            + ", ".join(unexpected_files)
        )

    # Read available expected files
    frames = []

    total_missing_values = 0
    coordinate_errors = 0

    for file in existing_expected_files:

        try:

            frame = pd.read_csv(
                file
            )

        except Exception as error:

            problems.append(
                f"{file.name} read error: "
                f"{error}"
            )

            continue

        required_columns = {
            "grid_id",
            "grid_latitude",
            "grid_longitude",
            "time_utc",
        }

        missing_columns = (
            required_columns
            - set(frame.columns)
        )

        if missing_columns:

            problems.append(
                f"{file.name} missing columns: "
                + ", ".join(
                    sorted(missing_columns)
                )
            )

            continue

        # Check grid_id stored inside file
        bad_grid_ids = (
            frame["grid_id"]
            .astype(str)
            .ne(grid_id)
            .sum()
        )

        if bad_grid_ids:

            problems.append(
                f"{file.name}: "
                f"{bad_grid_ids} rows have "
                f"wrong grid_id"
            )

        # Check returned coordinates
        latitude_error = (
            (
                frame["grid_latitude"]
                - expected_latitude
            )
            .abs()
            .gt(COORDINATE_TOLERANCE)
            .sum()
        )

        longitude_error = (
            (
                frame["grid_longitude"]
                - expected_longitude
            )
            .abs()
            .gt(COORDINATE_TOLERANCE)
            .sum()
        )

        file_coordinate_errors = (
            latitude_error
            + longitude_error
        )

        coordinate_errors += (
            file_coordinate_errors
        )

        if file_coordinate_errors:

            problems.append(
                f"{file.name}: "
                f"coordinate mismatch"
            )

        # Parse time
        try:

            frame["time_utc"] = (
                pd.to_datetime(
                    frame["time_utc"],
                    errors="raise",
                )
            )

        except Exception as error:

            problems.append(
                f"{file.name}: "
                f"time parse error: {error}"
            )

            continue

        # Check that file contains only its named year
        expected_year = int(
            file.name[:4]
        )

        wrong_year_rows = (
            frame["time_utc"]
            .dt.year
            .ne(expected_year)
            .sum()
        )

        if wrong_year_rows:

            problems.append(
                f"{file.name}: "
                f"{wrong_year_rows} rows "
                f"belong to another year"
            )

        # Missing values
        file_missing = (
            frame
            .isna()
            .sum()
            .sum()
        )

        total_missing_values += (
            file_missing
        )

        if file_missing:

            problems.append(
                f"{file.name}: "
                f"{file_missing} missing values"
            )

        frames.append(
            frame
        )

    # If nothing readable, fail
    if not frames:

        return {
            "grid_id": grid_id,
            "status": "FAIL",
            "files": len(
                existing_expected_files
            ),
            "rows": 0,
            "duplicates": 0,
            "gaps": 0,
            "missing_values": (
                total_missing_values
            ),
            "coordinate_errors": (
                coordinate_errors
            ),
            "problems": (
                "; ".join(problems)
            ),
        }

    # Combine this ONE grid only
    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    combined = combined.sort_values(
        "time_utc"
    ).reset_index(
        drop=True
    )

    total_rows = len(
        combined
    )

    # Duplicate timestamps
    duplicate_count = (
        combined["time_utc"]
        .duplicated()
        .sum()
    )

    if duplicate_count:

        problems.append(
            f"{duplicate_count} "
            f"duplicate timestamps"
        )

    # Exact timeline comparison
    actual_times = pd.DatetimeIndex(
        combined["time_utc"]
    )

    missing_times = (
        EXPECTED_TIMES
        .difference(actual_times)
    )

    extra_times = (
        actual_times
        .difference(EXPECTED_TIMES)
    )

    gap_count = len(
        missing_times
    )

    if gap_count:

        problems.append(
            f"{gap_count} expected "
            f"hours missing"
        )

    if len(extra_times):

        problems.append(
            f"{len(extra_times)} "
            f"unexpected timestamps"
        )

    # Row count
    if (
        total_rows
        != EXPECTED_ROWS_PER_GRID
    ):

        problems.append(
            f"rows={total_rows}, "
            f"expected="
            f"{EXPECTED_ROWS_PER_GRID}"
        )

    # Start/end timestamps
    actual_start = (
        combined["time_utc"].min()
    )

    actual_end = (
        combined["time_utc"].max()
    )

    if actual_start != START_TIME:

        problems.append(
            f"start={actual_start}, "
            f"expected={START_TIME}"
        )

    if actual_end != END_TIME:

        problems.append(
            f"end={actual_end}, "
            f"expected={END_TIME}"
        )

    # Final status
    status = (
        "PASS"
        if len(problems) == 0
        else "FAIL"
    )

    return {
        "grid_id": grid_id,
        "status": status,
        "files": len(
            existing_expected_files
        ),
        "rows": total_rows,
        "duplicates": (
            duplicate_count
        ),
        "gaps": gap_count,
        "missing_values": (
            total_missing_values
        ),
        "coordinate_errors": (
            coordinate_errors
        ),
        "problems": (
            ""
            if not problems
            else "; ".join(problems)
        ),
    }

# Main
def main():

    grids = pd.read_csv(
        GRID_FILE
    )

    print("=" * 70)
    print(
        "RAW WEATHER GRID DATA VALIDATION"
    )
    print("=" * 70)

    print(
        f"Expected grids: {len(grids)}"
    )

    print(
        f"Expected files per grid: "
        f"{len(EXPECTED_YEARS)}"
    )

    print(
        f"Expected rows per grid: "
        f"{EXPECTED_ROWS_PER_GRID}"
    )

    print(
        f"Expected total rows: "
        f"{EXPECTED_ROWS_PER_GRID * len(grids)}"
    )

    print()

    results = []

    for index, grid in grids.iterrows():

        grid_id = str(
            grid["grid_id"]
        )

        expected_latitude = float(
            grid["returned_latitude"]
        )

        expected_longitude = float(
            grid["returned_longitude"]
        )

        print(
            f"[{index + 1}/{len(grids)}] "
            f"Checking {grid_id}..."
        )

        result = validate_grid(
            grid_id=grid_id,
            expected_latitude=(
                expected_latitude
            ),
            expected_longitude=(
                expected_longitude
            ),
        )

        results.append(
            result
        )

        print(
            f"  {result['status']} "
            f"| files={result['files']} "
            f"| rows={result['rows']} "
            f"| duplicates="
            f"{result['duplicates']} "
            f"| gaps={result['gaps']} "
            f"| missing="
            f"{result['missing_values']} "
            f"| coordinate_errors="
            f"{result['coordinate_errors']}"
        )

        if result["problems"]:

            print(
                f"  Problems: "
                f"{result['problems']}"
            )

    # Report
    report = pd.DataFrame(
        results
    )

    REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report.to_csv(
        REPORT_FILE,
        index=False,
    )

    passed = (
        report["status"]
        .eq("PASS")
        .sum()
    )

    failed = (
        report["status"]
        .eq("FAIL")
        .sum()
    )

    total_files = (
        report["files"].sum()
    )

    total_rows = (
        report["rows"].sum()
    )

    total_duplicates = (
        report["duplicates"].sum()
    )

    total_gaps = (
        report["gaps"].sum()
    )

    total_missing = (
        report["missing_values"].sum()
    )

    total_coordinate_errors = (
        report["coordinate_errors"].sum()
    )

    print()
    print("=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    print(
        f"Grids checked: {len(report)}"
    )

    print(
        f"Passed grids: {passed}"
    )

    print(
        f"Failed grids: {failed}"
    )

    print(
        f"Total yearly files: "
        f"{total_files}"
    )

    print(
        f"Total weather rows: "
        f"{total_rows}"
    )

    print(
        f"Total duplicate timestamps: "
        f"{total_duplicates}"
    )

    print(
        f"Total missing hours: "
        f"{total_gaps}"
    )

    print(
        f"Total missing values: "
        f"{total_missing}"
    )

    print(
        f"Total coordinate errors: "
        f"{total_coordinate_errors}"
    )

    print()

    if failed == 0:

        print(
            "FINAL RESULT: PASS"
        )

        print(
            "All raw weather grid data "
            "passed validation."
        )

    else:

        print(
            "FINAL RESULT: FAIL"
        )

        print(
            "Some raw weather grid data "
            "requires attention."
        )

    print()

    print(
        f"Validation report saved: "
        f"{REPORT_FILE}"
    )


if __name__ == "__main__":
    main()