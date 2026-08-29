from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tech_arena.config import Settings
from tech_arena.phase1.model import _split


KEY_COLUMNS = ["fips_code", "issue_time", "target_time"]


def _summarise_errors(frame: pd.DataFrame, group_column: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for value, group in frame.groupby(group_column, sort=False, observed=True):
        selected_mae = float(group["selected_abs_error"].mean())
        persistence_mae = float(group["persistence_abs_error"].mean())
        improvement = (
            100.0 * (persistence_mae - selected_mae) / persistence_mae
            if persistence_mae > 0
            else 0.0
        )
        records.append(
            {
                group_column: str(value),
                "rows": int(len(group)),
                "selected_mae": selected_mae,
                "persistence_mae": persistence_mae,
                "improvement_percent": improvement,
            }
        )
    return records


def _lead_band(task_id: str, leads: pd.Series) -> pd.Series:
    if task_id == "A":
        hours = leads / 60.0
        return pd.cut(
            hours,
            bins=[0, 12, 24, 36, 48],
            labels=["1-12 h", "13-24 h", "25-36 h", "37-48 h"],
            include_lowest=True,
        )
    return pd.cut(
        leads,
        bins=[0, 90, 180, 270, 360],
        labels=["15-90 min", "105-180 min", "195-270 min", "285-360 min"],
        include_lowest=True,
    )


def _validation_frame(
    settings: Settings,
    task_id: str,
    *,
    rebuild: bool = False,
) -> pd.DataFrame:
    detailed_path = (
        settings.path("artifact_dir")
        / "phase1"
        / task_id
        / "validation_diagnostics.csv.gz"
    )
    if detailed_path.is_file() and not rebuild:
        recorded = pd.read_csv(
            detailed_path,
            dtype={"fips_code": "string"},
            parse_dates=["issue_time", "target_time"],
        )
        required = {
            "county",
            "lead_minutes",
            "selected_abs_error",
            "persistence_abs_error",
        }
        missing = required - set(recorded.columns)
        if missing:
            raise ValueError(
                f"Task {task_id} recorded diagnostics are missing: {sorted(missing)}"
            )
        recorded["lead_band"] = _lead_band(task_id, recorded["lead_minutes"])
        return recorded

    training_path = settings.path("processed_dir") / f"phase1_{task_id}_training.csv.gz"
    recorded_path = (
        settings.path("artifact_dir") / "phase1" / task_id / "validation_predictions.csv.gz"
    )
    if not training_path.is_file() or not recorded_path.is_file():
        raise FileNotFoundError(
            "Validation diagnostics require the training features and recorded validation predictions. "
            "Run the full Phase 1 training route first."
        )

    training = pd.read_csv(
        training_path,
        dtype={"fips_code": "string"},
        parse_dates=["issue_time", "target_time", "history_cutoff"],
    )
    _, validation = _split(training, task_id)
    recorded = pd.read_csv(
        recorded_path,
        dtype={"fips_code": "string"},
        parse_dates=["issue_time", "target_time"],
    )
    joined = validation[
        KEY_COLUMNS + ["county", "state", "lead_minutes", "current_x", "target_x"]
    ].merge(
        recorded[KEY_COLUMNS + ["predicted_x"]],
        on=KEY_COLUMNS,
        how="inner",
        validate="one_to_one",
    )
    if len(joined) != len(validation):
        raise ValueError(f"Task {task_id} validation diagnostics do not cover every hold-out row.")

    joined["selected_abs_error"] = np.abs(joined["target_x"] - joined["predicted_x"])
    joined["persistence_abs_error"] = np.abs(joined["target_x"] - joined["current_x"])
    joined["lead_band"] = _lead_band(task_id, joined["lead_minutes"])
    joined.insert(0, "task_id", task_id)
    return joined


def build_phase1_diagnostics(
    settings: Settings,
    destination: str | Path = "reports/phase1_diagnostics.json",
    *,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Export transparent error breakdowns for the recorded chronological hold-outs."""
    result: dict[str, Any] = {"description": "Recorded chronological hold-out diagnostics"}
    for task_id in ("A", "B"):
        frame = _validation_frame(settings, task_id, rebuild=rebuild)
        detailed_path = (
            settings.path("artifact_dir")
            / "phase1"
            / task_id
            / "validation_diagnostics.csv.gz"
        )
        frame.to_csv(detailed_path, index=False, compression="gzip")
        result[task_id] = {
            "rows": int(len(frame)),
            "by_lead_band": _summarise_errors(frame, "lead_band"),
            "by_county": _summarise_errors(frame, "county"),
        }

    output_path = Path(destination)
    if not output_path.is_absolute():
        output_path = settings.root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {"path": str(output_path), **result}
