"""Temporary worktrees and their branches."""

from __future__ import annotations

import shutil
from pathlib import Path

from . import checks
from ._compat import chdir
from .git import GitRunner


def _relative(path: Path) -> Path:
    """`path` relative to the current directory (the repository top) when it lies inside it.

    git lists worktrees by absolute path; the ones under .git/tmp read
    better, and the same as the rest of git-nested's output, without it.
    """
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


def _parse_worktree_block(block: str) -> tuple[Path, str | None] | None:
    """One worktree from `git worktree list --porcelain`: its path and checked-out branch."""
    fields = {key: value for key, _, value in (line.partition(' ') for line in block.splitlines())}
    if 'worktree' not in fields:
        return None
    branch = fields.get('branch', '').removeprefix('refs/heads/') or None
    return _relative(Path(fields['worktree'])), branch


def list_worktrees(git: GitRunner) -> list[tuple[Path, str | None]]:
    """Every worktree of the repository, with the branch checked out in it (None when detached)."""
    porcelain = git.check_output(['worktree', 'list', '--porcelain'], may_fail=True) or ''
    # One block per worktree, blank-line separated, of 'key value' lines.
    parsed = (_parse_worktree_block(block) for block in porcelain.split('\n\n'))
    return [entry for entry in parsed if entry]


def find_worktree(git: GitRunner, branch: str) -> Path | None:
    """Where `branch` is checked out, or None if it is not.

    Wherever that is: `git nested worktree -d` puts it anywhere, so the
    default place under .git/tmp is no guide.
    """
    for path, checked_out in list_worktrees(git):
        if checked_out == branch:
            return path
    return None


def branch_at(git: GitRunner, path: Path) -> tuple[bool, str | None]:
    """Whether `path` is a worktree, and which branch it has checked out."""
    resolved = path.resolve()
    for worktree_path, checked_out in list_worktrees(git):
        if worktree_path.resolve() == resolved:
            return True, checked_out
    return False, None


def create_worktree(git: GitRunner, branch: str, git_tmp: Path, path: Path | None = None) -> Path:
    """Create a worktree for the given branch, at `path` or else in the default place under git_tmp."""
    subdir_worktree = path or git_tmp / branch
    git.run(['worktree', 'add', subdir_worktree, branch])
    return subdir_worktree


def remove_worktree(git: GitRunner, worktree: Path | None) -> None:
    """Remove worktree."""
    if not worktree:
        return

    worktree_path = Path(worktree)
    if not worktree_path.is_dir():
        return

    with chdir(worktree):
        checks.check_worktree_clean(git, 'clean')

    shutil.rmtree(worktree)
    git.run(['worktree', 'prune'])


def delete_branch(git: GitRunner, branch: str, git_tmp: Path) -> None:
    """Delete a branch."""
    remove_worktree(git, find_worktree(git, branch) or git_tmp / branch)
    git.run(['branch', '-D', branch], may_fail=True)
