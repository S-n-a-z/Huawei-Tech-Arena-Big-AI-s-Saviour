from __future__ import annotations

from datetime import timedelta

import pandas as pd

from tech_arena.config import Settings


def task_leads(task_id: str) -> list[int]:
    if task_id == "A":
        return [60 * value for value in range(1, 49)]
    if task_id == "B":
        return [15 * value for value in range(1, 25)]
    raise ValueError(f"Unknown Phase 1 task: {task_id}")


def training_issue_times(settings: Settings, task_id: str) -> pd.DatetimeIndex:
    config = settings.values["phase1"]
    start = pd.Timestamp(config["training_start"]) + timedelta(days=7)
    end = pd.Timestamp(config["training_end"])
    if task_id == "A":
        issue_offset = timedelta(hours=int(config["task_a_issue_hour_utc"]))
        first = start.normalize() + issue_offset
        last = (end - timedelta(hours=48)).normalize() + issue_offset
        return pd.date_range(first, last, freq="1D", tz="UTC")
    if task_id == "B":
        first = start.ceil("6h")
        last = (end - timedelta(hours=6)).floor("6h")
        return pd.date_range(first, last, freq="6h", tz="UTC")
    raise ValueError(f"Unknown Phase 1 task: {task_id}")


def test_issue_times(settings: Settings, task_id: str) -> pd.DatetimeIndex:
    config = settings.values["phase1"]
    start = pd.Timestamp(config["test_start"])
    end = pd.Timestamp(config["test_end"])
    if task_id == "A":
        # The preceding issue is included so the first scoring-day timestamps are covered.
        issue_offset = timedelta(hours=int(config["task_a_issue_hour_utc"]))
        first = start.normalize() - timedelta(days=1) + issue_offset
        last = end.normalize() + issue_offset
        return pd.date_range(first, last, freq="1D", tz="UTC")
    if task_id == "B":
        # A 6-hourly rolling batch immediately before the window covers 00:00 UTC.
        first = start.floor("6h") - timedelta(hours=6)
        last = end.floor("6h")
        return pd.date_range(first, last, freq="6h", tz="UTC")
    raise ValueError(f"Unknown Phase 1 task: {task_id}")


def required_forecast_runs(settings: Settings) -> pd.DatetimeIndex:
    lag = timedelta(hours=int(settings.values["phase1"]["forecast_availability_lag_hours"]))
    issues = test_issue_times(settings, "A").append(test_issue_times(settings, "B")).unique()
    return pd.DatetimeIndex(sorted(issues - lag))
