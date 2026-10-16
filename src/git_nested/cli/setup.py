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


def resolve_subdir(subdir: str | Path | None) -> Path:
    """The <subdir> a command was given, which has to be there and relative."""
    if not subdir:
        output.error("no subdir given, and none could be guessed")
    subdir = Path(subdir)
    # anchor, not is_absolute(): on Windows a rooted path such as /x has no drive
    # and so is not absolute, yet it still points outside the repository
    if subdir.anchor:
        output.usage_error(f"{subdir.as_posix()}: subdir must be a relative path")
    return subdir


def resolve_gitnested_file(subdir: Path) -> Path:
    """Determine the .gitnested (or highest .gitnested.levelN) file to use for subdir."""
    level_files = sorted(f for f in subdir.glob(f'{GITNESTED_LEVEL_PREFIX}*') if f.is_file())
    if not level_files:
        return subdir / GITNESTED_FILENAME
    # Use the highest level file found (for deeply nested repos)
    output.verbose(f"using {level_files[-1].as_posix()} (detected from the level files)")
    return level_files[-1]


def _check_existing_worktree(git: GitRunner, command: str, subdir: Path, gitnested: Path, branch: str) -> None:
    """Error out if an existing worktree of subdir's nested `branch` conflicts with this command."""
    output.verbose(f"checking for a worktree on {branch}")
    worktree_list = git.check_output(['worktree', 'list'], may_fail=True)
    worktree_path = next((line.split()[0] for line in worktree_list.splitlines() if f'[{branch}]' in line), None)

    if command == 'commit' and worktree_path is None:
        output.error(
            f"{subdir.as_posix()}: no worktree to commit from; run 'git nested branch {subdir.as_posix()}' first"
        )
    elif command not in ['branch', 'clean', 'commit', 'push', 'run'] and worktree_path is not None:
        output.error(messages.worktree_exists(subdir, worktree_path, prunable=gitnested.exists()))


def setup_command(
    git: GitRunner, command: str, flags: Flags, subdir: str | Path | None, upstream: str | None
) -> tuple[Path, Path, str, NestedConfig]:
    """Setup command with parameters.

    Returns:
        tuple: (subdir, gitnested, subref, config)
    """
    subdir = resolve_subdir(subdir)
    subref = refs.sanitize_subref(git, subdir.as_posix())
    gitnested = resolve_gitnested_file(subdir)

    if not flags.force:
        _check_existing_worktree(git, command, subdir, gitnested, refs.nested_branch(git, subref))

    # clone and init have no .gitnested to read yet; they start from scratch
    if command in ['clone', 'init']:
        config = NestedConfig(remote=flags.remote or upstream or '', branch=flags.branch or '')
    else:
        config = gitfile.read_config(gitnested, flags)

    return subdir, gitnested, subref, config
