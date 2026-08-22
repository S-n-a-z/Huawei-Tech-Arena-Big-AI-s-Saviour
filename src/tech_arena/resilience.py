from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from tech_arena.config import Settings


OUTPUT_COLUMNS = [
    "issue_time",
    "target_time",
    "network",
    "district_id",
    "lead_minutes",
    "architecture_id",
    "architecture_name",
    "regional_risk_prediction",
    "site_risk_score",
    "critical_load_coverage_ratio",
    "estimated_backup_duration_hours",
]


def expected_leads(task_name: str) -> list[int]:
    if task_name == "day_ahead":
        return list(range(60, 48 * 60 + 1, 60))
    if task_name == "hour_ahead":
        return list(range(5, 6 * 60 + 1, 5))
    raise ValueError(f"Unknown task: {task_name}")


def validate_submission_frame(
    frame: pd.DataFrame,
    settings: Settings,
    task_name: str,
) -> dict[str, object]:
    missing = set(OUTPUT_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Prediction output is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Prediction output is empty.")

    architecture_ids = {
        item["topology_id"] for item in settings.values["resilience"]["topologies"]
    }
    actual_architectures = set(frame["architecture_id"].dropna().astype(str))
    if actual_architectures != architecture_ids:
        raise ValueError(
            "Prediction output does not contain exactly the configured architectures."
        )

    actual_leads = sorted(frame["lead_minutes"].dropna().astype(int).unique().tolist())
    if actual_leads != expected_leads(task_name):
        raise ValueError(f"Unexpected lead times for {task_name}: {actual_leads}")

    probability_columns = [
        "regional_risk_prediction",
        "site_risk_score",
        "critical_load_coverage_ratio",
    ]
    for column in probability_columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not values.between(0, 1).all():
            raise ValueError(f"{column} must contain finite values between zero and one.")

    backup = pd.to_numeric(frame["estimated_backup_duration_hours"], errors="coerce")
    if backup.isna().any() or (backup < 0).any():
        raise ValueError("Backup-duration values must be finite and non-negative.")

    key = [
        "issue_time",
        "target_time",
        "network",
        "district_id",
        "lead_minutes",
        "architecture_id",
    ]
    if frame.duplicated(key).any():
        raise ValueError("Prediction output contains duplicate forecast rows.")

    group_sizes = frame.groupby(["network", "district_id"], dropna=False).size()
    expected_rows = len(actual_leads) * len(architecture_ids)
    if not (group_sizes == expected_rows).all():
        raise ValueError(
            "Every district must contain one row for each lead time and architecture."
        )

    return {
        "task": task_name,
        "rows": int(len(frame)),
        "districts": int(frame[["network", "district_id"]].drop_duplicates().shape[0]),
        "architectures": sorted(architecture_ids),
        "lead_count": len(actual_leads),
        "minimum_target_time": str(pd.to_datetime(frame["target_time"], utc=True).min()),
        "maximum_target_time": str(pd.to_datetime(frame["target_time"], utc=True).max()),
    }


def site_risk(regional_outage_prop: np.ndarray, k: float, x0: float) -> np.ndarray:
    values = np.clip(k * (regional_outage_prop - x0), -40, 40)
    return 1 / (1 + np.exp(-values))


def apply_resilience_rules(
    predictions: pd.DataFrame,
    settings: Settings,
    critical_load_kw: float | None = None,
) -> pd.DataFrame:
    load_kw = critical_load_kw or float(settings.values["resilience"]["default_critical_load_kw"])
    frames: list[pd.DataFrame] = []
    for topology in settings.values["resilience"]["topologies"]:
        frame = predictions.copy()
        risk = site_risk(
            frame["regional_risk_prediction"].to_numpy(dtype=float),
            float(topology["k"]),
            float(topology["x0"]),
        )
        coverage = np.clip(
            float(topology["redundancy_factor"]) * (1 - risk),
            0,
            float(topology["coverage_cap"]),
        )
        protected_load = np.maximum(load_kw * coverage, 1e-6)
        battery_hours = float(topology["usable_energy_kwh"]) / protected_load
        backup_hours = coverage * (battery_hours + float(topology["generator_hours"]))
        frame["architecture_id"] = topology["topology_id"]
        frame["architecture_name"] = topology["display_name"]
        frame["site_risk_score"] = risk
        frame["critical_load_coverage_ratio"] = coverage
        frame["estimated_backup_duration_hours"] = np.clip(backup_hours, 0, 168)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _latest_regional_predictions(settings: Settings, task_name: str) -> pd.DataFrame:
    artifact_dir = settings.path("artifact_dir") / task_name
    cache = artifact_dir / "latest_regional_predictions.csv"
    training_path = settings.path("processed_dir") / f"{task_name}_training.csv.gz"
    model_path = artifact_dir / "hurdle_model.joblib"
    if (
        cache.exists()
        and cache.stat().st_mtime >= training_path.stat().st_mtime
        and cache.stat().st_mtime >= model_path.stat().st_mtime
    ):
        return pd.read_csv(cache)
    training = pd.read_csv(
        training_path,
        parse_dates=["issue_time", "target_time"],
    )
    latest_indices = training.groupby(
        ["network", "district_id", "lead_minutes"], sort=True
    )["issue_time"].idxmax()
    latest = training.loc[latest_indices].copy()
    model = joblib.load(model_path)
    predictions = latest[
        ["issue_time", "target_time", "network", "district_id", "lead_minutes"]
    ].copy()
    predictions["regional_risk_prediction"] = model.predict(latest)
    predictions["event_probability"] = model.predict_event_probability(latest)
    predictions.to_csv(cache, index=False)
    return predictions


def export_submission(settings: Settings, task_name: str) -> str:
    predictions = _latest_regional_predictions(settings, task_name)
    submission = apply_resilience_rules(predictions, settings)
    output = settings.path("output_dir") / f"{task_name}_predictions.csv"
    output_frame = submission[OUTPUT_COLUMNS].sort_values(
        ["network", "district_id", "lead_minutes", "architecture_id"],
        kind="stable",
    )
    summary = validate_submission_frame(output_frame, settings, task_name)
    output_frame.to_csv(output, index=False)
    summary["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    summary["parameter_status"] = settings.values["resilience"].get(
        "parameter_status", "unspecified"
    )
    manifest = settings.path("output_dir") / f"{task_name}_manifest.json"
    manifest.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return str(output)


def validate_submission_file(settings: Settings, task_name: str) -> dict[str, object]:
    path = settings.path("output_dir") / f"{task_name}_predictions.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing prediction file: {path}")
    frame = pd.read_csv(path)
    summary = validate_submission_frame(frame, settings, task_name)
    summary["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return summary
