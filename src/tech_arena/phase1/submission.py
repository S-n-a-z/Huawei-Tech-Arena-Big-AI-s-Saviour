from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from tech_arena.config import Settings
from tech_arena.phase1.schedules import task_leads


SUBMISSION_COLUMNS = [
    "task_id",
    "fips_code",
    "county",
    "state",
    "issue_time",
    "target_time",
    "predicted_x",
]

FROZEN_INFERENCE_MANIFEST = Path("artifacts/phase1/inference_manifest.json")


def _iso_utc(values: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(values, utc=True)
    return timestamps.dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _submission_frame(parts: list[pd.DataFrame]) -> pd.DataFrame:
    combined = pd.concat(parts, ignore_index=True)
    combined["fips_code"] = combined["fips_code"].astype(str).str.zfill(5)
    combined["issue_time"] = _iso_utc(combined["issue_time"])
    combined["target_time"] = _iso_utc(combined["target_time"])
    return combined[SUBMISSION_COLUMNS].sort_values(
        ["task_id", "issue_time", "fips_code", "target_time"]
    ).reset_index(drop=True)


def _predict_task(features_path: Path, model_path: Path) -> pd.DataFrame:
    features = pd.read_csv(
        features_path,
        dtype={"fips_code": "string"},
        parse_dates=["issue_time", "target_time", "history_cutoff", "model_run_time"],
    )
    model = joblib.load(model_path)
    output = features[
        ["task_id", "fips_code", "county", "state", "issue_time", "target_time"]
    ].copy()
    output["predicted_x"] = np.round(model.predict(features), 8)
    return output


def _verify_frozen_file(root: Path, item: dict[str, Any]) -> Path:
    path = root / str(item["path"])
    if not path.is_file():
        raise FileNotFoundError(f"Frozen inference file is missing: {item['path']}")
    expected_size = int(item["bytes"])
    if path.stat().st_size != expected_size:
        raise ValueError(f"Frozen inference file has the wrong size: {item['path']}")
    expected_hash = str(item["sha256"])
    if _sha256(path) != expected_hash:
        raise ValueError(f"Frozen inference file failed its SHA-256 check: {item['path']}")
    return path


def validate_phase1_submission(frame: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    if list(frame.columns) != SUBMISSION_COLUMNS:
        raise ValueError(f"Submission columns must be exactly {SUBMISSION_COLUMNS}")
    if frame.empty:
        raise ValueError("Submission is empty.")
    if frame[SUBMISSION_COLUMNS].isna().any().any():
        raise ValueError("Submission contains missing values.")
    if set(frame["task_id"]) != {"A", "B"}:
        raise ValueError("Submission must contain both Task A and Task B.")
    expected_fips = {
        str(county["fips_code"]).zfill(5) for county in settings.values["phase1"]["counties"]
    }
    actual_fips = set(frame["fips_code"].astype(str).str.zfill(5))
    if actual_fips != expected_fips:
        raise ValueError("Submission does not contain exactly the five configured counties.")
    keys = ["task_id", "fips_code", "issue_time", "target_time"]
    if frame.duplicated(keys).any():
        raise ValueError("Submission contains duplicate forecast keys.")
    predicted = pd.to_numeric(frame["predicted_x"], errors="coerce")
    if predicted.isna().any() or not predicted.between(0, 1).all():
        raise ValueError("predicted_x must be numeric and bounded by 0 and 1.")

    issue = pd.to_datetime(frame["issue_time"], utc=True)
    target = pd.to_datetime(frame["target_time"], utc=True)
    lead = ((target - issue).dt.total_seconds() / 60).astype(int)
    checked_batches = 0
    check = frame.assign(_lead=lead)
    for (task_id, _fips, _issue), group in check.groupby(
        ["task_id", "fips_code", "issue_time"], sort=False
    ):
        if sorted(group["_lead"].tolist()) != task_leads(str(task_id)):
            raise ValueError(f"Incomplete {task_id} horizon in a county/issue batch.")
        checked_batches += 1

    test_start = pd.Timestamp(settings.values["phase1"]["test_start"])
    test_end = pd.Timestamp(settings.values["phase1"]["test_end"])
    scoring = check.loc[(target >= test_start) & (target <= test_end)]
    for task_id, cadence in (("A", "1h"), ("B", "15min")):
        expected_targets = pd.date_range(test_start, test_end, freq=cadence, tz="UTC")
        covered = pd.DatetimeIndex(
            pd.to_datetime(scoring.loc[scoring["task_id"] == task_id, "target_time"], utc=True).unique()
        )
        missing = expected_targets.difference(covered)
        if len(missing):
            raise ValueError(f"Task {task_id} misses {len(missing)} scoring timestamps.")
    return {
        "rows": int(len(frame)),
        "task_a_rows": int((frame["task_id"] == "A").sum()),
        "task_b_rows": int((frame["task_id"] == "B").sum()),
        "counties": len(expected_fips),
        "complete_county_issue_batches": checked_batches,
        "minimum_prediction": float(predicted.min()),
        "maximum_prediction": float(predicted.max()),
    }


def export_phase1_submission(settings: Settings) -> dict[str, Any]:
    parts: list[pd.DataFrame] = []
    for task_id in ("A", "B"):
        features_path = settings.path("processed_dir") / f"phase1_{task_id}_test.csv.gz"
        model_path = settings.path("artifact_dir") / "phase1" / task_id / "model.joblib"
        parts.append(_predict_task(features_path, model_path))
    combined = _submission_frame(parts)
    validation = validate_phase1_submission(combined, settings)
    destination = settings.path("output_dir") / "predictions.csv"
    combined.to_csv(destination, index=False)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest = {
        **validation,
        "file": destination.name,
        "sha256": digest,
        "schema": SUBMISSION_COLUMNS,
        "task_a_resolution": "1 hour",
        "task_b_resolution": "15 minutes",
        "forecast_weather": "Open-Meteo Single Runs, ECMWF IFS HRES, six-hour availability lag",
    }
    manifest_path = settings.path("output_dir") / "predictions_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {**manifest, "path": str(destination), "manifest": str(manifest_path)}


def reproduce_phase1_submission(
    settings: Settings,
    destination: str | Path = "outputs/reproduced_predictions.csv",
) -> dict[str, Any]:
    """Run inference with the exact frozen artefacts used for the submitted CSV."""
    manifest_path = settings.root / FROZEN_INFERENCE_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Frozen inference manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    parts: list[pd.DataFrame] = []
    for task_id in ("A", "B"):
        task = manifest["tasks"][task_id]
        model_path = _verify_frozen_file(settings.root, task["model"])
        features_path = _verify_frozen_file(settings.root, task["features"])
        parts.append(_predict_task(features_path, model_path))

    combined = _submission_frame(parts)
    validation = validate_phase1_submission(combined, settings)
    output_path = Path(destination)
    if not output_path.is_absolute():
        output_path = settings.root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)

    digest = _sha256(output_path)
    expected = str(manifest["submitted_predictions"]["sha256"])
    if digest != expected:
        raise ValueError(
            "Frozen inference completed, but the generated CSV does not match the submitted file. "
            "Install the pinned environment from requirements-lock.txt and try again."
        )
    return {
        **validation,
        "path": str(output_path),
        "sha256": digest,
        "matches_submitted_predictions": True,
    }


def validate_phase1_file(settings: Settings, path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else settings.path("output_dir") / "predictions.csv"
    frame = pd.read_csv(source, dtype={"fips_code": "string"})
    result = validate_phase1_submission(frame, settings)
    result["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    return result
