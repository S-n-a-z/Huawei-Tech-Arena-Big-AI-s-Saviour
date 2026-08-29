from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from typing import Sequence

from tech_arena.config import load_settings
from tech_arena.data.nafirs import download_nafirs, normalize_nafirs, summarize_incidents
from tech_arena.data.locations import derive_district_locations, export_substation_coordinates
from tech_arena.data.osm import download_osm_features
from tech_arena.data.weather import download_historical_weather
from tech_arena.features import build_task_features
from tech_arena.model import evaluate_persistence, train_task
from tech_arena.report import write_mvp_report
from tech_arena.resilience import export_submission, validate_submission_file
from tech_arena.phase1.data import download_phase1_data, prepare_phase1_outages
from tech_arena.phase1.diagnostics import build_phase1_diagnostics
from tech_arena.phase1.features import build_phase1_features
from tech_arena.phase1.model import train_phase1_task
from tech_arena.phase1.pipeline import run_phase1
from tech_arena.phase1.submission import (
    export_phase1_submission,
    reproduce_phase1_submission,
    validate_phase1_file,
)
from tech_arena.phase1.weather import download_phase1_weather


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, default=str))


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="configs/default.toml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Huawei Tech Arena Topic Two local pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    phase1_download = subparsers.add_parser(
        "download-phase1-data", help="Download EAGLE-I, customer-count and Gazetteer sources"
    )
    _add_common(phase1_download)
    phase1_download.add_argument("--force", action="store_true")

    phase1_prepare = subparsers.add_parser(
        "prepare-phase1-data", help="Prepare five-county, 15-minute EAGLE-I history"
    )
    _add_common(phase1_prepare)

    phase1_weather = subparsers.add_parser(
        "download-phase1-weather", help="Download training weather and archived forecast runs"
    )
    _add_common(phase1_weather)
    phase1_weather.add_argument("--mode", choices=("training", "forecast", "all"), default="all")
    phase1_weather.add_argument("--force", action="store_true")

    phase1_features = subparsers.add_parser(
        "build-phase1-features", help="Build leakage-safe Phase 1 feature tables"
    )
    _add_common(phase1_features)
    phase1_features.add_argument("--task", choices=("A", "B", "all"), default="all")
    phase1_features.add_argument("--purpose", choices=("training", "test", "all"), default="all")

    phase1_train = subparsers.add_parser("train-phase1", help="Train the Phase 1 county models")
    _add_common(phase1_train)
    phase1_train.add_argument("--task", choices=("A", "B", "all"), default="all")

    phase1_export = subparsers.add_parser(
        "export-phase1", help="Export the combined organiser-schema predictions.csv"
    )
    _add_common(phase1_export)

    phase1_infer = subparsers.add_parser(
        "infer-phase1",
        help="Reproduce predictions from the submitted frozen models and feature tables",
    )
    _add_common(phase1_infer)
    phase1_infer.add_argument("--output", default="outputs/reproduced_predictions.csv")

    phase1_validate = subparsers.add_parser(
        "validate-phase1", help="Validate Phase 1 schema, batches, horizons and coverage"
    )
    _add_common(phase1_validate)
    phase1_validate.add_argument("--path")

    phase1_diagnostics = subparsers.add_parser(
        "diagnose-phase1",
        help="Export lead-time and county error breakdowns for the chronological hold-outs",
    )
    _add_common(phase1_diagnostics)
    phase1_diagnostics.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild row-level diagnostics from training features and validation predictions",
    )

    phase1_all = subparsers.add_parser(
        "phase1-run-all", help="Run the complete Phase 1 submission pipeline"
    )
    _add_common(phase1_all)
    phase1_all.add_argument("--force-download", action="store_true")

    download = subparsers.add_parser("download-nafirs", help="Download current NaFIRS CSV resources")
    _add_common(download)
    download.add_argument("--force", action="store_true")

    prepare = subparsers.add_parser("prepare-nafirs", help="Normalize NaFIRS incident records")
    _add_common(prepare)

    locations = subparsers.add_parser("prepare-locations", help="Derive district weather coordinates")
    _add_common(locations)
    locations.add_argument("--force-download", action="store_true")

    substations = subparsers.add_parser(
        "export-substations", help="Export unique SSEN substation coordinates in WGS84"
    )
    _add_common(substations)
    substations.add_argument("--force-download", action="store_true")

    weather = subparsers.add_parser("download-weather", help="Download Open-Meteo history")
    _add_common(weather)
    weather.add_argument("--start")
    weather.add_argument("--end")
    weather.add_argument("--force", action="store_true")

    osm = subparsers.add_parser("download-osm", help="Build optional OSM vulnerability features")
    _add_common(osm)
    osm.add_argument("--force", action="store_true")
    osm.add_argument("--cached-only", action="store_true")

    features = subparsers.add_parser("build-features", help="Build causal supervised tables")
    _add_common(features)
    features.add_argument("--task", choices=("day_ahead", "hour_ahead", "all"), default="all")
    features.add_argument("--include-osm", action="store_true")

    train = subparsers.add_parser("train", help="Train models and export validation predictions")
    _add_common(train)
    train.add_argument("--task", choices=("day_ahead", "hour_ahead", "all"), default="all")

    export = subparsers.add_parser("export", help="Export compact latest-window prediction CSVs")
    _add_common(export)
    export.add_argument("--task", choices=("day_ahead", "hour_ahead", "all"), default="all")

    baseline = subparsers.add_parser("baseline", help="Evaluate the persistence ablation")
    _add_common(baseline)
    baseline.add_argument("--task", choices=("day_ahead", "hour_ahead", "all"), default="all")

    run = subparsers.add_parser("run-all", help="Run the end-to-end local MVP")
    _add_common(run)
    run.add_argument("--force-download", action="store_true")
    run.add_argument("--include-osm", action="store_true")

    report = subparsers.add_parser("report", help="Regenerate the local MVP results report")
    _add_common(report)

    validate = subparsers.add_parser("validate", help="Validate generated prediction files")
    _add_common(validate)
    validate.add_argument("--task", choices=("day_ahead", "hour_ahead", "all"), default="all")
    return parser


def _tasks(value: str) -> list[str]:
    return ["day_ahead", "hour_ahead"] if value == "all" else [value]


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)

    if args.command == "download-phase1-data":
        _print(download_phase1_data(settings, force=args.force))
    elif args.command == "prepare-phase1-data":
        _print(prepare_phase1_outages(settings))
    elif args.command == "download-phase1-weather":
        _print(download_phase1_weather(settings, mode=args.mode, force=args.force))
    elif args.command == "build-phase1-features":
        tasks = ("A", "B") if args.task == "all" else (args.task,)
        purposes = ("training", "test") if args.purpose == "all" else (args.purpose,)
        _print(
            {
                f"{task}_{purpose}": build_phase1_features(settings, task, purpose)
                for purpose in purposes
                for task in tasks
            }
        )
    elif args.command == "train-phase1":
        tasks = ("A", "B") if args.task == "all" else (args.task,)
        _print({task: train_phase1_task(settings, task) for task in tasks})
    elif args.command == "export-phase1":
        _print(export_phase1_submission(settings))
    elif args.command == "infer-phase1":
        _print(reproduce_phase1_submission(settings, args.output))
    elif args.command == "validate-phase1":
        _print(validate_phase1_file(settings, args.path))
    elif args.command == "diagnose-phase1":
        _print(build_phase1_diagnostics(settings, rebuild=args.rebuild))
    elif args.command == "phase1-run-all":
        _print(run_phase1(settings, force_download=args.force_download))
    elif args.command == "download-nafirs":
        _print(download_nafirs(settings, force=args.force))
    elif args.command == "prepare-nafirs":
        path = normalize_nafirs(settings)
        _print({"path": path, "summary": summarize_incidents(path)})
    elif args.command == "prepare-locations":
        _print({"path": derive_district_locations(settings, force_download=args.force_download)})
    elif args.command == "export-substations":
        _print({"path": export_substation_coordinates(settings, force_download=args.force_download)})
    elif args.command == "download-weather":
        _print(
            {
                "path": download_historical_weather(
                    settings,
                    start=_date(args.start),
                    end=_date(args.end),
                    force=args.force,
                )
            }
        )
    elif args.command == "download-osm":
        _print(
            {
                "path": download_osm_features(
                    settings,
                    force=args.force,
                    cached_only=args.cached_only,
                )
            }
        )
    elif args.command == "build-features":
        _print(
            {
                task: build_task_features(settings, task, include_osm=args.include_osm)
                for task in _tasks(args.task)
            }
        )
    elif args.command == "train":
        result = {}
        for task in _tasks(args.task):
            result[task] = {
                "metrics": train_task(settings, task),
                "predictions": export_submission(settings, task),
            }
        _print(result)
    elif args.command == "export":
        _print({task: export_submission(settings, task) for task in _tasks(args.task)})
    elif args.command == "baseline":
        _print({task: evaluate_persistence(settings, task) for task in _tasks(args.task)})
    elif args.command == "run-all":
        download_nafirs(settings, force=args.force_download)
        normalize_nafirs(settings)
        derive_district_locations(settings, force_download=args.force_download)
        download_historical_weather(settings, force=args.force_download)
        if args.include_osm:
            download_osm_features(settings, force=args.force_download)
        result = {}
        for task in ("day_ahead", "hour_ahead"):
            build_task_features(settings, task, include_osm=args.include_osm)
            result[task] = {
                "metrics": train_task(settings, task),
                "persistence": evaluate_persistence(settings, task),
                "predictions": export_submission(settings, task),
            }
        result["report"] = write_mvp_report(settings)
        _print(result)
    elif args.command == "report":
        _print({"path": write_mvp_report(settings)})
    elif args.command == "validate":
        _print({task: validate_submission_file(settings, task) for task in _tasks(args.task)})
