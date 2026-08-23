from __future__ import annotations

from typing import Any

from tech_arena.config import Settings
from tech_arena.phase1.data import download_phase1_data, prepare_phase1_outages
from tech_arena.phase1.features import build_phase1_features
from tech_arena.phase1.model import train_phase1_task
from tech_arena.phase1.submission import export_phase1_submission
from tech_arena.phase1.weather import download_phase1_weather


def run_phase1(settings: Settings, force_download: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["downloads"] = download_phase1_data(settings, force=force_download)
    result["outages"] = prepare_phase1_outages(settings)
    result["weather"] = download_phase1_weather(settings, mode="all", force=force_download)
    result["training_features"] = {
        task: build_phase1_features(settings, task, purpose="training") for task in ("A", "B")
    }
    result["metrics"] = {task: train_phase1_task(settings, task) for task in ("A", "B")}
    result["test_features"] = {
        task: build_phase1_features(settings, task, purpose="test") for task in ("A", "B")
    }
    result["submission"] = export_phase1_submission(settings)
    return result
