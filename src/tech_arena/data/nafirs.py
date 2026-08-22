from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tech_arena.config import Settings
from tech_arena.net import download_file, get_json


NUMERIC_COLUMNS = (
    "REPORTING_YEAR",
    "DISTRICT_CODE",
    "PRIMARY_NRN",
    "CATEGORY_CODE",
    "DAMAGE",
    "EXCEPTIONAL_EVENT",
    "LV_CUST_AFF",
    "LV_CUST_MINS_LOST",
    "AVG_TIME_OFF_MINS",
)


def resolve_resources(settings: Settings) -> dict[str, dict[str, Any]]:
    payload = get_json(settings.values["nafirs"]["package_api"])
    if not payload.get("success"):
        raise RuntimeError("The SSEN CKAN package API did not return success.")
    wanted = {
        settings.values["nafirs"]["sepd_resource_id"]: "SEPD",
        settings.values["nafirs"]["shepd_resource_id"]: "SHEPD",
    }
    resources: dict[str, dict[str, Any]] = {}
    for resource in payload["result"]["resources"]:
        network = wanted.get(resource.get("id"))
        if network:
            resources[network] = resource
    missing = set(wanted.values()) - set(resources)
    if missing:
        raise RuntimeError(f"Missing expected NaFIRS resources: {sorted(missing)}")
    return resources


def download_nafirs(settings: Settings, force: bool = False) -> list[dict[str, Any]]:
    resources = resolve_resources(settings)
    raw_dir = settings.path("raw_dir") / "nafirs"
    records: list[dict[str, Any]] = []
    for network, resource in sorted(resources.items()):
        record = download_file(
            resource["url"],
            raw_dir / f"nafirs_{network.lower()}.csv",
            force=force,
        )
        record.update(
            {
                "network": network,
                "resource_id": resource["id"],
                "resource_name": resource["name"],
                "license": "CC BY 4.0",
            }
        )
        records.append(record)
    manifest = raw_dir / "manifest.json"
    manifest.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return records


def _local_to_utc(values: pd.Series, timezone: str) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", dayfirst=True)
    if getattr(parsed.dt, "tz", None) is None:
        parsed = parsed.dt.tz_localize(
            timezone,
            ambiguous="NaT",
            nonexistent="shift_forward",
        )
    return parsed.dt.tz_convert("UTC")


def normalize_nafirs(settings: Settings) -> Path:
    raw_dir = settings.path("raw_dir") / "nafirs"
    frames: list[pd.DataFrame] = []
    for network in ("SEPD", "SHEPD"):
        path = raw_dir / f"nafirs_{network.lower()}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}. Run download-nafirs first.")
        frame = pd.read_csv(path, low_memory=False)
        frame.columns = [str(column).strip().upper() for column in frame.columns]
        frame["NETWORK"] = network
        frames.append(frame)

    incidents = pd.concat(frames, ignore_index=True, sort=False)
    required = {"LV_INCIDENT_TIME", "LV_CUST_AFF", "AVG_TIME_OFF_MINS"}
    missing = required - set(incidents.columns)
    if missing:
        raise ValueError(f"NaFIRS files are missing required columns: {sorted(missing)}")

    for column in NUMERIC_COLUMNS:
        if column in incidents:
            incidents[column] = pd.to_numeric(incidents[column], errors="coerce")

    incidents["TIMESTAMP_UTC"] = _local_to_utc(
        incidents["LV_INCIDENT_TIME"], settings.values["nafirs"]["timezone"]
    )
    fallback_duration = incidents["LV_CUST_MINS_LOST"].div(
        incidents["LV_CUST_AFF"].replace(0, np.nan)
    )
    incidents["DURATION_MINUTES"] = (
        incidents["AVG_TIME_OFF_MINS"]
        .fillna(fallback_duration)
        .clip(lower=1, upper=14 * 24 * 60)
    )
    incidents["CUSTOMERS_AFFECTED"] = incidents["LV_CUST_AFF"].fillna(0).clip(lower=0)
    incidents["DISTRICT_ID"] = (
        incidents.get("DISTRICT_SHORT_CODE", incidents.get("DISTRICT_CODE", "UNKNOWN"))
        .fillna("UNKNOWN")
        .astype(str)
        .str.strip()
    )
    descriptor_columns = [
        column
        for column in ("CATEGORY_DESCRIPTION", "CAUSE_DESCRIPTION", "EQUIPMENT_DESCRIPTION")
        if column in incidents
    ]
    if descriptor_columns:
        descriptors = incidents[descriptor_columns].fillna("").agg(" ".join, axis=1).str.lower()
        incidents["IS_PLANNED"] = descriptors.str.contains(r"\bplanned\b", regex=True)
    else:
        incidents["IS_PLANNED"] = False

    incidents = incidents.dropna(subset=["TIMESTAMP_UTC"])
    incidents = incidents.loc[incidents["CUSTOMERS_AFFECTED"] > 0].copy()
    incidents = incidents.sort_values(["NETWORK", "DISTRICT_ID", "TIMESTAMP_UTC"])

    output = settings.path("interim_dir") / "nafirs_incidents.csv.gz"
    incidents.to_csv(output, index=False, compression="gzip")
    return output


def summarize_incidents(path: Path) -> dict[str, Any]:
    incidents = pd.read_csv(path, parse_dates=["TIMESTAMP_UTC"], low_memory=False)
    return {
        "rows": int(len(incidents)),
        "start": str(incidents["TIMESTAMP_UTC"].min()),
        "end": str(incidents["TIMESTAMP_UTC"].max()),
        "networks": incidents.groupby("NETWORK").size().astype(int).to_dict(),
        "districts": int(incidents[["NETWORK", "DISTRICT_ID"]].drop_duplicates().shape[0]),
        "planned_fraction": float(incidents["IS_PLANNED"].astype(bool).mean()),
    }
