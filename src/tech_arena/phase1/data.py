from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from zipfile import ZipFile

import pandas as pd
import requests

from tech_arena.config import Settings


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path, expected_md5: str | None = None, force: bool = False) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        if expected_md5 is None or _md5(destination) == expected_md5:
            return destination
    temporary = destination.with_suffix(destination.suffix + ".part")
    with requests.get(url, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            shutil.copyfileobj(response.raw, handle, length=8 * 1024 * 1024)
    if expected_md5 and _md5(temporary) != expected_md5:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"Checksum mismatch for {destination.name}")
    temporary.replace(destination)
    return destination


def download_phase1_data(settings: Settings, force: bool = False) -> dict[str, str]:
    config = settings.values["phase1"]
    raw = settings.path("raw_dir") / "eaglei"
    outage = _download(
        str(config["eaglei_url"]),
        raw / "eaglei_outages_2025.csv",
        str(config["eaglei_md5"]),
        force,
    )
    customers = _download(
        str(config["mcc_url"]),
        raw / "MCC.csv",
        str(config["mcc_md5"]),
        force,
    )
    gazetteer_zip = _download(
        str(config["gazetteer_url"]),
        raw / "2025_Gaz_counties_national.zip",
        force=force,
    )
    gazetteer_dir = raw / "gazetteer"
    gazetteer_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(gazetteer_zip) as archive:
        archive.extractall(gazetteer_dir)
    return {
        "outages": str(outage),
        "customers": str(customers),
        "gazetteer": str(gazetteer_dir / "2025_Gaz_counties_national.txt"),
    }


def county_frame(settings: Settings) -> pd.DataFrame:
    frame = pd.DataFrame(settings.values["phase1"]["counties"])
    frame["fips_code"] = frame["fips_code"].astype(str).str.zfill(5)
    return frame


def prepare_phase1_outages(settings: Settings) -> dict[str, Any]:
    paths = download_phase1_data(settings)
    selected = county_frame(settings)
    selected_fips = set(selected["fips_code"])

    frames: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        paths["outages"],
        usecols=["fips_code", "customers_out", "run_start_time"],
        dtype={"fips_code": "string", "customers_out": "float64"},
        chunksize=1_000_000,
    ):
        chunk["fips_code"] = chunk["fips_code"].str.zfill(5)
        matched = chunk.loc[chunk["fips_code"].isin(selected_fips)].copy()
        if not matched.empty:
            frames.append(matched)
    if not frames:
        raise RuntimeError("No EAGLE-I rows matched the configured counties.")

    observed = pd.concat(frames, ignore_index=True)
    observed["timestamp"] = pd.to_datetime(observed.pop("run_start_time"), utc=True)
    observed = (
        observed.groupby(["fips_code", "timestamp"], as_index=False)["customers_out"]
        .max()
        .sort_values(["fips_code", "timestamp"])
    )
    observed["record_present"] = 1

    config = settings.values["phase1"]
    start = pd.Timestamp(config["training_start"])
    end = pd.Timestamp(config["test_end"])
    times = pd.date_range(start, end, freq="15min", tz="UTC")
    dense_parts: list[pd.DataFrame] = []
    for county in selected.to_dict("records"):
        base = pd.DataFrame({"timestamp": times})
        base["fips_code"] = county["fips_code"]
        county_observed = observed.loc[observed["fips_code"] == county["fips_code"]]
        base = base.merge(county_observed, on=["fips_code", "timestamp"], how="left")
        base["record_present"] = base["record_present"].fillna(0).astype("int8")
        base["customers_out"] = base["customers_out"].fillna(0).clip(lower=0)
        base["total_customers"] = int(county["total_customers"])
        base["outage_ratio"] = (base["customers_out"] / base["total_customers"]).clip(0, 1)
        base["county"] = county["county"]
        base["state"] = county["state"]
        dense_parts.append(base)
    dense = pd.concat(dense_parts, ignore_index=True)

    destination = settings.path("interim_dir") / "phase1_outages_15min.csv.gz"
    dense.to_csv(destination, index=False, compression="gzip")

    training_end = pd.Timestamp(config["training_end"])
    audit = dense.loc[dense["timestamp"] <= training_end].groupby(
        ["fips_code", "county", "state", "total_customers"], as_index=False
    ).agg(
        source_records=("record_present", "sum"),
        source_coverage=("record_present", "mean"),
        mean_outage_ratio=("outage_ratio", "mean"),
        maximum_outage_ratio=("outage_ratio", "max"),
    )
    audit_path = settings.path("processed_dir") / "phase1_county_selection.csv"
    audit.to_csv(audit_path, index=False)
    manifest = {
        "path": str(destination),
        "rows": int(len(dense)),
        "counties": int(dense["fips_code"].nunique()),
        "start": dense["timestamp"].min().isoformat(),
        "end": dense["timestamp"].max().isoformat(),
        "zero_fill_policy": (
            "Absent county/time rows are set to zero in line with the EAGLE-I release convention; "
            "record_present preserves a missingness indicator because collection gaps are not separable."
        ),
        "eaglei_md5": _md5(Path(paths["outages"])),
        "mcc_md5": _md5(Path(paths["customers"])),
    }
    manifest_path = settings.path("processed_dir") / "phase1_data_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {**manifest, "audit": str(audit_path), "manifest": str(manifest_path)}
