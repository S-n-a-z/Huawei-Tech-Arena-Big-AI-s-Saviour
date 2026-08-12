from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd
from pyproj import Transformer

from net import download_file, get_json


PACKAGE_API = "https://data-api.ssen.co.uk/api/3/action/package_show?id=ssen-substation-data"
CSV_RESOURCE_ID = "336d9720-353c-49d3-8415-11e1cf4a85b9"
SOURCE_CRS = "EPSG:27700"
TARGET_CRS = "EPSG:4326"
DEFAULT_RAW_PATH = Path("data/raw/ssen/substations.csv")
DEFAULT_INCIDENTS_PATH = Path("data/interim/nafirs_incidents.csv.gz")


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


def download_substations(force: bool = False) -> Path:
    payload = get_json(PACKAGE_API)
    resource = next(
        (item for item in payload["result"]["resources"] if item.get("id") == CSV_RESOURCE_ID),
        None,
    )
    if resource is None:
        raise RuntimeError("SSEN substation CSV resource was not found in the package metadata.")

    record = download_file(resource["url"], DEFAULT_RAW_PATH, force=force)
    record.update(
        {
            "resource_id": CSV_RESOURCE_ID,
            "license": payload["result"].get(
                "license_title", "Creative Commons Attribution 4.0"
            ),
            "license_url": payload["result"].get("license_url"),
        }
    )
    manifest = DEFAULT_RAW_PATH.parent / "manifest.json"
    manifest.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return DEFAULT_RAW_PATH


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


def export_substation_coordinates(
    source: Path,
    output: Path = Path("ssen_individual_substation_coordinates.csv"),
) -> Path:
    """Write one WGS84 row per unique SSEN physical coordinate."""
    substations = _read_substations(source)
    substations["easting_m"] = substations["location_x_m"].round(3)
    substations["northing_m"] = substations["location_y_m"].round(3)
    key_columns = ["owner_name", "easting_m", "northing_m"]
    substations["source_record_count"] = substations.groupby(key_columns)[
        "owner_name"
    ].transform("size")

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

    transformer = Transformer.from_crs(SOURCE_CRS, TARGET_CRS, always_xy=True)
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
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, float_format="%.8f")
    return output


def derive_district_locations(
    source: Path,
    incidents_path: Path = DEFAULT_INCIDENTS_PATH,
    output: Path = Path("district_locations.csv"),
    excluded_output: Path = Path("excluded_unmatched_districts.csv"),
) -> Path:
    substations = _read_substations(source)[
        ["owner_name", "operating_area", "location_x_m", "location_y_m"]
    ].drop_duplicates(["owner_name", "operating_area", "location_x_m", "location_y_m"])
    incidents = pd.read_csv(
        incidents_path,
        usecols=["NETWORK", "DISTRICT_ID"],
        low_memory=False,
    ).drop_duplicates()
    transformer = Transformer.from_crs(SOURCE_CRS, TARGET_CRS, always_xy=True)

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

        district_points = substations.loc[
            (substations["owner_name"] == network)
            & (substations["operating_area"].str.casefold() == operating_area.casefold())
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

    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).sort_values(["network", "district_id"]).to_csv(output, index=False)
    pd.DataFrame(
        excluded_rows,
        columns=["network", "district_id", "reason"],
    ).sort_values(["network", "district_id"]).to_csv(excluded_output, index=False)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare SSEN location data for Topic Two")
    parser.add_argument(
        "command",
        choices=("export-substations", "prepare-locations", "all"),
        nargs="?",
        default="export-substations",
    )
    parser.add_argument("--source", type=Path, help="Use an existing SSEN substation CSV")
    parser.add_argument("--incidents", type=Path, default=DEFAULT_INCIDENTS_PATH)
    parser.add_argument("--force-download", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source = args.source or download_substations(force=args.force_download)
    completed: list[Path] = []
    if args.command in {"export-substations", "all"}:
        completed.append(export_substation_coordinates(source))
    if args.command in {"prepare-locations", "all"}:
        if not args.incidents.exists():
            raise FileNotFoundError(
                f"NaFIRS incident file not found: {args.incidents}. "
                "Pass its path with --incidents."
            )
        completed.append(derive_district_locations(source, incidents_path=args.incidents))
    for path in completed:
        print(path.resolve())


if __name__ == "__main__":
    main()
