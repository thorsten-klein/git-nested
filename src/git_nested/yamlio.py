"""Reading and writing the .gitnested YAML file."""

from __future__ import annotations

from pathlib import Path

import yaml

from .messages import GITNESTED_HEADER


def _read_yaml_config(filepath: Path) -> dict:
    """Read YAML configuration file."""
    with filepath.open('r') as f:
        return yaml.safe_load(f) or {}


def _write_yaml_config(filepath: Path, data: dict) -> None:
    """Write YAML configuration file with header."""
    with filepath.open('w') as f:
        f.write(GITNESTED_HEADER)
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
