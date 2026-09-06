"""Reading and writing the .gitnested YAML file."""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml


def _read_yaml_config(filepath: Path) -> dict:
    """Read YAML configuration file."""
    with filepath.open('r') as f:
        return yaml.safe_load(f) or {}


def _write_yaml_config(filepath: Path, data: dict) -> None:
    """Write YAML configuration file with header."""
    GITREPO_HEADER = textwrap.dedent("""\
        # This subdirectory is managed by "git nested".
        # Refer to: https://github.com/thorsten-klein/git-nested#readme
        #
        """)
    with filepath.open('w') as f:
        f.write(GITREPO_HEADER)
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
