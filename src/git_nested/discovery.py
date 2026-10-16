"""Finding nested repositories and asking git about the repo."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from ._version import VERSION
from .constants import GITNESTED_FILENAME
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags, NestedConfig


def find_all_nested_repositories(git: GitRunner, flags: Flags) -> list[Path]:
    """Find all nested repositories in repository; only the outermost ones unless --ALL."""
    tracked_files = git.check_output(['ls-files'])
    paths = sorted(Path(line).parent for line in tracked_files.splitlines() if line.endswith(GITNESTED_FILENAME))
    if flags.all_deep:
        return paths
    return [p for p in paths if not any(p.is_relative_to(other) for other in paths if p != other)]


def get_upstream_branch(git: GitRunner, config: NestedConfig) -> str:
    """Determine upstream default branch."""
    remote_branches = git.check_output(['ls-remote', '--symref', config.remote], may_fail=True)
    if not remote_branches:
        raise GitNestedError(f"can't reach {config.remote}: git ls-remote failed")
    upstream_branch = re.search(r"^ref:\s+refs/heads/(\S+)\s+HEAD", remote_branches, re.MULTILINE)
    if not upstream_branch:
        raise GitNestedError(f"can't determine the default branch of {config.remote}")
    return upstream_branch.group(1)


def build_commit_message(
    git: GitRunner,
    config: NestedConfig,
    upstream_head_commit: str,
    nested_commit_ref: str,
    subdir: Path,
    command: str,
) -> str:
    """Generate commit message."""
    upstream_commit = 'none'
    if upstream_head_commit:
        upstream_commit = git.check_output(['rev-parse', '--short', upstream_head_commit])
    commit = git.check_output(['rev-parse', '--short', nested_commit_ref])
    return textwrap.dedent(
        f"""\
        git nested {command}

        nested:
          subdir:   "{subdir.as_posix()}"
          merged:   "{commit}"
        upstream:
          remote:   "{config.remote}"
          branch:   "{config.branch}"
          commit:   "{upstream_commit}"
        git-nested:
          version:  "{VERSION}"
        """
    )
