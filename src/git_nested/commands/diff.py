"""Diffing a nested subdirectory against its upstream."""

from __future__ import annotations

from pathlib import Path

from .. import filters, output
from ..cli import setup
from ..git import GitRunner
from ..models import CommandContext, NestedConfig
from . import fetch


def get_diff(git: GitRunner, config: NestedConfig, subdir: Path, subref: str) -> str:
    """Compute the diff between the local nested repository content and the freshly fetched upstream content.

    Returns:
        diff text (empty string if there are no differences)
    """
    upstream_head_commit = fetch.do_fetch(git, config, subref)

    local_tree = git.check_output(['rev-parse', f'HEAD:{subdir}'])

    if config.filter:
        upstream_target = filters.build_filtered_commit(git, Path.cwd(), config, upstream_head_commit)
    else:
        upstream_target = upstream_head_commit

    return git.check_output([
        'diff',
        local_tree,
        upstream_target,
        '--',
        ':(exclude,glob)**/.gitnested*',
    ])


def cmd_diff(ctx: CommandContext) -> None:
    """Show the local diff of a nested repo compared to upstream."""
    git = ctx.git
    flags, subdir, upstream = ctx.flags, ctx.subdir, ctx.upstream
    subdir, _gitnested, subref, config = setup.setup_command(git, 'diff', flags, subdir, upstream)

    if config.remote == 'none':
        output.say(f"{subdir}: skipped, it has no remote")
        return

    diff_output = get_diff(git, config, subdir, subref)

    if not diff_output:
        output.say(f"{subdir}: no differences from {config.remote} ({config.branch})")
    else:
        output.payload(diff_output)
