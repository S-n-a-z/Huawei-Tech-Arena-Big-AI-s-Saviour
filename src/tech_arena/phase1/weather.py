from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

import pandas as pd
import requests

from tech_arena.config import Settings
from tech_arena.phase1.data import county_frame
from tech_arena.phase1.schedules import required_forecast_runs


def _request_json(url: str, params: dict[str, Any], retries: int = 5) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": "Huawei-Tech-Arena-Topic-2/0.2 (academic project)"},
                timeout=(30, 180),
            )
            if response.status_code == 429:
                delay = min(45, int(response.headers.get("Retry-After", 5 * (attempt + 1))))
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(min(20, 2 ** attempt))
    raise RuntimeError(f"Open-Meteo request failed: {url}") from last_error


def _normalise_payload(payload: Any, counties: pd.DataFrame, run_time: pd.Timestamp | None) -> pd.DataFrame:
    responses = payload if isinstance(payload, list) else [payload]
    if len(responses) != len(counties):
        raise ValueError(f"Expected {len(counties)} weather locations, received {len(responses)}")
    parts: list[pd.DataFrame] = []
    for response, county in zip(responses, counties.to_dict("records"), strict=True):
        hourly = response.get("hourly", {})
        if "time" not in hourly:
            raise ValueError(f"Weather response for {county['fips_code']} has no hourly timestamps")
        frame = pd.DataFrame(hourly)
        frame["weather_time"] = pd.to_datetime(frame.pop("time"), utc=True)
        frame["fips_code"] = county["fips_code"]
        if run_time is not None:
            frame["model_run_time"] = run_time
        parts.append(frame)
    return pd.concat(parts, ignore_index=True)


def download_training_weather(settings: Settings, force: bool = False) -> dict[str, Any]:
    config = settings.values["phase1"]
    counties = county_frame(settings)
    raw_dir = settings.path("raw_dir") / "phase1_weather"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cache = raw_dir / "training_ecmwf_ifs.json"
    params = {
        "latitude": ",".join(counties["latitude"].astype(str)),
        "longitude": ",".join(counties["longitude"].astype(str)),
        "start_date": pd.Timestamp(config["training_start"]).date().isoformat(),
        "end_date": pd.Timestamp(config["training_end"]).date().isoformat(),
        "hourly": ",".join(config["weather_variables"]),
        "models": config["weather_model"],
        "timezone": "GMT",
    }
    if cache.exists() and not force:
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        payload = _request_json(str(config["historical_weather_api"]), params)
        cache.write_text(json.dumps(payload), encoding="utf-8")
    frame = _normalise_payload(payload, counties, run_time=None)
    destination = settings.path("interim_dir") / "phase1_weather_training.csv.gz"
    frame.to_csv(destination, index=False, compression="gzip")
    return {"path": str(destination), "rows": int(len(frame)), "locations": len(counties)}


def download_test_forecasts(settings: Settings, force: bool = False) -> dict[str, Any]:
    config = settings.values["phase1"]
    counties = county_frame(settings)
    raw_dir = settings.path("raw_dir") / "phase1_weather" / "single_runs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parts: list[pd.DataFrame] = []
    runs = required_forecast_runs(settings)
    for index, run_time in enumerate(runs, start=1):
        cache = raw_dir / f"{run_time.strftime('%Y%m%dT%H%MZ')}.json"
        params = {
            "latitude": ",".join(counties["latitude"].astype(str)),
            "longitude": ",".join(counties["longitude"].astype(str)),
            "hourly": ",".join(config["weather_variables"]),
            "models": config["weather_model"],
            "run": run_time.strftime("%Y-%m-%dT%H:%M"),
            "forecast_hours": 60,
            "timezone": "GMT",
        }
        if cache.exists() and not force:
            payload = json.loads(cache.read_text(encoding="utf-8"))
        else:
            payload = _request_json(str(config["single_runs_api"]), params)
            cache.write_text(json.dumps(payload), encoding="utf-8")
            if index % 25 == 0:
                time.sleep(1)
        parts.append(_normalise_payload(payload, counties, run_time=run_time))
    frame = pd.concat(parts, ignore_index=True)
    destination = settings.path("interim_dir") / "phase1_weather_single_runs.csv.gz"
    frame.to_csv(destination, index=False, compression="gzip")
    return {
        "path": str(destination),
        "rows": int(len(frame)),
        "runs": int(frame["model_run_time"].nunique()),
        "availability_lag_hours": int(config["forecast_availability_lag_hours"]),
    }


def download_phase1_weather(settings: Settings, mode: str = "all", force: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if mode in {"training", "all"}:
        result["training"] = download_training_weather(settings, force=force)
    if mode in {"forecast", "all"}:
        result["forecast"] = download_test_forecasts(settings, force=force)
    return result
