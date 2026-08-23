from __future__ import annotations

import pandas as pd
import pytest

from tech_arena.config import load_settings
from tech_arena.phase1.schedules import task_leads, test_issue_times as phase1_test_issue_times
from tech_arena.phase1.submission import SUBMISSION_COLUMNS, validate_phase1_submission


def _complete_submission() -> pd.DataFrame:
    settings = load_settings()
    parts: list[pd.DataFrame] = []
    for task_id in ("A", "B"):
        leads = task_leads(task_id)
        for issue_time in phase1_test_issue_times(settings, task_id):
            for county in settings.values["phase1"]["counties"]:
                part = pd.DataFrame({"target_time": issue_time + pd.to_timedelta(leads, unit="m")})
                part["task_id"] = task_id
                part["fips_code"] = str(county["fips_code"]).zfill(5)
                part["county"] = county["county"]
                part["state"] = county["state"]
                part["issue_time"] = issue_time
                part["predicted_x"] = 0.001
                parts.append(part)
    frame = pd.concat(parts, ignore_index=True)
    frame["issue_time"] = pd.to_datetime(frame["issue_time"], utc=True).dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    frame["target_time"] = pd.to_datetime(frame["target_time"], utc=True).dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return frame[SUBMISSION_COLUMNS]


def test_phase1_schedule_matches_submission_design() -> None:
    settings = load_settings()
    assert len(task_leads("A")) == 48
    assert task_leads("A")[-1] == 48 * 60
    assert len(task_leads("B")) == 24
    assert task_leads("B")[-1] == 6 * 60
    assert len(phase1_test_issue_times(settings, "A")) == 92
    assert len(phase1_test_issue_times(settings, "B")) == 365


def test_complete_phase1_submission_passes() -> None:
    settings = load_settings()
    frame = _complete_submission()
    result = validate_phase1_submission(frame, settings)
    assert result["rows"] == 65_880
    assert result["complete_county_issue_batches"] == 2_285


def test_phase1_duplicate_key_is_rejected() -> None:
    settings = load_settings()
    frame = _complete_submission()
    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        validate_phase1_submission(duplicated, settings)
