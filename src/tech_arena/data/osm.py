from __future__ import annotations

import json
import math
from pathlib import Path
import time
from typing import Any

import pandas as pd

from tech_arena.config import Settings
from tech_arena.data.locations import configured_locations
from tech_arena.net import post_form_json


OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
)


def _query(latitude: float, longitude: float, radius_m: int) -> str:
    return f"""
[out:json][timeout:60];
(
  nwr[power=substation](around:{radius_m},{latitude},{longitude});
  nwr[power=transformer](around:{radius_m},{latitude},{longitude});
  nwr[power=tower](around:{radius_m},{latitude},{longitude});
  nwr[power=pole](around:{radius_m},{latitude},{longitude});
  way[power=line](around:{radius_m},{latitude},{longitude});
  way[power=minor_line](around:{radius_m},{latitude},{longitude});
  way[power=cable](around:{radius_m},{latitude},{longitude});
);
out tags geom;
""".strip()


def _haversine_km(a: dict[str, float], b: dict[str, float]) -> float:
    radius = 6371.0088
    lat1, lon1 = math.radians(a["lat"]), math.radians(a["lon"])
    lat2, lon2 = math.radians(b["lat"]), math.radians(b["lon"])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def download_osm_features(
    settings: Settings,
    force: bool = False,
    cached_only: bool = False,
) -> Path:
    raw_dir = settings.path("raw_dir") / "osm"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for location in configured_locations(settings):
        output = raw_dir / f"{location['location_id']}.json"
        if output.exists() and not force:
            payload = json.loads(output.read_text(encoding="utf-8"))
        elif cached_only:
            payload = {"elements": [], "cache_missing": True}
        else:
            query = _query(
                float(location["latitude"]),
                float(location["longitude"]),
                int(float(location["radius_km"]) * 1000),
            )
            payload = None
            errors: list[str] = []
            for endpoint in OVERPASS_ENDPOINTS:
                try:
                    payload = post_form_json(endpoint, {"data": query}, retries=2, timeout=180)
                    break
                except RuntimeError as exc:
                    errors.append(str(exc))
            if payload is None:
                raise RuntimeError("All configured Overpass instances failed: " + "; ".join(errors))
            output.write_text(json.dumps(payload), encoding="utf-8")
            time.sleep(2)

        counts: dict[str, int] = {}
        line_length_km = 0.0
        overhead_length_km = 0.0
        voltages: list[int] = []
        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            power = tags.get("power", "unknown")
            counts[power] = counts.get(power, 0) + 1
            geometry = element.get("geometry", [])
            if len(geometry) > 1:
                length = sum(_haversine_km(a, b) for a, b in zip(geometry, geometry[1:]))
                line_length_km += length
                if power in {"line", "minor_line"}:
                    overhead_length_km += length
            voltage = str(tags.get("voltage", "")).split(";")[0]
            if voltage.isdigit():
                voltages.append(int(voltage))
        area_km2 = math.pi * float(location["radius_km"]) ** 2
        rows.append(
            {
                "location_id": location["location_id"],
                "network": location["network"],
                "district_id": location.get("district_id"),
                "osm_substation_count": counts.get("substation", 0),
                "osm_transformer_count": counts.get("transformer", 0),
                "osm_tower_count": counts.get("tower", 0),
                "osm_pole_count": counts.get("pole", 0),
                "osm_line_length_km": line_length_km,
                "osm_overhead_length_km": overhead_length_km,
                "osm_overhead_share": overhead_length_km / line_length_km if line_length_km else 0.0,
                "osm_asset_density_km2": len(payload.get("elements", [])) / area_km2,
                "osm_max_voltage": max(voltages, default=0),
                "osm_missing": int(len(payload.get("elements", [])) == 0),
                "osm_cache_missing": int(bool(payload.get("cache_missing"))),
            }
        )
    features = pd.DataFrame(rows)
    group_columns = ["network"]
    if "district_id" in features.columns and features["district_id"].notna().any():
        group_columns.append("district_id")
    features = features.groupby(group_columns).mean(numeric_only=True).reset_index()
    output = settings.path("interim_dir") / "osm_network_features.csv"
    features.to_csv(output, index=False)
    return output
