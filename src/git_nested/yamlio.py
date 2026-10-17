"""Reading and writing the .gitnested YAML file."""

from __future__ import annotations

from pathlib import Path

import yaml

from .messages import GITNESTED_HEADER

# The fields with a default value, as they read in the file.
DEFAULTS = {'method': 'merge', 'squash': 'true', 'readonly': 'false'}
DEFAULT_COMMENT = '# optional: this is the default'


def _read_yaml_config(filepath: Path) -> dict:
    """Read YAML configuration file."""
    with filepath.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _write_yaml_config(filepath: Path, data: dict, mark_defaults: bool = False) -> None:
    """Write YAML configuration file with header.

    With `mark_defaults`, a field that has its default value gets a comment:
    the line is optional. The comments stay as long as the file has them.
    LF and UTF-8 on every platform, so the file is the same everywhere.
    """
    mark_defaults = mark_defaults or (filepath.is_file() and DEFAULT_COMMENT in filepath.read_text(encoding='utf-8'))
    marked = _default_lines(data.get('nested') or {}) if mark_defaults else ()
    lines = yaml.dump(data, default_flow_style=False, sort_keys=False).splitlines()
    with filepath.open('w', encoding='utf-8', newline='\n') as f:
        f.write(GITNESTED_HEADER)
        f.writelines(f'{line}  {DEFAULT_COMMENT}\n' if line.startswith(marked) else f'{line}\n' for line in lines)


def _default_lines(nested: dict) -> tuple[str, ...]:
    """How the lines of the fields that have their default value start."""
    return tuple(f'  {key}: ' for key, value in DEFAULTS.items() if str(nested.get(key)).lower() == value)
