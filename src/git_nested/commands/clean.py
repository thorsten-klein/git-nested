"""Removing the branches, worktrees and refs a nested repository leaves behind."""

from __future__ import annotations

from pathlib import Path

from .. import discovery, output, refs, worktree
from ..cli import setup
from ..git import GitRunner
from ..models import CommandContext, Flags


def do_clean(git: GitRunner, flags: Flags, subdir: Path, git_tmp: Path) -> list[str]:
    """Clean nested branches and refs."""
    subref = refs.sanitize_subref(git, subdir.as_posix())
    items = _delete_branch(git, refs.nested_branch(git, subref), git_tmp)
    refs.record_nested_branch(git, subref, None)
    if flags.force:
        _delete_refs(git, f'{subref}/')
    return items


def _delete_branch(git: GitRunner, branch: str, git_tmp: Path) -> list[str]:
    """Remove `branch` and its worktree; return what was removed."""
    worktree.remove_worktree(git, worktree.find_worktree(git, branch) or git_tmp / branch)
    if not git.branch_exists(branch):
        return []
    git.run(['update-ref', '-d', f'refs/heads/{branch}'])
    return [f"branch '{branch}'"]


def _delete_refs(git: GitRunner, suffix: str) -> None:
    """Delete every ref under refs/nested/<suffix>, and filter-branch's backups of nested/<suffix>."""
    prefixes = (f'refs/nested/{suffix}', f'refs/original/refs/heads/nested/{suffix}')
    for line in git.check_output(['show-ref'], may_fail=True).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith(prefixes):
            git.run(['update-ref', '-d', parts[1]])


def _clean_all(git: GitRunner, flags: Flags, git_tmp: Path) -> list[str]:
    """Clean every nested repository; with --force also what is left of former ones."""
    items = [
        item
        for subdir in discovery.find_all_nested_repositories(git, flags)
        for item in do_clean(git, flags, subdir, git_tmp)
    ]
    if flags.force:
        # Their .gitnested may be gone, so they are found by branch name.
        items += _delete_leftover_branches(git, git_tmp)
        _delete_refs(git, '')
    return items


def _delete_leftover_branches(git: GitRunner, git_tmp: Path) -> list[str]:
    """Remove every nested/* branch of this worktree, with its worktree."""
    leftover = git.check_output(['for-each-ref', '--format=%(refname:short)', 'refs/heads/nested/'])
    mine = [branch for branch in leftover.splitlines() if _of_this_worktree(git, branch)]
    return [item for branch in mine for item in _delete_branch(git, branch, git_tmp)]


def _of_this_worktree(git: GitRunner, branch: str) -> bool:
    """Whether `branch` is a nested branch of this worktree, not of another one."""
    suffix = refs.worktree_suffix(git)
    if suffix:
        return branch.endswith(suffix)
    worktrees = Path(git.check_output(['rev-parse', '--git-common-dir'])) / 'worktrees'
    others = [entry.name for entry in worktrees.iterdir()] if worktrees.is_dir() else []
    return not any(branch.endswith(f'@{name}') for name in others)


def cmd_clean(ctx: CommandContext) -> None:
    """Remove branches, remotes and refs for a nested repo, or for all of them."""
    if ctx.flags.all:
        items = _clean_all(ctx.git, ctx.flags, ctx.tmp)
    else:
        subdir, _, _, _ = setup.setup_command(ctx.git, 'clean', ctx.flags, ctx.subdir, ctx.upstream)
        items = do_clean(ctx.git, ctx.flags, subdir, ctx.tmp)
    for item in items:
        output.say(f"removed {item}")
