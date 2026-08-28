from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from tech_arena.config import load_settings
from tech_arena.phase1.submission import reproduce_phase1_submission


def test_frozen_inference_reproduces_submitted_csv(tmp_path: Path) -> None:
    settings = load_settings()
    generated = tmp_path / "predictions.csv"

    result = reproduce_phase1_submission(settings, generated)

    submitted = settings.path("output_dir") / "predictions.csv"
    submitted_archive = settings.path("output_dir") / "predictions.csv.zip"
    with ZipFile(submitted_archive) as archive:
        archived_bytes = archive.read("predictions.csv")

    submitted_bytes = submitted.read_bytes()
    assert archived_bytes == submitted_bytes
    assert generated.read_bytes() == submitted_bytes
    assert result["rows"] == 65880
    assert result["matches_submitted_predictions"] is True
    assert result["sha256"] == sha256(submitted_bytes).hexdigest()
