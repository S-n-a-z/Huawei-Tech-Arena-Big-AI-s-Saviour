from __future__ import annotations

import argparse
import json
from pathlib import Path

from tech_arena.config import load_settings
from tech_arena.phase1.submission import validate_phase1_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a Huawei Tech Arena Topic Two Phase 1 prediction file."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="outputs/predictions.csv",
        help="CSV to check (default: outputs/predictions.csv)",
    )
    args = parser.parse_args()
    result = validate_phase1_file(load_settings(), Path(args.path))
    print(json.dumps({"valid": True, **result}, indent=2))


if __name__ == "__main__":
    main()
