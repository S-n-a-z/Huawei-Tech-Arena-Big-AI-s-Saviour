from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pandas as pd
from pyproj import Transformer

from tech_arena.config import Settings
from tech_arena.net import download_file, get_json


DISTRICT_TO_OPERATING_AREA = {
    "SEPD": {
        "ALDE": "Aldershot",
        "ANDO": "Andover",
        "BASI": "Basingstoke",
        "BOUR": "Bournemouth",
        "BRAC": "Bracknell",
        "CHIC": "Chichester",
        "EGHA": "Egham",
        "ISLE": "Isle Of Wight",
        "MELK": "Melksham",
        "NEWB": "Newbury",
        "NEWF": "New Forest",
        "OXFN": "Oxford North",
        "OXFS": "Oxford South",
        "PETE": "Petersfield",
        "POOL": "Poole",
        "PORT": "Portsmouth",
        "REAN": "Reading North",
        "REAS": "Reading South",
        "SALI": "Salisbury",
        "SLOU": "Slough",
        "SOTN": "Southampton",
        "SWIN": "Swindon",
        "WLON": "West London excl.",
        "YEOV": "Yeovil",
    },
    "SHEPD": {
        "ARGYLL": "Argyll & West Highl.",
        "HIGH": "Highland District",
        "N/EAST": "North East District",
        "ORKN": "Orkney",
        "SHET": "Shetland District",
        "TAYCEN": "Tayside and Central",
        "WISLES": "Western Isles",
    },
}


def download_substations(settings: Settings, force: bool = False) -> Path:
    config = settings.values["substations"]
    payload = get_json(config["package_api"])
    wanted = config["csv_resource_id"]
    resource = next(
        (item for item in payload["result"]["resources"] if item.get("id") == wanted),
        None,
    )
    if resource is None:
        raise RuntimeError("SSEN substation CSV resource was not found in the package metadata.")
    output = settings.path("raw_dir") / "ssen" / "substations.csv"
    record = download_file(resource["url"], output, force=force)
    record.update(
        {
            "resource_id": wanted,
            "license": payload["result"].get("license_title", "Creative Commons Attribution 4.0"),
            "license_url": payload["result"].get("license_url"),
        }
    )
    (output.parent / "manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return output


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _read_substations(source: Path) -> pd.DataFrame:
    substations = pd.read_csv(source, low_memory=False)
    substations.columns = [str(column).strip().lower() for column in substations.columns]
    substations["owner_name"] = substations["owner_name"].astype("string").str.upper().str.strip()
    substations["operating_area"] = substations["operating_area"].astype("string").str.strip()
    substations["location_x_m"] = pd.to_numeric(substations["location_x_m"], errors="coerce")
    substations["location_y_m"] = pd.to_numeric(substations["location_y_m"], errors="coerce")
    return substations.dropna(subset=["location_x_m", "location_y_m"]).copy()


def export_substation_coordinates(settings: Settings, force_download: bool = False) -> Path:
    """Export one WGS84 row per unique SSEN physical coordinate.

    The SSEN source contains repeated records for some locations. A physical point is
    identified by owner plus British National Grid easting/northing rounded to the
    source's millimetre precision. The most complete metadata row is retained and the
    number of contributing source records is included for auditability.
    """
    source = download_substations(settings, force=force_download)
    substations = _read_substations(source)
    substations["easting_m"] = substations["location_x_m"].round(3)
    substations["northing_m"] = substations["location_y_m"].round(3)
    key_columns = ["owner_name", "easting_m", "northing_m"]
    substations["source_record_count"] = substations.groupby(key_columns)["owner_name"].transform(
        "size"
    )

    metadata_columns = [
        "type",
        "class",
        "number",
        "status",
        "data_confidence",
        "fence_type",
        "operating_area",
        "locality",
    ]
    substations["metadata_completeness"] = substations[metadata_columns].notna().sum(axis=1)
    substations = substations.sort_values(
        key_columns + ["metadata_completeness"],
        ascending=[True, True, True, False],
        kind="stable",
    ).drop_duplicates(key_columns, keep="first")

    transformer = Transformer.from_crs(
        settings.values["substations"]["source_crs"],
        settings.values["substations"]["target_crs"],
        always_xy=True,
    )
    longitude, latitude = transformer.transform(
        substations["easting_m"].to_numpy(),
        substations["northing_m"].to_numpy(),
    )
    substations["latitude"] = latitude
    substations["longitude"] = longitude
    substations["substation_id"] = (
        substations["owner_name"]
        + "_"
        + (substations["easting_m"] * 1000).round().astype("int64").astype(str)
        + "_"
        + (substations["northing_m"] * 1000).round().astype("int64").astype(str)
    )
    result = substations.rename(columns={"owner_name": "network"})[
        [
            "substation_id",
            "network",
            "type",
            "class",
            "number",
            "status",
            "data_confidence",
            "fence_type",
            "operating_area",
            "locality",
            "latitude",
            "longitude",
            "easting_m",
            "northing_m",
            "source_record_count",
        ]
    ].sort_values(["network", "substation_id"])
    output = settings.path("output_dir") / "ssen_individual_substation_coordinates.csv"
    result.to_csv(output, index=False, float_format="%.8f")
    return output


def derive_district_locations(settings: Settings, force_download: bool = False) -> Path:
    source = download_substations(settings, force=force_download)
    substations = _read_substations(source)[
        ["owner_name", "operating_area", "location_x_m", "location_y_m"]
    ]
    substations = substations.drop_duplicates(
        ["owner_name", "operating_area", "location_x_m", "location_y_m"]
    )

    incidents = pd.read_csv(
        settings.path("interim_dir") / "nafirs_incidents.csv.gz",
        usecols=["NETWORK", "DISTRICT_ID"],
        low_memory=False,
    ).drop_duplicates()
    transformer = Transformer.from_crs(
        settings.values["substations"]["source_crs"],
        settings.values["substations"]["target_crs"],
        always_xy=True,
    )
    rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, str]] = []
    for item in incidents.itertuples(index=False):
        network, district = str(item.NETWORK), str(item.DISTRICT_ID)
        operating_area = DISTRICT_TO_OPERATING_AREA.get(network, {}).get(district)
        if operating_area is None:
            excluded_rows.append(
                {
                    "network": network,
                    "district_id": district,
                    "reason": "no_operating_area_mapping",
                }
            )
            continue
        network_points = substations.loc[substations["owner_name"] == network]
        district_points = network_points.loc[
            network_points["operating_area"].str.casefold() == operating_area.casefold()
        ]
        if district_points.empty:
            excluded_rows.append(
                {
                    "network": network,
                    "district_id": district,
                    "reason": f"no_substations_for_operating_area:{operating_area}",
                }
            )
            continue
        x = float(district_points["location_x_m"].median())
        y = float(district_points["location_y_m"].median())
        longitude, latitude = transformer.transform(x, y)
        rows.append(
            {
                "location_id": f"{network.lower()}_{_slug(district)}",
                "network": network,
                "district_id": district,
                "latitude": latitude,
                "longitude": longitude,
                "radius_km": 6.0,
                "location_source": f"operating_area:{operating_area}",
                "substations_in_area": int(len(district_points)),
            }
        )
    result = pd.DataFrame(rows).sort_values(["network", "district_id"])
    output = settings.path("interim_dir") / "district_locations.csv"
    result.to_csv(output, index=False)
    excluded_output = settings.path("interim_dir") / "excluded_unmatched_districts.csv"
    pd.DataFrame(
        excluded_rows,
        columns=["network", "district_id", "reason"],
    ).sort_values(["network", "district_id"]).to_csv(excluded_output, index=False)
    return output


def configured_locations(settings: Settings) -> list[dict[str, Any]]:
    path = settings.path("interim_dir") / "district_locations.csv"
    if path.exists():
        return pd.read_csv(path).to_dict(orient="records")
    return list(settings.values["weather"]["locations"])
