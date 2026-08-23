from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from tech_arena.config import Settings
from tech_arena.phase1.features import WEATHER_VARIABLES


IDENTITY_COLUMNS = {
    "task_id",
    "county",
    "state",
    "issue_time",
    "target_time",
    "history_cutoff",
    "model_run_time",
    "target_x",
    "target_event",
}


def _target_transform(values: np.ndarray) -> np.ndarray:
    return np.log1p(np.clip(values, 0, 1) * 1000.0)


def _target_inverse(values: np.ndarray) -> np.ndarray:
    return np.clip(np.expm1(values) / 1000.0, 0, 1)


@dataclass
class Phase1Forecaster:
    classifier: Pipeline
    regressor: Pipeline
    feature_columns: list[str]
    persistence_weight: float

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        learned = _target_inverse(self.regressor.predict(frame[self.feature_columns]))
        persistence = frame["current_x"].to_numpy(dtype=float)
        return np.clip(
            (1.0 - self.persistence_weight) * learned + self.persistence_weight * persistence,
            0,
            1,
        )

    def event_probability(self, frame: pd.DataFrame) -> np.ndarray:
        return self.classifier.predict_proba(frame[self.feature_columns])[:, 1]


def _preprocessor(columns: list[str]) -> ColumnTransformer:
    categorical = ["fips_code"] if "fips_code" in columns else []
    numeric = [column for column in columns if column not in categorical]
    return ColumnTransformer(
        [
            ("numeric", SimpleImputer(strategy="median", add_indicator=True), numeric),
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


def _build_models(settings: Settings, columns: list[str]) -> tuple[Pipeline, Pipeline]:
    config = settings.values["model"]
    seed = int(settings.values["project"]["random_seed"])
    classifier = Pipeline(
        [
            ("preprocess", _preprocessor(columns)),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=float(config["learning_rate"]),
                    max_iter=int(config["classifier_max_iter"]),
                    max_leaf_nodes=int(config["max_leaf_nodes"]),
                    min_samples_leaf=int(config["min_samples_leaf"]),
                    random_state=seed,
                ),
            ),
        ]
    )
    regressor = Pipeline(
        [
            ("preprocess", _preprocessor(columns)),
            (
                "model",
                HistGradientBoostingRegressor(
                    learning_rate=float(config["learning_rate"]),
                    max_iter=int(config["regressor_max_iter"]),
                    max_leaf_nodes=int(config["max_leaf_nodes"]),
                    min_samples_leaf=int(config["min_samples_leaf"]),
                    loss="squared_error",
                    random_state=seed,
                ),
            ),
        ]
    )
    return classifier, regressor


def _fit(
    settings: Settings,
    frame: pd.DataFrame,
    columns: list[str],
) -> tuple[Pipeline, Pipeline]:
    classifier, regressor = _build_models(settings, columns)
    events = frame["target_event"].to_numpy(dtype=int)
    positive = max(int(events.sum()), 1)
    negative = max(len(events) - positive, 1)
    classifier_weights = np.where(events == 1, negative / positive, 1.0)
    classifier.fit(frame[columns], events, model__sample_weight=classifier_weights)
    regression_weights = np.where(events == 1, 6.0, 1.0)
    regressor.fit(
        frame[columns],
        _target_transform(frame["target_x"].to_numpy(dtype=float)),
        model__sample_weight=regression_weights,
    )
    return classifier, regressor


def _split(frame: pd.DataFrame, task_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    issues = np.sort(frame["issue_time"].unique())
    split_at = max(1, int(len(issues) * 0.8))
    validation_start = pd.Timestamp(issues[split_at])
    purge = pd.Timedelta(hours=48 if task_id == "A" else 6)
    train = frame.loc[frame["target_time"] < validation_start - purge].copy()
    validation = frame.loc[frame["issue_time"] >= validation_start].copy()
    if train.empty or validation.empty:
        raise RuntimeError("The chronological Phase 1 split is empty.")
    return train, validation


def _metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    high_risk = truth >= np.quantile(truth, 0.9)
    return {
        "mae": float(mean_absolute_error(truth, prediction)),
        "rmse": float(mean_squared_error(truth, prediction) ** 0.5),
        "high_risk_mae": float(mean_absolute_error(truth[high_risk], prediction[high_risk])),
    }


def _feature_columns(frame: pd.DataFrame, include_weather: bool = True) -> list[str]:
    columns = [column for column in frame.columns if column not in IDENTITY_COLUMNS]
    if not include_weather:
        columns = [column for column in columns if column not in WEATHER_VARIABLES]
    return columns


def train_phase1_task(settings: Settings, task_id: str) -> dict[str, Any]:
    path = settings.path("processed_dir") / f"phase1_{task_id}_training.csv.gz"
    frame = pd.read_csv(
        path,
        dtype={"fips_code": "string"},
        parse_dates=["issue_time", "target_time", "history_cutoff"],
    )
    train, validation = _split(frame, task_id)
    columns = _feature_columns(frame)
    classifier, regressor = _fit(settings, train, columns)
    learned = _target_inverse(regressor.predict(validation[columns]))
    persistence = validation["current_x"].to_numpy(dtype=float)
    truth = validation["target_x"].to_numpy(dtype=float)

    candidates = np.linspace(0.0, 1.0, 11)
    errors = {
        float(weight): float(mean_absolute_error(truth, (1 - weight) * learned + weight * persistence))
        for weight in candidates
    }
    persistence_weight = min(errors, key=errors.get)
    selected = np.clip(
        (1 - persistence_weight) * learned + persistence_weight * persistence,
        0,
        1,
    )

    event_probability = classifier.predict_proba(validation[columns])[:, 1]
    try:
        event_pr_auc = float(average_precision_score(validation["target_event"], event_probability))
    except ValueError:
        event_pr_auc = float("nan")

    history_columns = _feature_columns(frame, include_weather=False)
    _, history_regressor = _fit(settings, train, history_columns)
    history_prediction = _target_inverse(history_regressor.predict(validation[history_columns]))

    metrics: dict[str, Any] = {
        "task_id": task_id,
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "train_start": train["target_time"].min().isoformat(),
        "validation_start": validation["target_time"].min().isoformat(),
        "event_threshold": float(settings.values["phase1"]["event_threshold"]),
        "validation_event_rate": float(validation["target_event"].mean()),
        "event_pr_auc": event_pr_auc,
        "selected_persistence_weight": float(persistence_weight),
        "selected": _metrics(truth, selected),
        "weather_model_unblended": _metrics(truth, learned),
        "history_only_ablation": _metrics(truth, history_prediction),
        "persistence_baseline": _metrics(truth, persistence),
    }

    final_classifier, final_regressor = _fit(settings, frame, columns)
    forecaster = Phase1Forecaster(
        classifier=final_classifier,
        regressor=final_regressor,
        feature_columns=columns,
        persistence_weight=float(persistence_weight),
    )
    artifact_dir = settings.path("artifact_dir") / "phase1" / task_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(forecaster, artifact_dir / "model.joblib")
    (artifact_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    validation_output = validation[
        ["fips_code", "county", "state", "issue_time", "target_time", "target_x"]
    ].copy()
    validation_output["predicted_x"] = selected
    validation_output["event_probability"] = event_probability
    validation_output.to_csv(
        artifact_dir / "validation_predictions.csv.gz", index=False, compression="gzip"
    )
    return metrics
