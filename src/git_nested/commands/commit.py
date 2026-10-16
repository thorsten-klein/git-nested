"""Committing a merged nested branch back into the parent repository."""

from __future__ import annotations

from .. import content, output, refs, worktree
from ..cli import setup
from ..models import CommandContext
from . import fetch


def cmd_commit(ctx: CommandContext) -> None:
    """Commit a merged nested branch."""
    git, flags = ctx.git, ctx.flags
    subdir, gitnested, subref, config = setup.setup_command(git, 'commit', flags, ctx.subdir, ctx.upstream)

    if flags.fetch:
        fetch.do_fetch(git, config, subref)

    refs_fetch = f'refs/nested/{subref}/fetch'
    if not git.rev_exists(refs_fetch):
        output.error(f"no ref {refs_fetch}; run 'git nested fetch' first, or pass -F")

    branch = refs.nested_branch(git, subref)
    nested_commit_ref = ctx.nested_commit_ref or branch
    content.commit_nested_branch(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        nested_commit_ref=nested_commit_ref,
        upstream_head_commit=git.check_output(['rev-parse', refs_fetch]),
        head_commit=ctx.head,
        subdir_worktree=worktree.find_worktree(git, branch) or ctx.tmp / branch,
        command='commit',
    )
    output.say(f"{subdir.as_posix()}: committed {nested_commit_ref}")
