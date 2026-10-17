"""Preconditions asserted before a command runs."""

from __future__ import annotations

from pathlib import Path

from . import output
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags


def check_repository(git: GitRunner, command: str, flags: Flags) -> tuple[Path | None, str | None]:
    """Check that repository is ready.

    Returns:
        tuple: (git_tmp, head_commit)
    """
    if command in ['completion', 'version']:
        return None, None

    try:
        git.run(['rev-parse', '--git-dir'])
    except GitNestedError:
        # A deliberate re-interpretation of git's own message, not an
        # incidental failure, so the chain is suppressed -- and since
        # nothing is printed until an error leaves the command, this is
        # the only line the user sees.
        raise GitNestedError("not inside a git repository") from None

    # Per worktree of this repository, so they do not block each other.
    git_tmp = Path(git.check_output(['rev-parse', '--git-dir'])) / 'tmp'

    # Not a nested branch. A detached HEAD is fine: commits go there, as with git commit.
    current_branch = git.check_output(['symbolic-ref', '--short', '--quiet', 'HEAD'], may_fail=True)
    if current_branch.startswith('nested/'):
        raise GitNestedError(f"can't {command} while the nested branch {current_branch} is checked out")

    if git.check_output(['rev-parse', '--is-inside-work-tree'], may_fail=True) != 'true':
        raise GitNestedError("not inside a git working tree")

    if _needs_clean_worktree(command, flags):
        check_worktree_clean(git, command)

    # `git rev-parse HEAD` prints the literal string `HEAD` on an unborn branch,
    # so the exit code has to decide whether there is a commit.
    head = git.run(['rev-parse', 'HEAD'], may_fail=True)
    return git_tmp, head.stdout.strip() if head.returncode == 0 else None


def _needs_clean_worktree(command: str, flags: Flags) -> bool:
    """Whether `command` writes to the parent worktree or index."""
    return command in ['clone', 'commit', 'init', 'pull', 'repair'] or (command == 'push' and flags.commit)


def check_worktree_clean(git: GitRunner, command: str) -> None:
    """Ensure working copy has no uncommitted changes."""
    if command not in ['clone', 'init', 'pull', 'push', 'branch', 'commit', 'diff', 'repair']:
        return

    pwd = Path.cwd().as_posix()
    git.run(['update-index', '-q', '--ignore-submodules', '--refresh'], may_fail=True)
    if git.run(['diff-files', '--quiet', '--ignore-submodules'], may_fail=True).returncode != 0:
        raise GitNestedError(f"{pwd}: can't {command}, there are unstaged changes")

    if command == 'clone' and not git.rev_exists('HEAD'):
        # This may happen when cloning into an empty repository
        return
    if git.run(['rev-parse', '--verify', 'HEAD'], may_fail=True).returncode != 0:
        raise GitNestedError(f"{pwd}: HEAD cannot be verified")
    if git.run(['diff-index', '--quiet', '--ignore-submodules', 'HEAD'], may_fail=True).returncode != 0:
        raise GitNestedError(f"{pwd}: can't {command}, the working tree has changes")
    if git.run(['diff-index', '--quiet', '--cached', '--ignore-submodules', 'HEAD'], may_fail=True).returncode != 0:
        raise GitNestedError(f"{pwd}: can't {command}, the index has changes")


def warn_uncommitted_subdir_changes(git: GitRunner, command: str, flags: Flags, subdir: Path) -> None:
    """Warn when `command` ignores uncommitted changes in `subdir`."""
    if command not in ['branch', 'diff', 'push'] or (command == 'push' and flags.commit):
        return

    git.run(['update-index', '-q', '--ignore-submodules', '--refresh'], may_fail=True)
    pathspec = ['--', subdir.as_posix()]
    if git.run(['diff-files', '--quiet', '--ignore-submodules', *pathspec], may_fail=True).returncode != 0:
        output.warn(f"{subdir.as_posix()}: has uncommitted changes; {command} uses only committed content")
        return
    if git.run(['rev-parse', '--verify', 'HEAD'], may_fail=True).returncode != 0:
        return
    if (
        git.run(
            ['diff-index', '--quiet', '--cached', '--ignore-submodules', 'HEAD', *pathspec], may_fail=True
        ).returncode
        != 0
    ):
        output.warn(f"{subdir.as_posix()}: has uncommitted changes; {command} uses only committed content")
