"""Temporary worktrees and their branches."""

from __future__ import annotations

import shutil
from contextlib import chdir
from pathlib import Path

from . import checks
from .git import GitRunner


def create_worktree(git: GitRunner, branch: str, git_tmp: Path) -> Path:
    """Create a worktree for the given branch."""
    subdir_worktree = git_tmp / branch
    git.run(['worktree', 'add', subdir_worktree, branch])
    return subdir_worktree


def remove_worktree(git: GitRunner, worktree: Path | None):
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


def delete_branch(git: GitRunner, branch: str, git_tmp: Path):
    """Delete a branch."""
    subdir_worktree = git_tmp / branch
    remove_worktree(git, subdir_worktree)
    git.run(['branch', '-D', branch], may_fail=True)
