import json
from pathlib import Path

from tech_arena.config import load_settings


def test_default_configuration_has_all_topologies() -> None:
    settings = load_settings()
    topology_ids = {
        item["topology_id"] for item in settings.values["resilience"]["topologies"]
    }
    assert topology_ids == {"ups_2n", "ups_dr", "hvdc_2n", "mains_2n"}


def test_site_architecture_schema_has_review_and_safety_fields() -> None:
    schema_path = Path(__file__).parents[1] / "configs" / "site_architecture.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    required = set(schema["required"])
    assert {
        "critical_load_kw",
        "protected_load_fraction",
        "usable_energy_kwh",
        "generator_endurance_hours",
        "parameter_status",
        "provenance",
    } <= required
    assert schema["properties"]["protected_load_fraction"]["maximum"] == 1
    assert "engineer_reviewed" in schema["properties"]["parameter_status"]["enum"]
