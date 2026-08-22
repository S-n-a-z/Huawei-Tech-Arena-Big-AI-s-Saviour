from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from tech_arena.config import Settings
from tech_arena.data.weather import load_model_weather


@dataclass(frozen=True)
class TaskDefinition:
    name: str
    frequency: str
    history_days: int
    max_horizon_minutes: int
    horizon_step_minutes: int
    lag_steps: tuple[int, ...]
    rolling_steps: tuple[int, ...]


def task_definitions(settings: Settings) -> dict[str, TaskDefinition]:
    features = settings.values["features"]
    return {
        "day_ahead": TaskDefinition(
            name="day_ahead",
            frequency="1h",
            history_days=int(features["hourly_history_days"]),
            max_horizon_minutes=48 * 60,
            horizon_step_minutes=60,
            lag_steps=(1, 3, 6, 12, 24, 48),
            rolling_steps=(3, 6, 12, 24, 48),
        ),
        "hour_ahead": TaskDefinition(
            name="hour_ahead",
            frequency="5min",
            history_days=int(features["five_minute_history_days"]),
            max_horizon_minutes=6 * 60,
            horizon_step_minutes=5,
            lag_steps=(1, 3, 6, 12, 36, 72),
            rolling_steps=(3, 12, 36, 72),
        ),
    }


def _expand_group(
    incidents: pd.DataFrame,
    frequency: str,
    global_end: pd.Timestamp,
    history_days: int,
) -> pd.DataFrame:
    start_limit = global_end - pd.Timedelta(days=history_days)
    group_start = max(incidents["TIMESTAMP_UTC"].min(), start_limit).floor(frequency)
    group_end = global_end.ceil(frequency)
    index = pd.date_range(group_start, group_end, freq=frequency, tz="UTC")
    if index.empty:
        return pd.DataFrame()

    customer_delta = np.zeros(len(index) + 1, dtype=float)
    incident_delta = np.zeros(len(index) + 1, dtype=float)
    starts = incidents["TIMESTAMP_UTC"].to_numpy(dtype="datetime64[ns]")
    ends = (
        incidents["TIMESTAMP_UTC"]
        + pd.to_timedelta(incidents["DURATION_MINUTES"], unit="m")
    ).to_numpy(dtype="datetime64[ns]")
    values = incidents["CUSTOMERS_AFFECTED"].to_numpy(dtype=float)
    index_values = index.tz_localize(None).to_numpy(dtype="datetime64[ns]")

    start_positions = np.searchsorted(index_values, starts, side="right") - 1
    end_positions = np.searchsorted(index_values, ends, side="left")
    for start, end, customers in zip(start_positions, end_positions, values):
        if end < 0 or start >= len(index):
            continue
        start = max(0, int(start))
        end = min(len(index), max(start + 1, int(end)))
        customer_delta[start] += customers
        customer_delta[end] -= customers
        incident_delta[start] += 1
        incident_delta[end] -= 1

    active_customers = np.cumsum(customer_delta[:-1])
    active_incidents = np.cumsum(incident_delta[:-1])
    positive = active_customers[active_customers > 0]
    event_exposure = incidents["CUSTOMERS_AFFECTED"].quantile(0.995)
    concurrent_exposure = np.quantile(positive, 0.995) if len(positive) else 0.0
    exposure_proxy = max(float(event_exposure), float(concurrent_exposure), 1.0)
    return pd.DataFrame(
        {
            "timestamp_utc": index,
            "active_customers": active_customers,
            "active_incidents": active_incidents,
            "exposure_proxy": exposure_proxy,
            "regional_outage_prop": np.clip(active_customers / exposure_proxy, 0.0, 1.0),
        }
    )


def build_regional_timeseries(
    settings: Settings,
    task: TaskDefinition,
    include_planned: bool = False,
) -> Path:
    source = settings.path("interim_dir") / "nafirs_incidents.csv.gz"
    incidents = pd.read_csv(source, parse_dates=["TIMESTAMP_UTC"], low_memory=False)
    incidents["TIMESTAMP_UTC"] = pd.to_datetime(incidents["TIMESTAMP_UTC"], utc=True)
    if not include_planned:
        planned = incidents["IS_PLANNED"].astype(str).str.lower().isin({"true", "1"})
        incidents = incidents.loc[~planned].copy()
    global_end = incidents["TIMESTAMP_UTC"].max()

    frames: list[pd.DataFrame] = []
    for (network, district), group in incidents.groupby(["NETWORK", "DISTRICT_ID"], sort=True):
        expanded = _expand_group(group, task.frequency, global_end, task.history_days)
        if expanded.empty:
            continue
        expanded["network"] = network
        expanded["district_id"] = str(district)
        frames.append(expanded)
    result = pd.concat(frames, ignore_index=True)
    output = settings.path("processed_dir") / f"{task.name}_regional_timeseries.csv.gz"
    result.to_csv(output, index=False, compression="gzip")
    return output


def _weather_at_frequency(weather: pd.DataFrame, frequency: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    group_columns = ["network"]
    if "district_id" in weather.columns:
        group_columns.append("district_id")
    for keys, group in weather.groupby(group_columns, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        group = group.sort_values("timestamp_utc").set_index("timestamp_utc")
        if frequency == "5min":
            group = group.resample(frequency).ffill()
        else:
            group = group.resample(frequency).mean(numeric_only=True)
        for column, value in zip(group_columns, keys):
            group[column] = value
        frames.append(group.reset_index())
    return pd.concat(frames, ignore_index=True)


def add_causal_features(
    regional: pd.DataFrame,
    weather: pd.DataFrame,
    task: TaskDefinition,
    osm: pd.DataFrame | None = None,
) -> pd.DataFrame:
    regional = regional.sort_values(["network", "district_id", "timestamp_utc"]).copy()
    weather = _weather_at_frequency(weather, task.frequency)
    join_columns = ["network", "timestamp_utc"]
    if "district_id" in weather.columns:
        join_columns.insert(1, "district_id")
    result = regional.merge(weather, on=join_columns, how="left")
    if osm is not None:
        osm_join = ["network", "district_id"] if "district_id" in osm.columns else ["network"]
        result = result.merge(osm, on=osm_join, how="left")

    grouped = result.groupby(["network", "district_id"], sort=False)
    for lag in task.lag_steps:
        result[f"risk_lag_{lag}"] = grouped["regional_outage_prop"].shift(lag)
    for window in task.rolling_steps:
        shifted = grouped["regional_outage_prop"].shift(1)
        result[f"risk_roll_mean_{window}"] = (
            shifted.groupby([result["network"], result["district_id"]])
            .rolling(window, min_periods=1)
            .mean()
            .reset_index(level=[0, 1], drop=True)
        )
        result[f"risk_roll_max_{window}"] = (
            shifted.groupby([result["network"], result["district_id"]])
            .rolling(window, min_periods=1)
            .max()
            .reset_index(level=[0, 1], drop=True)
        )

    result["hour_sin"] = np.sin(2 * np.pi * result["timestamp_utc"].dt.hour / 24)
    result["hour_cos"] = np.cos(2 * np.pi * result["timestamp_utc"].dt.hour / 24)
    day_of_year = result["timestamp_utc"].dt.dayofyear
    result["year_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    result["year_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
    result["weather_age_minutes"] = 0 if task.frequency == "1h" else result["timestamp_utc"].dt.minute % 60
    return result


def make_supervised_table(
    featured: pd.DataFrame,
    task: TaskDefinition,
    event_threshold: float,
    negative_ratio: int,
    max_positive: int,
    minimum_negative: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames: list[pd.DataFrame] = []
    step_minutes = pd.Timedelta(task.frequency).total_seconds() / 60
    for (_, _), group in featured.groupby(["network", "district_id"], sort=False):
        group = group.sort_values("timestamp_utc").reset_index(drop=True)
        for horizon_minutes in range(
            task.horizon_step_minutes,
            task.max_horizon_minutes + 1,
            task.horizon_step_minutes,
        ):
            shift_steps = int(horizon_minutes / step_minutes)
            target = group["regional_outage_prop"].shift(-shift_steps)
            valid = target.notna()
            if not valid.any():
                continue
            subset = group.loc[valid].copy()
            subset["target_regional_outage_prop"] = target.loc[valid].to_numpy()
            subset["target_event"] = (
                subset["target_regional_outage_prop"] > event_threshold
            ).astype(int)
            subset["lead_minutes"] = horizon_minutes
            subset["issue_time"] = subset.pop("timestamp_utc")
            subset["target_time"] = subset["issue_time"] + pd.to_timedelta(horizon_minutes, unit="m")

            positive_index = subset.index[subset["target_event"] == 1].to_numpy()
            negative_index = subset.index[subset["target_event"] == 0].to_numpy()
            if len(positive_index) > max_positive:
                positive_index = rng.choice(positive_index, size=max_positive, replace=False)
            negative_count = min(
                len(negative_index),
                max(minimum_negative, negative_ratio * max(1, len(positive_index))),
            )
            if negative_count < len(negative_index):
                negative_index = rng.choice(negative_index, size=negative_count, replace=False)
            selected = np.concatenate([positive_index, negative_index])
            frames.append(subset.loc[np.sort(selected)])
    if not frames:
        raise RuntimeError(f"No supervised rows were created for {task.name}.")
    result = pd.concat(frames, ignore_index=True)
    return result.sort_values(["target_time", "network", "district_id", "lead_minutes"])


def build_task_features(settings: Settings, task_name: str, include_osm: bool = False) -> Path:
    task = task_definitions(settings)[task_name]
    regional_path = build_regional_timeseries(settings, task)
    regional = pd.read_csv(regional_path, parse_dates=["timestamp_utc"])
    regional["timestamp_utc"] = pd.to_datetime(regional["timestamp_utc"], utc=True)
    weather = load_model_weather(settings)
    weather["timestamp_utc"] = pd.to_datetime(weather["timestamp_utc"], utc=True)
    locations_path = settings.path("interim_dir") / "district_locations.csv"
    if locations_path.exists():
        valid_districts = pd.read_csv(
            locations_path,
            usecols=["network", "district_id"],
        ).drop_duplicates()
        regional = regional.merge(valid_districts, on=["network", "district_id"], how="inner")
    osm_path = settings.path("interim_dir") / "osm_network_features.csv"
    osm = pd.read_csv(osm_path) if include_osm and osm_path.exists() else None
    featured = add_causal_features(regional, weather, task, osm=osm)
    supervised = make_supervised_table(
        featured,
        task,
        event_threshold=float(settings.values["model"]["event_threshold"]),
        negative_ratio=int(settings.values["features"]["negative_to_positive_ratio"]),
        max_positive=int(
            settings.values["features"][
                "day_max_positive_per_district_horizon"
                if task_name == "day_ahead"
                else "hour_max_positive_per_district_horizon"
            ]
        ),
        minimum_negative=int(
            settings.values["features"]["minimum_negative_per_district_horizon"]
        ),
        seed=int(settings.values["project"]["random_seed"]),
    )
    output = settings.path("processed_dir") / f"{task_name}_training.csv.gz"
    supervised.to_csv(output, index=False, compression="gzip")
    return output
