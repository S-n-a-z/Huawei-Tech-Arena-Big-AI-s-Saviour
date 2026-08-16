from pathlib import Path
import time
import pandas as pd
import requests

# Configuration
GRID_FILE = Path("weather_unique_grids.csv")

OUTPUT_ROOT = Path(
    "data/raw/weather_grids"
)

URL = "https://archive-api.open-meteo.com/v1/archive"

START_DATE = pd.Timestamp("2015-03-28")
END_DATE = pd.Timestamp("2026-08-12")

MAX_RETRIES = 5

REQUEST_WAIT_SECONDS = 3

# Weather variables
HOURLY_VARIABLES = [
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

# Request-coordinate overrides

# Normally the returned Open-Meteo grid coordinate can be used
# as the request coordinate.

# grid_0151 is a special case:
# requesting its returned coordinate directly repeatedly timed
# out, while requesting the original ORKN sampling coordinate
# with cell_selection="land" successfully maps back to the
# same Open-Meteo grid.
REQUEST_COORDINATE_OVERRIDES = {
    "grid_0151": {
        "latitude": 59.017508,
        "longitude": -2.908032,
    },
}

# Coordinate comparison tolerance
COORDINATE_TOLERANCE = 0.0001

# Build expected yearly periods
def build_year_periods():

    periods = []

    for year in range(
        START_DATE.year,
        END_DATE.year + 1,
    ):

        period_start = max(
            START_DATE,
            pd.Timestamp(f"{year}-01-01"),
        )

        period_end = min(
            END_DATE,
            pd.Timestamp(f"{year}-12-31"),
        )

        periods.append(
            (
                year,
                period_start.strftime("%Y-%m-%d"),
                period_end.strftime("%Y-%m-%d"),
            )
        )

    return periods

# Request Open-Meteo data
def request_weather(
    latitude,
    longitude,
    start_date,
    end_date,
):

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "GMT",

        # Explicitly freeze the spatial cell-selection method.
        # Previously this was implicitly using Open-Meteo's
        # default land selection.
        "cell_selection": "land",
    }

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            print(
                f"REQUEST: "
                f"{start_date} to {end_date} "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )

            response = requests.get(
                URL,
                params=params,
                timeout=300,
            )

            if response.status_code == 429:

                wait_seconds = 60 * attempt

                print(
                    f"RATE LIMITED (429). "
                    f"Waiting {wait_seconds} seconds..."
                )

                time.sleep(wait_seconds)

                continue

            response.raise_for_status()

            data = response.json()

            if data.get("timezone") != "GMT":
                raise ValueError(
                    f"Expected GMT, got "
                    f"{data.get('timezone')}"
                )

            if data.get("utc_offset_seconds") != 0:
                raise ValueError(
                    f"Expected UTC offset 0, got "
                    f"{data.get('utc_offset_seconds')}"
                )

            frame = pd.DataFrame(
                data["hourly"]
            )

            frame = frame.rename(
                columns={
                    "time": "time_utc"
                }
            )

            frame["time_utc"] = pd.to_datetime(
                frame["time_utc"]
            )

            duplicate_count = (
                frame["time_utc"]
                .duplicated()
                .sum()
            )

            missing_count = (
                frame
                .isna()
                .sum()
                .sum()
            )

            gaps = (
                frame["time_utc"]
                .sort_values()
                .diff()
                .dropna()
                .ne(pd.Timedelta(hours=1))
                .sum()
            )

            if duplicate_count != 0:
                raise ValueError(
                    f"Found {duplicate_count} "
                    f"duplicate timestamps."
                )

            if missing_count != 0:
                raise ValueError(
                    f"Found {missing_count} "
                    f"missing values."
                )

            if gaps != 0:
                raise ValueError(
                    f"Found {gaps} "
                    f"non-hourly gaps."
                )

            time.sleep(
                REQUEST_WAIT_SECONDS
            )

            return frame, data

        except (
            requests.RequestException,
            ValueError,
            KeyError,
        ) as error:

            print(
                f"ERROR: {error}"
            )

            if attempt < MAX_RETRIES:

                wait_seconds = 30 * attempt

                print(
                    f"Waiting "
                    f"{wait_seconds} seconds..."
                )

                time.sleep(
                    wait_seconds
                )

    return None, None

# Validate returned Open-Meteo grid
def validate_returned_grid(
    grid_id,
    data,
    expected_latitude,
    expected_longitude,
):

    returned_latitude = float(
        data["latitude"]
    )

    returned_longitude = float(
        data["longitude"]
    )

    latitude_difference = abs(
        returned_latitude
        - expected_latitude
    )

    longitude_difference = abs(
        returned_longitude
        - expected_longitude
    )

    print(
        f"Expected grid coordinate: "
        f"{expected_latitude}, "
        f"{expected_longitude}"
    )

    print(
        f"Returned grid coordinate: "
        f"{returned_latitude}, "
        f"{returned_longitude}"
    )

    if (
        latitude_difference
        > COORDINATE_TOLERANCE
        or
        longitude_difference
        > COORDINATE_TOLERANCE
    ):
        raise ValueError(
            f"{grid_id}: Open-Meteo returned a "
            f"different grid coordinate. "
            f"Expected "
            f"({expected_latitude}, "
            f"{expected_longitude}), "
            f"got "
            f"({returned_latitude}, "
            f"{returned_longitude})."
        )

    print(
        f"GRID VALIDATION PASS: {grid_id}"
    )

# Save one year
def save_year_file(
    frame,
    data,
    grid_id,
    year,
    output_file,
):

    year_frame = frame.loc[
        frame["time_utc"].dt.year == year
    ].copy()

    year_frame.insert(
        0,
        "grid_id",
        grid_id,
    )

    year_frame.insert(
        1,
        "grid_latitude",
        data["latitude"],
    )

    year_frame.insert(
        2,
        "grid_longitude",
        data["longitude"],
    )

    year_frame.to_csv(
        output_file,
        index=False,
        compression="gzip",
    )

    print(
        f"OK: {output_file} "
        f"({len(year_frame)} rows)"
    )

# Process one grid
def process_grid(
    grid_id,
    expected_latitude,
    expected_longitude,
    request_latitude,
    request_longitude,
    periods,
):

    grid_dir = (
        OUTPUT_ROOT / grid_id
    )

    grid_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    expected_files = {
        year: (
            grid_dir / f"{year}.csv.gz"
        )
        for year, _, _ in periods
    }

    existing_years = [
        year
        for year, file in expected_files.items()
        if file.exists()
    ]

    missing_years = [
        year
        for year, file in expected_files.items()
        if not file.exists()
    ]

    # Case 1: complete grid
    if len(missing_years) == 0:

        print(
            f"SKIP GRID: {grid_id} "
            f"already complete."
        )

        return len(periods), 0

    if (
        request_latitude != expected_latitude
        or
        request_longitude != expected_longitude
    ):

        print(
            f"REQUEST COORDINATE OVERRIDE: "
            f"{grid_id}"
        )

        print(
            f"Stored grid coordinate: "
            f"{expected_latitude}, "
            f"{expected_longitude}"
        )

        print(
            f"API request coordinate: "
            f"{request_latitude}, "
            f"{request_longitude}"
        )

    # Case 2: no files exist
    
    # One long request for entire period,
    # then split locally into yearly files.
    if len(existing_years) == 0:

        print(
            f"FULL DOWNLOAD: {grid_id}"
        )

        frame, data = request_weather(
            latitude=request_latitude,
            longitude=request_longitude,
            start_date=START_DATE.strftime(
                "%Y-%m-%d"
            ),
            end_date=END_DATE.strftime(
                "%Y-%m-%d"
            ),
        )

        if frame is None:

            print(
                f"FAILED GRID: {grid_id}"
            )

            return 0, len(periods)

        # Confirm that Open-Meteo still maps the request
        # coordinate to the expected stored grid.
        try:

            validate_returned_grid(
                grid_id=grid_id,
                data=data,
                expected_latitude=expected_latitude,
                expected_longitude=expected_longitude,
            )

        except ValueError as error:

            print(
                f"GRID VALIDATION FAILED: "
                f"{error}"
            )

            print(
                "No files will be saved "
                "for this grid."
            )

            return 0, len(periods)

        successful = 0

        for (
            year,
            start_date,
            end_date,
        ) in periods:

            output_file = (
                expected_files[year]
            )

            save_year_file(
                frame=frame,
                data=data,
                grid_id=grid_id,
                year=year,
                output_file=output_file,
            )

            successful += 1

        return successful, 0

    # Case 3: partial grid

    # Only download missing years.
    print(
        f"PARTIAL GRID: {grid_id}"
    )

    print(
        f"Existing years: "
        f"{len(existing_years)}"
    )

    print(
        f"Missing years: "
        f"{missing_years}"
    )

    successful = 0
    failed = 0

    period_lookup = {
        year: (
            start_date,
            end_date,
        )
        for (
            year,
            start_date,
            end_date,
        ) in periods
    }

    for year in missing_years:

        start_date, end_date = (
            period_lookup[year]
        )

        frame, data = request_weather(
            latitude=request_latitude,
            longitude=request_longitude,
            start_date=start_date,
            end_date=end_date,
        )

        if frame is None:

            print(
                f"FAILED: "
                f"{grid_id} {year}"
            )

            failed += 1

            continue

        # Validate every newly downloaded missing year
        # before saving it.
        try:

            validate_returned_grid(
                grid_id=grid_id,
                data=data,
                expected_latitude=expected_latitude,
                expected_longitude=expected_longitude,
            )

        except ValueError as error:

            print(
                f"GRID VALIDATION FAILED: "
                f"{error}"
            )

            print(
                f"Not saving "
                f"{grid_id} {year}."
            )

            failed += 1

            continue

        output_file = (
            expected_files[year]
        )

        save_year_file(
            frame=frame,
            data=data,
            grid_id=grid_id,
            year=year,
            output_file=output_file,
        )

        successful += 1

    return successful, failed

# Main
def main():

    grids = pd.read_csv(
        GRID_FILE
    )

    periods = build_year_periods()

    total_successful = 0
    total_failed = 0

    print()
    print("SMART WEATHER GRID DOWNLOADER")
    print("=" * 60)

    print(
        f"Grids: {len(grids)}"
    )

    print(
        f"Period: "
        f"{START_DATE.date()} "
        f"to {END_DATE.date()}"
    )

    print(
        f"Expected files per grid: "
        f"{len(periods)}"
    )

    print(
        "Open-Meteo cell selection: land"
    )

    print()

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

        # Select API request coordinate
        if grid_id in REQUEST_COORDINATE_OVERRIDES:

            override = (
                REQUEST_COORDINATE_OVERRIDES[
                    grid_id
                ]
            )

            request_latitude = float(
                override["latitude"]
            )

            request_longitude = float(
                override["longitude"]
            )

        else:

            request_latitude = (
                expected_latitude
            )

            request_longitude = (
                expected_longitude
            )

        print()
        print(
            f"[{index + 1}/{len(grids)}] "
            f"{grid_id}"
        )

        print(
            f"Grid coordinates: "
            f"{expected_latitude}, "
            f"{expected_longitude}"
        )

        successful, failed = (
            process_grid(
                grid_id=grid_id,
                expected_latitude=expected_latitude,
                expected_longitude=expected_longitude,
                request_latitude=request_latitude,
                request_longitude=request_longitude,
                periods=periods,
            )
        )

        total_successful += successful
        total_failed += failed

    print()
    print("=" * 60)
    print("DOWNLOAD FINISHED")
    print("=" * 60)

    print(
        f"Successful/new files: "
        f"{total_successful}"
    )

    print(
        f"Failed files: "
        f"{total_failed}"
    )

    print()

    print(
        "Note: already-existing complete grids "
        "are counted as successful."
    )


if __name__ == "__main__":
    main()