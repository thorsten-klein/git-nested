"""Removing the branches, worktrees and refs a nested repository leaves behind."""

from __future__ import annotations

from pathlib import Path

from .. import output, refs, worktree
from ..cli import setup
from ..git import GitRunner
from ..models import CommandContext, Flags


def do_clean(git: GitRunner, flags: Flags, subdir: Path, git_tmp: Path) -> list[str]:
    """Clean nested branches and refs."""
    items = []
    subref = refs.sanitize_subref(git, subdir.as_posix())
    branch = refs.nested_branch(git, subref)
    worktree.remove_worktree(git, worktree.find_worktree(git, branch) or git_tmp / branch)

    if git.branch_exists(branch):
        git.run(['update-ref', '-d', f'refs/heads/{branch}'])
        items.append(f"branch '{branch}'")
    refs.record_nested_branch(git, subref, None)

    if flags.force:
        _delete_refs(git, '' if flags.all else f'{subref}/')
    return items


def _delete_refs(git: GitRunner, suffix: str) -> None:
    """Delete every ref under refs/nested/<suffix>, and filter-branch's backups of nested/<suffix>."""
    prefixes = (f'refs/nested/{suffix}', f'refs/original/refs/heads/nested/{suffix}')
    for line in git.check_output(['show-ref'], may_fail=True).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith(prefixes):
            git.run(['update-ref', '-d', parts[1]])


def cmd_clean(ctx: CommandContext) -> None:
    """Remove branches, remotes and refs for a nested repo."""
    subdir, _, _, _ = setup.setup_command(ctx.git, 'clean', ctx.flags, ctx.subdir, ctx.upstream)
    for item in do_clean(ctx.git, ctx.flags, subdir, ctx.tmp):
        output.say(f"removed {item}")
