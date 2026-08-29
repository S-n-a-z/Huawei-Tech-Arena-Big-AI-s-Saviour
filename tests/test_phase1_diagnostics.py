from __future__ import annotations

import pandas as pd
import pytest

from tech_arena.phase1.diagnostics import _lead_band, _summarise_errors


def test_lead_bands_cover_both_phase1_tasks() -> None:
    task_a = _lead_band("A", pd.Series([60, 720, 780, 1440, 1500, 2160, 2220, 2880]))
    task_b = _lead_band("B", pd.Series([15, 90, 105, 180, 195, 270, 285, 360]))
    assert task_a.astype(str).tolist() == [
        "1-12 h",
        "1-12 h",
        "13-24 h",
        "13-24 h",
        "25-36 h",
        "25-36 h",
        "37-48 h",
        "37-48 h",
    ]
    assert task_b.astype(str).tolist() == [
        "15-90 min",
        "15-90 min",
        "105-180 min",
        "105-180 min",
        "195-270 min",
        "195-270 min",
        "285-360 min",
        "285-360 min",
    ]


def test_error_summary_reports_relative_improvement() -> None:
    frame = pd.DataFrame(
        {
            "county": ["Example", "Example"],
            "selected_abs_error": [0.1, 0.2],
            "persistence_abs_error": [0.2, 0.4],
        }
    )
    summary = _summarise_errors(frame, "county")
    assert summary[0]["selected_mae"] == pytest.approx(0.15)
    assert summary[0]["persistence_mae"] == pytest.approx(0.3)
    assert summary[0]["improvement_percent"] == pytest.approx(50.0)
