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
    subref = refs.sanitize_subref(git, str(subdir))
    branch = f'nested/{subref}'
    ref = f'refs/heads/{branch}'
    subdir_worktree = git_tmp / branch

    worktree.remove_worktree(git, subdir_worktree)

    if git.branch_exists(branch):
        git.run(['update-ref', '-d', ref])
        items.append(f"branch '{branch}'")

    if flags.force:
        suffix = '' if flags.all else f'{subref}/'
        _force_clean_refs(git, suffix)

    return items


def _ref_matches_clean_target(ref: str, suffix: str) -> bool:
    """Check whether a ref name is one a force-clean of `suffix` should delete."""
    return ref.startswith((f'refs/nested/{suffix}', f'refs/original/refs/heads/nested/{suffix}'))


def _force_clean_refs(git: GitRunner, suffix: str) -> None:
    """Delete every ref matching the nested/<suffix> prefix (the --force sweep)."""
    show_ref = git.check_output(['show-ref'], may_fail=True) or ''
    for line in show_ref.splitlines():
        parts = line.split()
        if len(parts) >= 2 and _ref_matches_clean_target(parts[1], suffix):
            git.run(['update-ref', '-d', parts[1]])


def cmd_clean(ctx: CommandContext) -> None:
    """Remove branches, remotes and refs for a nested repo."""
    git = ctx.git
    flags, subdir, upstream, git_tmp = ctx.flags, ctx.subdir, ctx.upstream, ctx.tmp
    subdir, _, _, _ = setup.setup_command(git, 'clean', flags, subdir, upstream)

    for item in do_clean(git, flags, subdir, git_tmp):
        output.say(f"Removed {item}.", flags)
