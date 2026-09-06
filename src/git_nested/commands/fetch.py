"""Fetching a nested repository's upstream branch."""

from __future__ import annotations

from .. import output, refs
from ..cli import setup
from ..constants import FETCH_HEAD_REV
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, NestedConfig


def do_fetch(git: GitRunner, config: NestedConfig, subref: str) -> str:
    """Fetch upstream content.

    Returns:
        upstream_head_commit
    """
    if config.remote == 'none':
        raise GitNestedError("can't fetch, the remote is 'none'")

    branch_info = f"({config.branch})" if config.branch else ""
    output.verbose(f"fetching {config.remote} {branch_info}")

    cmd = ['fetch', '--no-tags', '--quiet', config.remote]
    if config.branch:
        cmd.append(config.branch)

    git.run(cmd)

    output.verbose("reading the upstream HEAD commit")
    upstream_head_commit = git.check_output(['rev-parse', FETCH_HEAD_REV])

    refs.create_nested_ref(git, subref, 'fetch', FETCH_HEAD_REV)

    return upstream_head_commit


def cmd_fetch(ctx: CommandContext) -> None:
    """Fetch a nested repo's remote branch."""
    git = ctx.git
    flags, subdir, upstream = ctx.flags, ctx.subdir, ctx.upstream
    subdir, _, subref, config = setup.setup_command(git, 'fetch', flags, subdir, upstream)

    if config.remote == 'none':
        output.say(f"{subdir}: skipped, it has no remote")
    else:
        do_fetch(git, config, subref)
        output.say(f"{subdir}: fetched from {config.remote} ({config.branch})")
