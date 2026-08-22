from __future__ import annotations

import pandas as pd

from tech_arena.features import TaskDefinition, add_causal_features


def test_five_minute_weather_is_forward_filled_causally() -> None:
    timestamps = pd.date_range("2026-01-01", periods=13, freq="5min", tz="UTC")
    regional = pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "network": "SEPD",
            "district_id": "A",
            "active_customers": 0.0,
            "active_incidents": 0.0,
            "exposure_proxy": 100.0,
            "regional_outage_prop": 0.0,
        }
    )
    weather = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"]),
            "network": ["SEPD", "SEPD"],
            "wx_mean_wind_gusts_10m": [10.0, 90.0],
        }
    )
    task = TaskDefinition("hour_ahead", "5min", 1, 60, 5, (1,), (3,))
    result = add_causal_features(regional, weather, task)
    at_0055 = result.loc[result["timestamp_utc"] == pd.Timestamp("2026-01-01T00:55:00Z")]
    assert at_0055["wx_mean_wind_gusts_10m"].item() == 10.0


def test_lag_does_not_use_current_target() -> None:
    timestamps = pd.date_range("2026-01-01", periods=4, freq="1h", tz="UTC")
    regional = pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "network": "SEPD",
            "district_id": "A",
            "active_customers": [0, 10, 20, 30],
            "active_incidents": [0, 1, 1, 1],
            "exposure_proxy": 100.0,
            "regional_outage_prop": [0.0, 0.1, 0.2, 0.3],
        }
    )
    weather = pd.DataFrame(
        {"timestamp_utc": timestamps, "network": "SEPD", "wx_mean_temperature_2m": 10.0}
    )
    task = TaskDefinition("day_ahead", "1h", 1, 60, 60, (1,), (2,))
    result = add_causal_features(regional, weather, task)
    assert result.loc[2, "risk_lag_1"] == 0.1

