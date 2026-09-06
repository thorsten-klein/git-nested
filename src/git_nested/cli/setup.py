"""Resolving a command's subdir into the four things every command needs.

`setup_command` is the shared preamble: it validates the subdir, derives
the ref name, finds the right .gitnested file, rejects a conflicting
worktree and loads the config -- applying any command-line overrides on
top.
"""

from __future__ import annotations

from pathlib import Path

from .. import gitfile, messages, output, refs
from ..constants import GITNESTED_FILENAME, GITNESTED_LEVEL_PREFIX
from ..git import GitRunner
from ..models import Flags, NestedConfig


def resolve_gitnested_file(subdir: Path) -> Path:
    """Determine the .gitnested (or highest .gitnested.levelN) file to use for subdir."""
    gitnested = subdir / GITNESTED_FILENAME

    # Search for .gitnested.levelN files to determine the correct level
    level_files = sorted([
        f
        for f in subdir.glob(f'{GITNESTED_LEVEL_PREFIX}*')
        if f.is_file() and f.name.startswith(GITNESTED_LEVEL_PREFIX)
    ])

    if level_files:
        # Use the highest level file found (for deeply nested repos)
        gitnested = level_files[-1]
        output.verbose(f"using {gitnested} (detected from the level files)")

    return gitnested


def _find_worktree_path(worktree_list: str, subdir: Path) -> str | None:
    """Find the worktree path whose branch matches nested/subdir, if one exists."""
    for line in worktree_list.splitlines():
        if f'[nested/{subdir}]' in line:
            return line.split()[0]
    return None


def _error_existing_worktree(subdir: Path, gitnested: Path, worktree_path: str | None) -> None:
    """Raise the appropriate 'worktree already exists' error message."""
    output.error(messages.worktree_exists(subdir, worktree_path, prunable=gitnested.exists()))


def _check_existing_worktree(git: GitRunner, command: str, subdir: Path, gitnested: Path) -> None:
    """Error out if an existing worktree for subdir conflicts with this command."""
    output.verbose(f"checking for a worktree on nested/{subdir}")
    worktree_list = git.check_output(['worktree', 'list'], may_fail=True) or ''
    worktree_path = _find_worktree_path(worktree_list, subdir)
    has_worktree = worktree_path is not None

    if command in ['commit'] and not has_worktree:
        output.error(f"{subdir}: no worktree to commit from; run 'git nested branch {subdir}' first")
    elif command not in ['branch', 'clean', 'commit', 'push'] and has_worktree:
        _error_existing_worktree(subdir, gitnested, worktree_path)


def _load_config_for_setup(command: str, gitnested: Path, flags: Flags, upstream: str | None) -> NestedConfig:
    """Load the existing .gitnested config, or initialize a fresh one for clone/init."""
    if command not in ['clone', 'init']:
        return gitfile.read_config(gitnested, flags)
    config = NestedConfig()
    if upstream:
        config.remote = upstream
    return config


def setup_command(
    git: GitRunner, command: str, flags: Flags, subdir: str | Path | None, upstream: str | None
) -> tuple[Path, Path, str, NestedConfig]:
    """Setup command with parameters.

    Returns:
        tuple: (subdir, gitnested, subref, config)
    """
    if not subdir:
        output.error("no subdir given, and none could be guessed")

    subdir = Path(subdir)

    if subdir.is_absolute():
        output.usage_error(f"{subdir}: subdir must be a relative path")

    subref = refs.sanitize_subref(git, str(subdir))

    # Determine the appropriate .gitnested file to use by detecting existing level files
    gitnested = resolve_gitnested_file(subdir)

    if not flags.force:
        _check_existing_worktree(git, command, subdir, gitnested)

    config = _load_config_for_setup(command, gitnested, flags, upstream)

    # Apply overrides (from command line flags)
    if flags.remote:
        config.remote = flags.remote
    if flags.branch:
        config.branch = flags.branch

    return subdir, gitnested, subref, config
