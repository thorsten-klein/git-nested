"""Repairing a .gitnested file whose sync point is no longer part of the history."""

from __future__ import annotations

import textwrap
from pathlib import Path

from .. import content, history, output, yamlio
from .._version import VERSION
from ..cli import setup
from ..git import GitRunner
from ..models import CommandContext


def _write_parent(git: GitRunner, gitnested: Path, parent: str) -> None:
    """Set the parent field of gitnested and stage the change."""
    data = yamlio._read_yaml_config(gitnested)
    data.setdefault('nested', {})['parent'] = parent
    yamlio._write_yaml_config(gitnested, data)
    git.run(['add', '-f', '--', gitnested])


def _repair_message(git: GitRunner, subdir: Path, parent: str) -> str:
    """The default commit message, in the shape the other nested commits use."""
    short = git.check_output(['rev-parse', '--short', parent])
    return textwrap.dedent(
        f"""\
        git nested repair

        nested:
          subdir:   "{subdir.as_posix()}"
          parent:   "{short}"
        git-nested:
          version:  "{VERSION}"
        """
    )


def cmd_repair(ctx: CommandContext) -> None:
    """Point the parent of a .gitnested file back at a commit of HEAD's history, and commit that.

    A pull made on a branch that was later squash-merged (or rebased) records
    a parent that only that branch has, so every command that rebuilds the
    nested history from it fails afterwards. The pull's copy on this history
    tells where the sync point is now.
    """
    git = ctx.git
    subdir, gitnested, _, config = setup.setup_command(git, 'repair', ctx.flags, ctx.subdir, None)

    if not config.parent:
        output.say(f"{subdir.as_posix()}: no sync point recorded, nothing to repair")
        return
    if history.parent_is_ancestor(git, config.parent):
        output.say(f"{subdir.as_posix()}: the sync point is part of HEAD's history, nothing to repair")
        return

    sync_point = history.find_sync_point(git, gitnested)
    if sync_point is None:
        output.error(
            f"{subdir.as_posix()}: no sync point in HEAD's history to repair to; "
            "no commit with a parent of its own ever brought it in step with upstream"
        )

    output.verbose(f"the sync point in HEAD's history is {sync_point}")
    _write_parent(git, gitnested, sync_point)
    content._commit_gitnested_update(git, ctx.flags, ctx.flags.message or _repair_message(git, subdir, sync_point))
    output.say(f"{subdir.as_posix()}: sync point repaired, parent is now {sync_point}")
