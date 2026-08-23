from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tech_arena.config import Settings
from tech_arena.phase1.schedules import task_leads, test_issue_times, training_issue_times


WEATHER_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "surface_pressure",
    "wind_speed_10m",
    "wind_gusts_10m",
)


def _load_outages(settings: Settings) -> pd.DataFrame:
    path = settings.path("interim_dir") / "phase1_outages_15min.csv.gz"
    if not path.exists():
        raise FileNotFoundError("Prepare the Phase 1 EAGLE-I data before building features.")
    frame = pd.read_csv(path, dtype={"fips_code": "string"}, parse_dates=["timestamp"])
    frame["fips_code"] = frame["fips_code"].str.zfill(5)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values(["fips_code", "timestamp"]).reset_index(drop=True)


def _history_features(outages: pd.DataFrame) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, group in outages.groupby("fips_code", sort=False):
        group = group.sort_values("timestamp").copy()
        ratio = group["outage_ratio"]
        group["current_x"] = ratio
        for hours in (1, 6, 24, 168):
            group[f"lag_x_{hours}h"] = ratio.shift(hours * 4)
        causal = ratio.shift(1)
        for hours in (6, 24, 168):
            window = hours * 4
            group[f"rolling_mean_x_{hours}h"] = causal.rolling(window, min_periods=1).mean()
            group[f"rolling_max_x_{hours}h"] = causal.rolling(window, min_periods=1).max()
        group["record_coverage_24h"] = (
            group["record_present"].shift(1).rolling(96, min_periods=1).mean()
        )
        parts.append(group)
    return pd.concat(parts, ignore_index=True)


def _candidate_rows(
    history: pd.DataFrame,
    issues: pd.DatetimeIndex,
    leads: list[int],
) -> pd.DataFrame:
    indexed = history.set_index(["timestamp", "fips_code"]).sort_index()
    parts: list[pd.DataFrame] = []
    for issue_time in issues:
        cutoff = issue_time - pd.Timedelta(minutes=15)
        try:
            state = indexed.loc[cutoff].reset_index()
        except KeyError as exc:
            raise ValueError(f"No outage history is available at {cutoff.isoformat()}") from exc
        repeated = state.loc[state.index.repeat(len(leads))].reset_index(drop=True)
        repeated["issue_time"] = issue_time
        repeated["lead_minutes"] = np.tile(leads, len(state))
        repeated["target_time"] = repeated["issue_time"] + pd.to_timedelta(
            repeated["lead_minutes"], unit="m"
        )
        repeated["history_cutoff"] = cutoff
        parts.append(repeated)
    return pd.concat(parts, ignore_index=True)


def _interpolate_weather_group(rows: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    result = rows.copy()
    target_ns = result["target_time"].astype("int64").to_numpy()
    weather = weather.sort_values("weather_time").drop_duplicates("weather_time", keep="last")
    source_ns = weather["weather_time"].astype("int64").to_numpy()
    if not len(source_ns):
        raise ValueError("A required weather group is empty.")
    for variable in WEATHER_VARIABLES:
        values = pd.to_numeric(weather[variable], errors="coerce").interpolate(limit_direction="both")
        numeric = values.to_numpy(dtype=float)
        if variable == "precipitation":
            positions = np.searchsorted(source_ns, target_ns, side="right") - 1
            positions = np.clip(positions, 0, len(source_ns) - 1)
            result[variable] = numeric[positions]
        else:
            result[variable] = np.interp(target_ns, source_ns, numeric)
    return result


def _attach_training_weather(settings: Settings, rows: pd.DataFrame) -> pd.DataFrame:
    path = settings.path("interim_dir") / "phase1_weather_training.csv.gz"
    weather = pd.read_csv(path, dtype={"fips_code": "string"}, parse_dates=["weather_time"])
    weather["fips_code"] = weather["fips_code"].str.zfill(5)
    parts = []
    for fips, group in rows.groupby("fips_code", sort=False):
        parts.append(_interpolate_weather_group(group, weather.loc[weather["fips_code"] == fips]))
    return pd.concat(parts, ignore_index=True)


def _attach_forecast_weather(settings: Settings, rows: pd.DataFrame) -> pd.DataFrame:
    path = settings.path("interim_dir") / "phase1_weather_single_runs.csv.gz"
    weather = pd.read_csv(
        path,
        dtype={"fips_code": "string"},
        parse_dates=["weather_time", "model_run_time"],
    )
    weather["fips_code"] = weather["fips_code"].str.zfill(5)
    lag = pd.Timedelta(hours=int(settings.values["phase1"]["forecast_availability_lag_hours"]))
    rows = rows.copy()
    rows["model_run_time"] = rows["issue_time"] - lag
    parts = []
    for (run_time, fips), group in rows.groupby(["model_run_time", "fips_code"], sort=False):
        match = weather.loc[
            (weather["model_run_time"] == run_time) & (weather["fips_code"] == fips)
        ]
        parts.append(_interpolate_weather_group(group, match))
    return pd.concat(parts, ignore_index=True)


def _add_calendar_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    hour = frame["target_time"].dt.hour + frame["target_time"].dt.minute / 60
    day = frame["target_time"].dt.dayofyear
    frame["target_hour_sin"] = np.sin(2 * np.pi * hour / 24)
    frame["target_hour_cos"] = np.cos(2 * np.pi * hour / 24)
    frame["target_year_sin"] = np.sin(2 * np.pi * day / 365.25)
    frame["target_year_cos"] = np.cos(2 * np.pi * day / 365.25)
    return frame


def build_phase1_features(
    settings: Settings,
    task_id: str,
    purpose: str = "training",
) -> dict[str, Any]:
    outages = _load_outages(settings)
    history = _history_features(outages)
    if purpose == "training":
        issues = training_issue_times(settings, task_id)
    elif purpose == "test":
        issues = test_issue_times(settings, task_id)
    else:
        raise ValueError("purpose must be 'training' or 'test'")
    rows = _candidate_rows(history, issues, task_leads(task_id))

    if purpose == "training":
        target = outages[["fips_code", "timestamp", "outage_ratio"]].rename(
            columns={"timestamp": "target_time", "outage_ratio": "target_x"}
        )
        rows = rows.merge(target, on=["fips_code", "target_time"], how="left", validate="many_to_one")
        rows = rows.dropna(subset=["target_x"]).copy()
        threshold = float(settings.values["phase1"]["event_threshold"])
        rows["target_event"] = (rows["target_x"] >= threshold).astype("int8")
        rows = _attach_training_weather(settings, rows)
    else:
        rows = _attach_forecast_weather(settings, rows)

    rows["task_id"] = task_id
    rows = _add_calendar_features(rows)
    keep = [
        "task_id",
        "fips_code",
        "county",
        "state",
        "issue_time",
        "target_time",
        "history_cutoff",
        "lead_minutes",
        "current_x",
        "lag_x_1h",
        "lag_x_6h",
        "lag_x_24h",
        "lag_x_168h",
        "rolling_mean_x_6h",
        "rolling_max_x_6h",
        "rolling_mean_x_24h",
        "rolling_max_x_24h",
        "rolling_mean_x_168h",
        "rolling_max_x_168h",
        "record_coverage_24h",
        *WEATHER_VARIABLES,
        "target_hour_sin",
        "target_hour_cos",
        "target_year_sin",
        "target_year_cos",
    ]
    if purpose == "test":
        keep.insert(7, "model_run_time")
    else:
        keep.extend(["target_x", "target_event"])
    rows = rows[keep].sort_values(["issue_time", "fips_code", "target_time"]).reset_index(drop=True)
    destination = settings.path("processed_dir") / f"phase1_{task_id}_{purpose}.csv.gz"
    rows.to_csv(destination, index=False, compression="gzip")
    return {
        "path": str(destination),
        "rows": int(len(rows)),
        "issues": int(rows["issue_time"].nunique()),
        "counties": int(rows["fips_code"].nunique()),
        "event_rate": float(rows["target_event"].mean()) if purpose == "training" else None,
    }
