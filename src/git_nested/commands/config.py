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
}


def _format_value(value) -> str:
    """One field's value as a single line: a filter is a list, everything else a scalar."""
    if isinstance(value, list):
        return ' '.join(str(item) for item in value)
    return str(value)


def read_fields(gitnested: Path) -> dict[str, str]:
    """The fields the .gitnested file actually sets, in the documented order."""
    if not gitnested.is_file():
        raise GitNestedError(f"No '{gitnested}' file.")
    nested = yamlio._read_yaml_config(gitnested).get('nested') or {}
    return {
        field: _format_value(nested[field])
        for field in gitfile.CONFIG_FIELDS
        if nested.get(field) not in (None, '', [])
    }


def _check_writable(key: str, value: str) -> None:
    """Reject a field git-nested owns, or a value it would not accept."""
    if key not in gitfile.WRITABLE_CONFIG_FIELDS:
        writable = ', '.join(gitfile.WRITABLE_CONFIG_FIELDS)
        raise GitNestedError(f"'{key}' is written by git-nested itself. Settable fields: {writable}.")
    valid = _VALID_VALUES.get(key)
    if valid and value not in valid:
        raise GitNestedError(f"'{value}' is not a valid '{key}'. Use one of: {', '.join(valid)}.")


def write_field(git: GitRunner, gitnested: Path, key: str, value: str) -> None:
    """Set one field of the .gitnested file and stage the change."""
    _check_writable(key, value)
    data = yamlio._read_yaml_config(gitnested)
    data.setdefault('nested', {})[key] = value
    yamlio._write_yaml_config(gitnested, data)
    git.run(['add', '-f', '--', gitnested])


def _check_known(key: str) -> None:
    """Reject a field that is not part of a .gitnested file at all."""
    if key not in gitfile.CONFIG_FIELDS:
        raise GitNestedError(f"Unknown config key '{key}'. Known keys: {', '.join(gitfile.CONFIG_FIELDS)}.")


def _print_all(gitnested: Path) -> None:
    """Print every field the file sets, one 'key value' line each."""
    for field, value in read_fields(gitnested).items():
        output.payload(f"{field} {value}")


def _print_one(gitnested: Path, key: str) -> None:
    """Print one field's value, or nothing at all if the file does not set it."""
    value = read_fields(gitnested).get(key)
    if value is not None:
        output.payload(value)


def _resolve_gitnested(subdir: str | Path | None) -> tuple[Path, Path]:
    """The subdir and the .gitnested file to read or write.

    Returns:
        tuple: (subdir, gitnested)
    """
    if not subdir:
        output.error("subdir not set")
    subdir = Path(subdir)
    if subdir.is_absolute():
        output.usage_error(f"The subdir '{subdir}' should not be absolute path.")
    return subdir, setup.resolve_gitnested_file(subdir)


def cmd_config(ctx: CommandContext) -> None:
    """Read or write one field of a nested repository's .gitnested file."""
    subdir, gitnested = _resolve_gitnested(ctx.subdir)

    if ctx.config_key is None:
        _print_all(gitnested)
        return

    _check_known(ctx.config_key)
    if ctx.config_value is None:
        _print_one(gitnested, ctx.config_key)
        return

    write_field(ctx.git, gitnested, ctx.config_key, ctx.config_value)
    output.say(f"Set '{ctx.config_key}' of '{subdir}' to '{ctx.config_value}'.")
