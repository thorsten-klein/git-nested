"""Creating a branch that holds the nested repository's own commits."""

from __future__ import annotations

from .. import content, output, worktree
from ..cli import setup
from ..models import CommandContext
from . import fetch


def cmd_branch(ctx: CommandContext) -> None:
    """Create a branch containing the local nested repo commits."""
    git = ctx.git
    flags, subdir, upstream, git_tmp = ctx.flags, ctx.subdir, ctx.upstream, ctx.tmp
    subdir, gitnested, subref, config = setup.setup_command(git, 'branch', flags, subdir, upstream)

    if flags.fetch:
        fetch.do_fetch(git, config, subref)

    branch = f'nested/{subref}'
    if flags.force:
        worktree.delete_branch(git, branch, git_tmp)
    elif git.branch_exists(branch):
        output.error(f"Branch '{branch}' already exists. Use '--force' to override.")

    subdir_worktree = content.create_nested_branch(
        git=git,
        flags=flags,
        config=config,
        branch=branch,
        subdir=subdir,
        gitnested=gitnested,
        git_tmp=git_tmp,
        subref=subref,
        command='branch',
    )
    output.say(f"Created branch '{branch}' and worktree '{subdir_worktree}'.")
