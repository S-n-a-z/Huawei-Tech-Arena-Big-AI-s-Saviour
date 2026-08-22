from __future__ import annotations

import numpy as np
import pandas as pd

from tech_arena.config import load_settings
from tech_arena.resilience import apply_resilience_rules, site_risk


def test_site_risk_is_monotonic() -> None:
    regional = np.array([0.0, 0.2, 0.5, 1.0])
    values = site_risk(regional, k=10.0, x0=0.2)
    assert np.all(np.diff(values) > 0)
    assert np.all((values >= 0) & (values <= 1))


def test_rule_output_has_four_architectures() -> None:
    settings = load_settings()
    source = pd.DataFrame(
        {
            "issue_time": ["2026-01-01T00:00:00Z"],
            "target_time": ["2026-01-01T01:00:00Z"],
            "network": ["SEPD"],
            "district_id": ["A"],
            "lead_minutes": [60],
            "regional_risk_prediction": [0.2],
        }
    )
    output = apply_resilience_rules(source, settings)
    assert len(output) == 4
    assert output["architecture_id"].nunique() == 4
    assert output["critical_load_coverage_ratio"].between(0, 1).all()
    assert output["site_risk_score"].between(0, 1).all()

