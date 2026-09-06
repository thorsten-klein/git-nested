"""Running git as a subprocess."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any  # kwargs forwarded to subprocess.run, whose own stub types them Any

from . import output
from .constants import REQUIRED_GIT_VERSION
from .errors import GitNestedError


def _git_env(env: dict[str, str] | None) -> dict[str, str]:
    """``env`` for a git subprocess, with git's slowest footgun defused.

    `git filter-branch` prints its "glut of gotchas" warning and then sleeps
    for ten seconds unless FILTER_BRANCH_SQUELCH_WARNING is set. git-nested
    calls filter-branch on the pull/push/branch/commit paths, so without this
    every one of those operations costs the user a flat ten seconds waiting
    out a warning about a command they did not choose to run and cannot act
    on. setdefault, so an explicit value from the environment still wins.
    """
    merged = dict(os.environ if env is None else env)
    merged.setdefault('FILTER_BRANCH_SQUELCH_WARNING', '1')
    return merged


class GitRunner:
    """Simplified git command execution."""

    def __init__(self) -> None:
        """Check the environment and record the detected git version."""
        self.check()
        self.version = self.get_version()

    def run(self, args: Sequence[str | Path], may_fail: bool = False, **kwargs: Any) -> subprocess.CompletedProcess:  # noqa: ANN401
        """Run git command."""
        # Convert any Path objects to strings
        cmd = ['git'] + [str(arg) for arg in args]
        output.trace(' '.join(cmd))
        kwargs['env'] = _git_env(kwargs.get('env'))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)
        if result.returncode != 0:
            if not may_fail:
                raise GitNestedError(f"command failed: {' '.join(cmd)}\n{result.stderr!s}")

            # Exception occurred but may_fail=True: Create a fake CompletedProcess for exception case
            return subprocess.CompletedProcess(args=cmd, returncode=-1, stdout=result.stdout, stderr=result.stderr)

        # Command succeeded
        return result

    def check_output(self, args: Sequence[str | Path], may_fail: bool = False, **kwargs: Any) -> str:  # noqa: ANN401
        """Run git command and return its stripped stdout."""
        result = self.run(args=args, may_fail=may_fail, **kwargs)
        return result.stdout.strip()

    def is_tracked(self, path: Path) -> bool:
        """Check if given path is tracked by git.

        'git ls-files' exits 0 regardless of whether it matched anything, so the presence
        of output -- not the exit code -- is what actually answers the question.
        """
        result = self.run(['ls-files', '--', path], may_fail=True)
        return bool(result.stdout.strip())

    def rev_exists(self, rev: str) -> bool:
        """Check if revision exists."""
        result = self.run(['rev-list', rev, '-1'], may_fail=True)
        return result.returncode == 0

    def branch_exists(self, branch: str) -> bool:
        """Check if branch exists."""
        return self.rev_exists(f'refs/heads/{branch}')

    def commit_in_rev_list(self, commit: str, list_head: str) -> bool:
        """Check if commit is in rev-list (i.e., is an ancestor)."""
        result = self.run(['merge-base', '--is-ancestor', commit, list_head], may_fail=True)
        return result.returncode == 0

    def check(self) -> None:
        """Check that environment is suitable."""
        if not shutil.which('git'):
            raise GitNestedError("git is not on PATH")
        version = self.get_version()

        def version_tuple(v: str) -> tuple[int, ...]:
            return tuple(map(int, (v.split("."))))

        if version_tuple(version) < version_tuple(REQUIRED_GIT_VERSION):
            raise GitNestedError(f"git {REQUIRED_GIT_VERSION} or newer is required, but this is {version}")

    def get_version(self) -> str:
        """Return the installed git version string (e.g. '2.43.0')."""
        git_version = self.check_output(['--version'])
        # Bounded digit groups (rather than unbounded `\d+`) keep this linear: an
        # unbounded run of digits with no dot would otherwise make re.search()
        # backtrack quadratically while probing every start position.
        m = re.search(r'(\d{1,6}\.\d{1,6}\.\d{1,6})', git_version)
        if not m:
            raise GitNestedError("can't parse the version git reports")
        return m.group(1)
