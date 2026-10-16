"""Temporary worktrees and their branches."""

from __future__ import annotations

import shutil
from pathlib import Path

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


def list_worktrees(git: GitRunner) -> list[tuple[Path, str | None]]:
    """Every worktree of the repository, with the branch checked out in it (None when detached)."""
    porcelain = git.check_output(['worktree', 'list', '--porcelain'], may_fail=True)
    worktrees = []
    # One block per worktree, blank-line separated, of 'key value' lines.
    for block in porcelain.split('\n\n'):
        fields = {key: value for key, _, value in (line.partition(' ') for line in block.splitlines())}
        if 'worktree' in fields:
            branch = fields.get('branch', '').removeprefix('refs/heads/') or None
            worktrees.append((_relative(Path(fields['worktree'])), branch))
    return worktrees


def find_worktree(git: GitRunner, branch: str) -> Path | None:
    """Where `branch` is checked out, or None if it is not.

    Wherever that is: `git nested branch -d` puts it anywhere, so the
    default place under .git/tmp is no guide.
    """
    return next((path for path, checked_out in list_worktrees(git) if checked_out == branch), None)


def branch_at(git: GitRunner, path: Path) -> tuple[bool, str | None]:
    """Whether `path` is a worktree, and which branch it has checked out."""
    resolved = path.resolve()
    for worktree_path, checked_out in list_worktrees(git):
        if worktree_path.resolve() == resolved:
            return True, checked_out
    return False, None


def remove_worktree(git: GitRunner, worktree: Path | None) -> None:
    """Remove worktree, if there is one."""
    if worktree and worktree.is_dir():
        shutil.rmtree(worktree)
        git.run(['worktree', 'prune'])
        _remove_empty_parents(git, worktree)


def _remove_empty_parents(git: GitRunner, path: Path) -> None:
    """Remove the directories above `path` that are now empty, up to .git/tmp."""
    git_tmp = Path(git.check_output(['rev-parse', '--git-common-dir'])).resolve() / 'tmp'
    for parent in path.resolve().parents:
        if not parent.is_relative_to(git_tmp) or any(parent.iterdir()):
            return
        parent.rmdir()


def delete_branch(git: GitRunner, branch: str, git_tmp: Path) -> None:
    """Delete a branch."""
    remove_worktree(git, find_worktree(git, branch) or git_tmp / branch)
    git.run(['branch', '-D', branch], may_fail=True)
