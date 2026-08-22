from tech_arena.config import load_settings


def test_default_configuration_has_all_topologies() -> None:
    settings = load_settings()
    topology_ids = {
        item["topology_id"] for item in settings.values["resilience"]["topologies"]
    }
    assert topology_ids == {"ups_2n", "ups_dr", "hvdc_2n", "mains_2n"}

