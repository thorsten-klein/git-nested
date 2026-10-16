"""Diffing a nested subdirectory against its upstream."""

from __future__ import annotations

from pathlib import Path

from .. import filters, output
from ..cli import setup
from ..models import CommandContext
from . import fetch


def cmd_diff(ctx: CommandContext) -> None:
    """Show the local diff of a nested repo compared to the freshly fetched upstream."""
    git = ctx.git
    subdir, _, subref, config = setup.setup_command(git, 'diff', ctx.flags, ctx.subdir, ctx.upstream)

    if config.remote == 'none':
        output.say(f"{subdir.as_posix()}: skipped, it has no remote")
        return

    upstream = fetch.do_fetch(git, config, subref)
    if config.filter:
        upstream = filters.build_filtered_commit(git, Path.cwd(), config.filter, upstream)
    local_tree = git.check_output(['rev-parse', f'HEAD:{subdir.as_posix()}'])
    diff = git.check_output(['diff', local_tree, upstream, '--', ':(exclude,glob)**/.gitnested*'])

    if diff:
        output.payload(diff)
    else:
        output.say(f"{subdir.as_posix()}: no differences from {config.remote} ({config.branch})")
