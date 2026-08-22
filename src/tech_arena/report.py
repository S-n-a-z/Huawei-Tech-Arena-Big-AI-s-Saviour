from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tech_arena.config import Settings
from tech_arena.data.nafirs import summarize_incidents


def write_mvp_report(settings: Settings) -> Path:
    summary = summarize_incidents(settings.path("interim_dir") / "nafirs_incidents.csv.gz")
    locations_path = settings.path("interim_dir") / "district_locations.csv"
    modelled_districts = None
    if locations_path.exists():
        locations = pd.read_csv(locations_path, usecols=["network", "district_id"])
        modelled_districts = int(locations.drop_duplicates().shape[0])
    metrics = {}
    persistence = {}
    for task in ("day_ahead", "hour_ahead"):
        path = settings.path("artifact_dir") / task / "metrics.json"
        if path.exists():
            metrics[task] = json.loads(path.read_text(encoding="utf-8"))
        baseline_path = settings.path("artifact_dir") / task / "persistence_metrics.json"
        if baseline_path.exists():
            persistence[task] = json.loads(baseline_path.read_text(encoding="utf-8"))

    lines = [
        "# Topic Two development results",
        "",
        "> Status: reproducible engineering baseline. Architecture calculations use the",
        "> versioned configuration recorded in `configs/default.toml`.",
        "",
        "## Data snapshot",
        "",
        f"- Normalized NaFIRS incidents: {summary['rows']:,}",
        f"- Time range: {summary['start']} to {summary['end']}",
        f"- Districts: {summary['districts']}",
        f"- Spatially matched districts used by the model: {modelled_districts or 'not available'}",
        "- Excluded from spatial modelling: SEPD NATS and NATSL (no supported operating-area match)",
        f"- Networks: {summary['networks']}",
        f"- Planned fraction: {summary['planned_fraction']:.3%}",
        "",
        "## Validation",
        "",
        "Validation is chronological and purged by the maximum task horizon. Metrics below",
        "are chronological hold-out diagnostics on the sampled modelling table.",
        "",
        "| Task | Train rows | Test rows | MAE | RMSE | High-risk MAE | PR-AUC | Event recall |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for task, values in metrics.items():
        lines.append(
            "| {task_label} | {train_rows:,} | {test_rows:,} | {mae:.5f} | {rmse:.5f} | "
            "{high_risk_mae:.5f} | {event_pr_auc:.5f} | {event_recall:.5f} |".format(
                task_label=task.replace("_", " ").title(), **values
            )
        )
    lines.extend(
        [
            "",
            "## Persistence ablation",
            "",
            "| Task | Persistence MAE | Hurdle MAE | MAE change | Persistence RMSE | Hurdle RMSE | Persistence PR-AUC | Hurdle PR-AUC |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for task, baseline in persistence.items():
        learned = metrics[task]
        lines.append(
            "| {task} | {base_mae:.5f} | {model_mae:.5f} | {change:+.2%} | {base_rmse:.5f} | {model_rmse:.5f} | {base_pr:.5f} | {model_pr:.5f} |".format(
                task=task.replace("_", " ").title(),
                base_mae=baseline["mae"],
                model_mae=learned["mae"],
                change=(learned["mae"] - baseline["mae"]) / baseline["mae"],
                base_rmse=baseline["rmse"],
                model_rmse=learned["rmse"],
                base_pr=baseline["event_pr_auc"],
                model_pr=learned["event_pr_auc"],
            )
        )
    lines.extend(
        [
            "",
            "The day-ahead model improves both average error and rare-event discrimination.",
            "For hour-ahead prediction it improves RMSE and PR-AUC but gives up some MAE to",
            "persistence. This metric trade-off is retained in the recorded evidence rather",
            "than hidden behind a single summary value.",
            "",
            "## Implemented ablation path",
            "",
            "1. Current-risk persistence is blended into every forecast.",
            "2. The hurdle model adds causal risk lags and weather variables.",
            "3. The deterministic topology layer maps regional predictions to site risk.",
            "4. OSM network features can be enabled and evaluated separately.",
            "",
            "## Known limitations",
            "",
            "- Regional outage proportion uses a documented train-data exposure proxy because",
            "  total customers per district are not present in the NaFIRS resource.",
            "- District weather coordinates are median SSEN substation locations, not asserted",
            "  AIDC site locations.",
            "- NaFIRS incident duration and customers affected are used only to construct labels;",
            "  post-event cause and duration fields are not forecasting inputs.",
            "- Architecture calculations use versioned engineering assumptions and are not",
            "  a substitute for site-specific protection studies or equipment certification.",
            "- Output CSVs are latest-window reference exports from the recorded model run.",
            "",
        ]
    )
    output = settings.root / "reports" / "mvp_results.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
