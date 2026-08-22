from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlencode

import pandas as pd

from tech_arena.config import Settings
from tech_arena.data.locations import configured_locations
from tech_arena.net import get_json


def _location_request_url(
    settings: Settings,
    location: dict[str, Any],
    start: date,
    end: date,
) -> str:
    weather = settings.values["weather"]
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(weather["variables"]),
        "timezone": weather["timezone"],
    }
    return f"{weather['archive_api']}?{urlencode(params)}"


def _batch_request_url(
    settings: Settings,
    locations: list[dict[str, Any]],
    start: date,
    end: date,
) -> str:
    weather = settings.values["weather"]
    params = {
        "latitude": ",".join(str(item["latitude"]) for item in locations),
        "longitude": ",".join(str(item["longitude"]) for item in locations),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(weather["variables"]),
        "timezone": weather["timezone"],
    }
    return f"{weather['archive_api']}?{urlencode(params)}"


def download_historical_weather(
    settings: Settings,
    start: date | None = None,
    end: date | None = None,
    force: bool = False,
) -> Path:
    incidents_path = settings.path("interim_dir") / "nafirs_incidents.csv.gz"
    if end is None or start is None:
        incidents = pd.read_csv(incidents_path, usecols=["TIMESTAMP_UTC"], parse_dates=["TIMESTAMP_UTC"])
        incident_end = incidents["TIMESTAMP_UTC"].max().date()
        history_days = int(settings.values["features"]["hourly_history_days"])
        end = end or incident_end
        start = start or max(incidents["TIMESTAMP_UTC"].min().date(), end - timedelta(days=history_days))

    output = settings.path("interim_dir") / "weather_hourly.csv.gz"
    manifest_path = settings.path("raw_dir") / "weather" / "manifest.json"
    if output.exists() and not force:
        return output

    raw_weather_dir = settings.path("raw_dir") / "weather"
    raw_weather_dir.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    manifest: list[dict[str, Any]] = []
    locations = configured_locations(settings)
    payloads: dict[str, dict[str, Any]] = {}
    missing: list[dict[str, Any]] = []
    for location in locations:
        cache = raw_weather_dir / f"{location['location_id']}_{start}_{end}.json"
        if cache.exists() and not force:
            payloads[location["location_id"]] = json.loads(cache.read_text(encoding="utf-8"))
        else:
            missing.append(location)

    batch_size = 5
    for offset in range(0, len(missing), batch_size):
        batch = missing[offset : offset + batch_size]
        url = _batch_request_url(settings, batch, start, end)
        response = get_json(url, retries=6, timeout=180)
        response_items = response if isinstance(response, list) else [response]
        if len(response_items) != len(batch):
            raise RuntimeError("Open-Meteo returned an unexpected number of location responses.")
        for location, payload in zip(batch, response_items):
            cache = raw_weather_dir / f"{location['location_id']}_{start}_{end}.json"
            cache.write_text(json.dumps(payload), encoding="utf-8")
            payloads[location["location_id"]] = payload
        if offset + batch_size < len(missing):
            time.sleep(2)

    for location in locations:
        url = _location_request_url(settings, location, start, end)
        payload = payloads[location["location_id"]]
        if payload.get("error"):
            raise RuntimeError(f"Open-Meteo error for {location['location_id']}: {payload.get('reason')}")
        hourly = pd.DataFrame(payload["hourly"])
        hourly["timestamp_utc"] = pd.to_datetime(hourly.pop("time"), utc=True)
        hourly["location_id"] = location["location_id"]
        hourly["network"] = location["network"]
        if "district_id" in location:
            hourly["district_id"] = location["district_id"]
        hourly["requested_latitude"] = location["latitude"]
        hourly["requested_longitude"] = location["longitude"]
        hourly["grid_latitude"] = payload.get("latitude")
        hourly["grid_longitude"] = payload.get("longitude")
        frames.append(hourly)
        manifest.append(
            {
                "location_id": location["location_id"],
                "network": location["network"],
                "district_id": location.get("district_id"),
                "url": url,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "license": "CC BY 4.0",
                "grid_latitude": payload.get("latitude"),
                "grid_longitude": payload.get("longitude"),
            }
        )

    weather = pd.concat(frames, ignore_index=True)
    weather = weather.sort_values(["network", "location_id", "timestamp_utc"])
    weather.to_csv(output, index=False, compression="gzip")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output


def aggregate_weather(path: Path) -> pd.DataFrame:
    weather = pd.read_csv(path, parse_dates=["timestamp_utc"])
    id_columns = {
        "timestamp_utc",
        "location_id",
        "network",
        "district_id",
        "requested_latitude",
        "requested_longitude",
        "grid_latitude",
        "grid_longitude",
    }
    value_columns = [column for column in weather.columns if column not in id_columns]
    group_columns = ["network", "timestamp_utc"]
    if "district_id" in weather.columns and weather["district_id"].notna().any():
        group_columns.insert(1, "district_id")
    mean = weather.groupby(group_columns)[value_columns].mean().add_prefix("wx_mean_")
    hazardous = [
        column
        for column in value_columns
        if any(token in column for token in ("gust", "wind_speed", "precip", "rain", "snow"))
    ]
    maximum = weather.groupby(group_columns)[hazardous].max().add_prefix("wx_max_")
    return mean.join(maximum).reset_index()


def load_prepared_district_weather(path: Path) -> pd.DataFrame:
    """Load the team's district-level weather table into the model feature contract."""

    weather = pd.read_csv(path, low_memory=False)
    weather.columns = [str(column).strip().lower() for column in weather.columns]
    timestamp_column = next(
        (
            column
            for column in ("timestamp_utc", "time", "timestamp", "datetime")
            if column in weather.columns
        ),
        None,
    )
    if timestamp_column is None:
        raise ValueError("Prepared district weather has no recognised timestamp column.")
    if timestamp_column != "timestamp_utc":
        weather = weather.rename(columns={timestamp_column: "timestamp_utc"})
    required = {"network", "district_id", "timestamp_utc"}
    missing = required - set(weather.columns)
    if missing:
        raise ValueError(f"Prepared district weather is missing columns: {sorted(missing)}")

    weather["timestamp_utc"] = pd.to_datetime(weather["timestamp_utc"], utc=True)
    id_columns = {
        "network",
        "district_id",
        "timestamp_utc",
        "location_id",
        "requested_latitude",
        "requested_longitude",
        "grid_latitude",
        "grid_longitude",
    }
    value_columns = [column for column in weather.columns if column not in id_columns]
    for column in value_columns:
        weather[column] = pd.to_numeric(weather[column], errors="coerce")
    rename = {
        column: column if column.startswith("wx_") else f"wx_{column}"
        for column in value_columns
    }
    keep = ["network", "district_id", "timestamp_utc", *value_columns]
    result = weather[keep].rename(columns=rename)
    if result.duplicated(["network", "district_id", "timestamp_utc"]).any():
        raise ValueError("Prepared district weather contains duplicate district-hours.")
    return result.sort_values(["network", "district_id", "timestamp_utc"])


def load_model_weather(settings: Settings) -> pd.DataFrame:
    prepared = settings.path("processed_dir") / "district_weather_hourly.csv.gz"
    if prepared.exists():
        return load_prepared_district_weather(prepared)
    return aggregate_weather(settings.path("interim_dir") / "weather_hourly.csv.gz")
