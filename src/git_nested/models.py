"""The data git-nested passes around: parsed flags and .gitnested config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml

from .errors import GitNestedError

if TYPE_CHECKING:
    from .git import GitRunner


@dataclass
class Flags:
    """Command-line flags."""

    all: bool = False
    all_deep: bool = False
    branch: None | str = None
    commit: bool = False
    filter: None | list[str] = None
    force: bool = False
    fetch: bool = False
    message: None | str = None
    message_file: None | str = None
    method: None | str = None
    remote: None | str = None
    squash: bool = False
    update: bool = False
    quiet: bool = False
    verbose: int = 0


@dataclass
class NestedConfig:
    """Nested configuration from .gitnested file."""

    remote: str = ''
    branch: str = ''
    commit: str = ''
    filter: None | list[str] = None
    parent: str = ''
    method: str = 'merge'

    @classmethod
    def from_file(cls, filepath: str | Path):
        """Read config from .gitnested YAML file."""
        path = Path(filepath)
        if not path.is_file():
            raise GitNestedError(f"No '{filepath}' file.")
        with path.open('r') as f:
            data = yaml.safe_load(f) or {}
        nested_data = data.get('nested', {})

        config = cls()
        config.remote = nested_data.get('remote', '')
        config.branch = nested_data.get('branch', '')
        config.commit = nested_data.get('commit', '')
        config.filter = nested_data.get('filter', None)
        config.parent = nested_data.get('parent', '')
        method = nested_data.get('method', 'merge')
        config.method = 'rebase' if method == 'rebase' else 'merge'

        if not config.remote:
            raise GitNestedError(f"Missing required 'remote' in '{filepath}'.")
        if not config.branch:
            raise GitNestedError(f"Missing required 'branch' in '{filepath}'.")

        return config


@dataclass
class CommandContext:
    """Everything a `cmd_*` handler is given, in one object.

    The handlers all take this instead of their own parameter list so that
    dispatch is a table lookup rather than a per-command lambda. Which
    fields are meaningful depends on the command: `nested_commit_ref` is
    only populated by the commands that take it as a positional,
    `upstream` only by `clone` and `completion_shell` only by `completion`.
    """

    git: GitRunner
    flags: Flags
    subdir: str | Path | None = None
    upstream: str | None = None
    nested_commit_ref: str | None = None
    # Spelled out rather than `shell`, which reads as subprocess's shell=
    # in a package whose every other module shells out to git.
    completion_shell: str | None = None
    git_tmp: Path | None = None
    head_commit: str | None = None

    # `version` is the one command that runs without a repository, so it is
    # the only reason these two are optional at all -- and it reads neither.
    # Every other handler goes through these, which say so once instead of
    # each caller re-proving it.

    @property
    def tmp(self) -> Path:
        """`git_tmp`, for a handler that only runs inside a repository."""
        return cast('Path', self.git_tmp)

    @property
    def head(self) -> str:
        """`head_commit`, for a handler that only runs inside a repository."""
        return cast('str', self.head_commit)
