"""Preconditions asserted before a command runs."""

from __future__ import annotations

from pathlib import Path

from .errors import GitNestedError
from .git import GitRunner


def _check_current_branch(git: GitRunner, command: str) -> None:
    """Ensure a real branch (not a nested branch, not detached HEAD) is checked out."""
    current_branch = git.check_output(['symbolic-ref', '--short', '--quiet', 'HEAD'], may_fail=True)
    if current_branch.startswith('nested/'):
        raise GitNestedError(f"Can't '{command}' while a nested branch is checked out: {current_branch}")

    if not current_branch or current_branch in ['HEAD']:
        raise GitNestedError("Must be on a branch to run this command.")


def check_repository(git: GitRunner, command: str) -> tuple[Path | None, str | None]:
    """Check that repository is ready.

    Returns:
        tuple: (git_tmp, head_commit)
    """
    if command in ['version']:
        return None, None

    try:
        git.run(['rev-parse', '--git-dir'])
    except GitNestedError:
        # git.run() already printed the underlying git error to stderr;
        # this is a deliberate, more user-friendly re-interpretation of
        # it, not an incidental failure, so the chain is suppressed.
        raise GitNestedError("Not inside a git repository.") from None

    git_common_dir = git.check_output(['rev-parse', '--git-common-dir'])
    git_tmp = Path(git_common_dir) / 'tmp'

    _check_current_branch(git, command)

    inside_worktree = git.check_output(['rev-parse', '--is-inside-work-tree'], may_fail=True)
    if inside_worktree != 'true':
        raise GitNestedError("Must run inside a git working tree.")

    check_worktree_clean(git, command)

    parents = git.check_output(['rev-parse', '--show-prefix'], may_fail=True)
    if parents:
        raise GitNestedError("Need to run nested command from top level directory of the repo.")

    # Store the current HEAD (may fail in case of an empty repository)
    head_commit = git.check_output(['rev-parse', 'HEAD'], may_fail=True)

    return git_tmp, head_commit


def _check_head_and_index_clean(git: GitRunner, command: str, pwd: Path) -> None:
    """Ensure HEAD is verifiable and the working tree/index have no pending changes."""
    if command == 'clone' and not git.rev_exists('HEAD'):
        # This may happen when cloning into an empty repository
        return

    result = git.run(['rev-parse', '--verify', 'HEAD'], may_fail=True)
    if result.returncode != 0:
        raise GitNestedError(f"HEAD cannot be verified ({pwd})")

    result = git.run(['diff-index', '--quiet', '--ignore-submodules', 'HEAD'], may_fail=True)
    if result.returncode != 0:
        raise GitNestedError(f"Can't {command} nested repository. Working tree has changes. ({pwd})")

    result = git.run(['diff-index', '--quiet', '--cached', '--ignore-submodules', 'HEAD'], may_fail=True)
    if result.returncode != 0:
        raise GitNestedError(f"Can't {command} nested repository. Index has changes. ({pwd})")


def check_worktree_clean(git: GitRunner, command: str):
    """Ensure working copy has no uncommitted changes."""
    if command not in ['clone', 'init', 'pull', 'push', 'branch', 'commit', 'diff']:
        return

    pwd = Path.cwd()
    git.run(['update-index', '-q', '--ignore-submodules', '--refresh'], may_fail=True)

    # Check for unstaged changes
    result = git.run(['diff-files', '--quiet', '--ignore-submodules'], may_fail=True)
    if result.returncode != 0:
        raise GitNestedError(f"Can't {command} nested repository. Unstaged changes. ({pwd})")

    _check_head_and_index_clean(git, command, pwd)


def check_subdir_for_init(git: GitRunner, subdir: Path, gitnested: Path):
    """Check subdir is ready for init."""
    if not subdir.exists():
        raise GitNestedError(f"'{subdir}' does not exist.")

    if gitnested.exists():
        raise GitNestedError(f"'{subdir}' is already a nested repository.")

    if not git.is_tracked(subdir):
        raise GitNestedError(f"'{subdir}' exists, but nothing is tracked by git.")
