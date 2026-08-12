from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any


@dataclass(frozen=True)
class Settings:
    root: Path
    values: dict[str, Any]

    def path(self, key: str) -> Path:
        return self.root / self.values["paths"][key]

    def ensure_directories(self) -> None:
        for key in ("raw_dir", "interim_dir", "processed_dir", "artifact_dir", "output_dir"):
            self.path(key).mkdir(parents=True, exist_ok=True)


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise FileNotFoundError("Could not find pyproject.toml from the current directory.")


def load_settings(config_path: str | Path | None = None) -> Settings:
    root = find_project_root()
    path = Path(config_path) if config_path else root / "configs" / "default.toml"
    if not path.is_absolute():
        path = root / path
    with path.open("rb") as handle:
        values = tomllib.load(handle)
    settings = Settings(root=root, values=values)
    settings.ensure_directories()
    return settings

