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


def _outermost_paths(paths: list[Path]) -> list[Path]:
    """Keep only the paths that are not nested inside another path in the list."""
    return [p for p in paths if not any(p.is_relative_to(other) for other in paths if p != other)]


def find_all_nested_repositories(git: GitRunner, flags: Flags) -> list[Path]:
    """Find all nested repositories in repository."""
    tracked_files = git.check_output(['ls-files'])
    gitnesteds = sorted(Path(line).parent for line in tracked_files.splitlines() if line.endswith(GITNESTED_FILENAME))
    if not flags.all_deep:
        # Filter the paths to contain only outermost nested repository paths
        gitnesteds = _outermost_paths(gitnesteds)
    return gitnesteds


def get_upstream_branch(git: GitRunner, config: NestedConfig) -> str:
    """Determine upstream default branch."""
    remote_branches = git.check_output(['ls-remote', '--symref', config.remote], may_fail=True)
    if not remote_branches:
        raise GitNestedError(f"Command failed: 'git ls-remote --symref {config.remote}'.")
    upstream_branch = re.search(r"^ref:\s+refs/heads/(\S+)\s+HEAD", remote_branches, re.MULTILINE)
    if not upstream_branch:
        raise GitNestedError("Problem finding remote default head branch.")
    return upstream_branch.group(1)


def get_default_branch(git: GitRunner) -> str:
    """Get git's default branch name."""
    default_branch = git.check_output(['config', '--get', 'init.defaultbranch'], may_fail=True)
    if default_branch:
        return default_branch
    return "main"


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
          subdir:   "{subdir}"
          merged:   "{commit}"
        upstream:
          remote:   "{config.remote}"
          branch:   "{config.branch}"
          commit:   "{upstream_commit}"
        git-nested:
          version:  "{VERSION}"
        """
    )
