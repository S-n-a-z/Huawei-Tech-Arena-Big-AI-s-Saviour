from __future__ import annotations

import pandas as pd
import pytest

from tech_arena.config import load_settings
from tech_arena.resilience import (
    apply_resilience_rules,
    expected_leads,
    validate_submission_frame,
)


def _regional_rows(task: str) -> pd.DataFrame:
    issue = pd.Timestamp("2026-08-01T00:00:00Z")
    return pd.DataFrame(
        {
            "issue_time": issue,
            "target_time": [
                issue + pd.Timedelta(int(value), unit="m") for value in expected_leads(task)
            ],
            "network": "SEPD",
            "district_id": "ALDE",
            "lead_minutes": expected_leads(task),
            "regional_risk_prediction": 0.05,
        }
    )


@pytest.mark.parametrize("task", ["day_ahead", "hour_ahead"])
def test_complete_submission_passes(task: str) -> None:
    settings = load_settings()
    output = apply_resilience_rules(_regional_rows(task), settings)
    summary = validate_submission_frame(output, settings, task)
    assert summary["districts"] == 1
    assert summary["lead_count"] == len(expected_leads(task))


def test_duplicate_submission_row_is_rejected() -> None:
    settings = load_settings()
    output = apply_resilience_rules(_regional_rows("day_ahead"), settings)
    duplicated = pd.concat([output, output.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        validate_submission_frame(duplicated, settings, "day_ahead")
