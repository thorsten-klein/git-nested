"""The data git-nested passes around: parsed flags and .gitnested config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import GitNestedError


@dataclass
class Flags:
    """Command-line flags."""

    all: bool = False
    all_deep: bool = False
    branch: None | str = None
    commit: bool = False
    filter: None | list[str] = None
    force: bool = False
    fetch: bool = False
    message: None | str = None
    message_file: None | str = None
    method: None | str = None
    remote: None | str = None
    squash: bool = False
    update: bool = False
    quiet: bool = False
    verbose: int = 0


@dataclass
class NestedConfig:
    """Nested configuration from .gitnested file."""

    remote: str = ''
    branch: str = ''
    commit: str = ''
    filter: None | list[str] = None
    parent: str = ''
    method: str = 'merge'

    @classmethod
    def from_file(cls, filepath: str | Path):
        """Read config from .gitnested YAML file."""
        path = Path(filepath)
        if not path.is_file():
            raise GitNestedError(f"No '{filepath}' file.")
        with path.open('r') as f:
            data = yaml.safe_load(f) or {}
        nested_data = data.get('nested', {})

        config = cls()
        config.remote = nested_data.get('remote', '')
        config.branch = nested_data.get('branch', '')
        config.commit = nested_data.get('commit', '')
        config.filter = nested_data.get('filter', None)
        config.parent = nested_data.get('parent', '')
        method = nested_data.get('method', 'merge')
        config.method = 'rebase' if method == 'rebase' else 'merge'

        if not config.remote:
            raise GitNestedError(f"Missing required 'remote' in '{filepath}'.")
        if not config.branch:
            raise GitNestedError(f"Missing required 'branch' in '{filepath}'.")

        return config
