from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from tech_arena.config import Settings


NON_FEATURE_COLUMNS = {
    "issue_time",
    "target_time",
    "target_regional_outage_prop",
    "target_event",
    "active_customers",
    "active_incidents",
    "exposure_proxy",
}


def _logit(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, 1e-5, 1 - 1e-5)
    return np.log(clipped / (1 - clipped))


def _sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, -40, 40)
    return 1 / (1 + np.exp(-values))


@dataclass
class HurdleForecaster:
    classifier: Pipeline
    regressor: Pipeline
    feature_columns: list[str]
    categorical_columns: list[str]
    event_threshold: float
    persistence_weight: float = 0.2

    def predict_event_probability(self, frame: pd.DataFrame) -> np.ndarray:
        return self.classifier.predict_proba(frame[self.feature_columns])[:, 1]

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        features = frame[self.feature_columns]
        event_probability = self.predict_event_probability(frame)
        conditional_severity = _sigmoid(self.regressor.predict(features))
        mixture = event_probability * conditional_severity
        persistence = frame["regional_outage_prop"].to_numpy(dtype=float)
        return np.clip(
            (1 - self.persistence_weight) * mixture + self.persistence_weight * persistence,
            0,
            1,
        )


def _preprocessor(frame: pd.DataFrame, feature_columns: list[str], categorical: list[str]) -> ColumnTransformer:
    numeric = [column for column in feature_columns if column not in categorical]
    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True))]),
                numeric,
            ),
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        (
                            "encode",
                            OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                        ),
                    ]
                ),
                categorical,
            ),
        ],
        remainder="drop",
    )


def _feature_columns(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    feature_columns = [column for column in frame.columns if column not in NON_FEATURE_COLUMNS]
    categorical = [column for column in ("network", "district_id") if column in feature_columns]
    return feature_columns, categorical


def _time_split(frame: pd.DataFrame, test_fraction: float, purge_minutes: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered_times = np.sort(frame["target_time"].dropna().unique())
    split_index = min(len(ordered_times) - 1, max(1, int(len(ordered_times) * (1 - test_fraction))))
    cutoff = pd.Timestamp(ordered_times[split_index])
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    purge = pd.Timedelta(minutes=purge_minutes)
    train = frame.loc[frame["target_time"] < cutoff - purge].copy()
    test = frame.loc[frame["target_time"] >= cutoff].copy()
    if train.empty or test.empty:
        raise RuntimeError("Chronological split produced an empty train or test set.")
    return train, test


def train_task(settings: Settings, task_name: str) -> dict[str, Any]:
    source = settings.path("processed_dir") / f"{task_name}_training.csv.gz"
    frame = pd.read_csv(source, parse_dates=["issue_time", "target_time"])
    frame["issue_time"] = pd.to_datetime(frame["issue_time"], utc=True)
    frame["target_time"] = pd.to_datetime(frame["target_time"], utc=True)
    model_config = settings.values["model"]
    max_horizon = 48 * 60 if task_name == "day_ahead" else 6 * 60
    train, test = _time_split(frame, float(model_config["test_fraction"]), max_horizon)
    feature_columns, categorical = _feature_columns(frame)
    preprocessor = _preprocessor(frame, feature_columns, categorical)

    classifier = Pipeline(
        [
            ("preprocess", preprocessor),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=float(model_config["learning_rate"]),
                    max_iter=int(model_config["classifier_max_iter"]),
                    max_leaf_nodes=int(model_config["max_leaf_nodes"]),
                    min_samples_leaf=int(model_config["min_samples_leaf"]),
                    random_state=int(settings.values["project"]["random_seed"]),
                ),
            ),
        ]
    )
    positive = train["target_event"].sum()
    negative = len(train) - positive
    positive_weight = negative / max(positive, 1)
    weights = np.where(train["target_event"].to_numpy() == 1, positive_weight, 1.0)
    classifier.fit(train[feature_columns], train["target_event"], model__sample_weight=weights)

    severity_train = train.loc[train["target_event"] == 1]
    if len(severity_train) < 50:
        severity_train = train
    regressor = Pipeline(
        [
            ("preprocess", _preprocessor(frame, feature_columns, categorical)),
            (
                "model",
                HistGradientBoostingRegressor(
                    learning_rate=float(model_config["learning_rate"]),
                    max_iter=int(model_config["regressor_max_iter"]),
                    max_leaf_nodes=int(model_config["max_leaf_nodes"]),
                    min_samples_leaf=int(model_config["min_samples_leaf"]),
                    loss="squared_error",
                    random_state=int(settings.values["project"]["random_seed"]),
                ),
            ),
        ]
    )
    regressor.fit(
        severity_train[feature_columns],
        _logit(severity_train["target_regional_outage_prop"].to_numpy(dtype=float)),
    )

    model = HurdleForecaster(
        classifier=classifier,
        regressor=regressor,
        feature_columns=feature_columns,
        categorical_columns=categorical,
        event_threshold=float(model_config["event_threshold"]),
    )
    predictions = model.predict(test)
    event_scores = model.predict_event_probability(test)
    event_predictions = event_scores >= 0.5
    truth_events = test["target_event"].to_numpy(dtype=int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        truth_events, event_predictions.astype(int), average="binary", zero_division=0
    )
    try:
        pr_auc = average_precision_score(truth_events, event_scores)
    except ValueError:
        pr_auc = float("nan")
    try:
        roc_auc = roc_auc_score(truth_events, event_scores)
    except ValueError:
        roc_auc = float("nan")
    target = test["target_regional_outage_prop"].to_numpy(dtype=float)
    high_risk = target >= np.quantile(target, 0.9)
    metrics = {
        "task": task_name,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_event_rate": float(train["target_event"].mean()),
        "test_event_rate": float(test["target_event"].mean()),
        "mae": float(mean_absolute_error(target, predictions)),
        "rmse": float(mean_squared_error(target, predictions) ** 0.5),
        "high_risk_mae": float(mean_absolute_error(target[high_risk], predictions[high_risk])),
        "event_precision": float(precision),
        "event_recall": float(recall),
        "event_f1": float(f1),
        "event_pr_auc": float(pr_auc),
        "event_roc_auc": float(roc_auc),
        "event_brier_score": float(brier_score_loss(truth_events, event_scores)),
        "split_start": str(test["target_time"].min()),
    }

    artifact_dir = settings.path("artifact_dir") / task_name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact_dir / "hurdle_model.joblib")
    (artifact_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    validation = test[["issue_time", "target_time", "network", "district_id", "lead_minutes"]].copy()
    validation["regional_risk_actual"] = target
    validation["regional_risk_prediction"] = predictions
    validation["event_probability"] = event_scores
    validation.to_csv(artifact_dir / "validation_predictions.csv.gz", index=False, compression="gzip")
    return metrics


def evaluate_persistence(settings: Settings, task_name: str) -> dict[str, Any]:
    source = settings.path("processed_dir") / f"{task_name}_training.csv.gz"
    frame = pd.read_csv(source, parse_dates=["issue_time", "target_time"])
    frame["target_time"] = pd.to_datetime(frame["target_time"], utc=True)
    max_horizon = 48 * 60 if task_name == "day_ahead" else 6 * 60
    _, test = _time_split(
        frame,
        float(settings.values["model"]["test_fraction"]),
        max_horizon,
    )
    target = test["target_regional_outage_prop"].to_numpy(dtype=float)
    predictions = test["regional_outage_prop"].to_numpy(dtype=float)
    threshold = float(settings.values["model"]["event_threshold"])
    truth_events = target > threshold
    event_predictions = predictions > threshold
    precision, recall, f1, _ = precision_recall_fscore_support(
        truth_events.astype(int),
        event_predictions.astype(int),
        average="binary",
        zero_division=0,
    )
    try:
        pr_auc = average_precision_score(truth_events.astype(int), predictions)
    except ValueError:
        pr_auc = float("nan")
    try:
        roc_auc = roc_auc_score(truth_events.astype(int), predictions)
    except ValueError:
        roc_auc = float("nan")
    high_risk = target >= np.quantile(target, 0.9)
    metrics = {
        "task": task_name,
        "test_rows": int(len(test)),
        "mae": float(mean_absolute_error(target, predictions)),
        "rmse": float(mean_squared_error(target, predictions) ** 0.5),
        "high_risk_mae": float(mean_absolute_error(target[high_risk], predictions[high_risk])),
        "event_precision": float(precision),
        "event_recall": float(recall),
        "event_f1": float(f1),
        "event_pr_auc": float(pr_auc),
        "event_roc_auc": float(roc_auc),
        "event_brier_score": float(
            brier_score_loss(truth_events.astype(int), np.clip(predictions, 0, 1))
        ),
    }
    artifact_dir = settings.path("artifact_dir") / task_name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "persistence_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    return metrics
