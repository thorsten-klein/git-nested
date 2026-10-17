"""Reading and writing the .gitnested file, as YAML or as TOML.

TOML needs Python 3.11 or newer, which has tomllib.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

from .errors import GitNestedError
from .messages import GITNESTED_HEADER

if sys.version_info >= (3, 11):  # pragma: no cover -- the branch not taken is the other Python's
    import tomllib
else:  # pragma: no cover -- only 3.10 runs this
    tomllib: Any = None

FORMATS = ('yaml', 'toml')


def is_toml_text(text: str) -> bool:
    """A TOML .gitnested has a [nested] table; a YAML one has nested: instead."""
    return any(line.strip() == '[nested]' for line in text.splitlines())


def is_toml(filepath: Path) -> bool:
    """Whether filepath exists and is written in TOML."""
    return filepath.is_file() and is_toml_text(filepath.read_text(encoding='utf-8'))


def need_toml(name: str) -> None:
    """Raise if this Python cannot read TOML."""
    if tomllib is None:  # pragma: no cover -- only 3.10 runs this
        raise GitNestedError(f"{name} is TOML, which needs Python 3.11 or newer")


def parse(text: str, name: str = '.gitnested') -> dict:
    """Parse the content of a .gitnested file. Raises GitNestedError if it is broken."""
    try:
        if is_toml_text(text):
            need_toml(name)
            return tomllib.loads(text)  # pragma: no cover -- 3.10 never gets here
        return yaml.safe_load(text) or {}
    except (yaml.YAMLError, ValueError) as e:
        # tomllib.TOMLDecodeError is a ValueError
        raise GitNestedError(f"cannot read {name}: {e}") from e


def read(filepath: Path) -> dict:
    """Read a .gitnested file."""
    return parse(filepath.read_text(encoding='utf-8'), filepath.as_posix())


def write(filepath: Path, data: dict, toml: bool | None = None) -> None:
    """Write a .gitnested file with the header on top.

    `toml` None keeps the format the file has now. LF and UTF-8 on every
    platform, so the file is the same everywhere.
    """
    if toml is None:
        toml = is_toml(filepath)
    body = _dump_toml(data) if toml else yaml.dump(data, default_flow_style=False, sort_keys=False)
    with filepath.open('w', encoding='utf-8', newline='\n') as f:
        f.write(GITNESTED_HEADER)
        f.write(body)


def _dump_toml(data: dict) -> str:
    """TOML for data: one table per top-level key, with plain values in it."""
    lines: list[str] = []
    for table, fields in data.items():
        lines.append(f'[{table}]')
        lines.extend(f'{key} = {_toml_value(value)}' for key, value in (fields or {}).items() if value is not None)
    return '\n'.join(lines) + '\n'


def _toml_value(value: object) -> str:
    """One TOML value. Strings use JSON quoting, which TOML reads the same way."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return '[' + ', '.join(_toml_value(item) for item in value) + ']'
    # TOML wants DEL escaped; JSON leaves it as it is.
    return json.dumps(str(value), ensure_ascii=False).replace('\x7f', '\\u007f')
