from __future__ import annotations

import pandas as pd

from tech_arena.data.weather import load_prepared_district_weather


def test_prepared_weather_is_normalised_for_the_model(tmp_path) -> None:
    source = tmp_path / "district_weather.csv"
    pd.DataFrame(
        {
            "network": ["SEPD"],
            "district_id": ["ALDE"],
            "time": ["2026-08-01T00:00:00Z"],
            "temperature_2m_mean": [17.5],
            "wind_gusts_10m_max": [31.0],
        }
    ).to_csv(source, index=False)

    result = load_prepared_district_weather(source)

    assert "wx_temperature_2m_mean" in result.columns
    assert "wx_wind_gusts_10m_max" in result.columns
    assert str(result["timestamp_utc"].dt.tz) == "UTC"
