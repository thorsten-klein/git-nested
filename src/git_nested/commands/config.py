"""Reading and writing a nested repository's .gitnested configuration."""

from __future__ import annotations

from pathlib import Path

from .. import gitfile, output, yamlio
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext

# Keyed by field name; a field absent from here takes any value.
_VALID_VALUES: dict[str, tuple[str, ...]] = {
    'method': ('merge', 'rebase'),
    'squash': ('true', 'false'),
    'readonly': ('true', 'false'),
}


def read_fields(gitnested: Path) -> dict[str, str]:
    """The fields the .gitnested file actually sets, in the documented order, each as one line."""
    if not gitnested.is_file():
        raise GitNestedError(f"{gitnested.as_posix()} does not exist")
    nested = yamlio._read_yaml_config(gitnested).get('nested') or {}
    return {
        # A filter is a list; it prints as one space-separated line.
        field: ' '.join(map(str, value)) if isinstance(value, list) else str(value)
        for field in gitfile.CONFIG_FIELDS
        if (value := nested.get(field)) not in (None, '', [])
    }


def write_field(git: GitRunner, gitnested: Path, key: str, value: str) -> None:
    """Set one field of the .gitnested file and stage the change; only the fields a user may set."""
    if key not in gitfile.WRITABLE_CONFIG_FIELDS:
        writable = ', '.join(gitfile.WRITABLE_CONFIG_FIELDS)
        raise GitNestedError(f"{key} is written by git-nested itself; the settable fields are {writable}")
    valid = _VALID_VALUES.get(key)
    if valid and value not in valid:
        raise GitNestedError(f"{value} is not a valid {key}; use one of {', '.join(valid)}")
    data = yamlio._read_yaml_config(gitnested)
    data.setdefault('nested', {})[key] = value
    yamlio._write_yaml_config(gitnested, data)
    git.run(['add', '-f', '--', gitnested])


def cmd_config(ctx: CommandContext) -> None:
    """Read or write one field of a nested repository's .gitnested file."""
    subdir = setup.resolve_subdir(ctx.subdir)
    gitnested = setup.resolve_gitnested_file(subdir)
    key, value = ctx.config_key, ctx.config_value

    if key is None:
        for field, field_value in read_fields(gitnested).items():
            output.payload(f"{field} {field_value}")
        return

    if key not in gitfile.CONFIG_FIELDS:
        raise GitNestedError(f"unknown config key {key}; the known keys are {', '.join(gitfile.CONFIG_FIELDS)}")
    if value is None:
        # A field the file does not set prints nothing at all
        if (current := read_fields(gitnested).get(key)) is not None:
            output.payload(current)
        return

    write_field(ctx.git, gitnested, key, value)
    output.say(f"{subdir.as_posix()}: {key} set to {value}")
