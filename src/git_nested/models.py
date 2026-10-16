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

    adopt: bool = False
    all: bool = False
    all_deep: bool = False
    branch: str | None = None
    commit: bool = False
    dir: str | None = None
    exclude: list[str] | None = None
    filter: list[str] | None = None
    force: bool = False
    from_submodule: bool = False
    recurse_submodules: bool = False
    gpg_sign: bool = False
    signoff: bool = False
    fetch: bool = False
    message: str | None = None
    message_file: str | None = None
    name: str | None = None
    path: str | None = None
    method: str | None = None
    remote: str | None = None
    short: bool = False
    squash: bool = False
    upstream_commit: str | None = None
    update: bool = False
    quiet: bool = False
    verbose: int = 0


@dataclass
class NestedConfig:
    """Nested configuration from .gitnested file."""

    remote: str = ''
    branch: str = ''
    commit: str = ''
    filter: list[str] | None = None
    exclude: list[str] | None = None
    path: str = ''
    parent: str = ''
    method: str = 'merge'
    readonly: bool = False

    @classmethod
    def from_file(cls, filepath: str | Path) -> NestedConfig:
        """Read config from .gitnested YAML file."""
        path = Path(filepath)
        if not path.is_file():
            raise GitNestedError(f"{path.as_posix()} does not exist")
        nested = (yaml.safe_load(path.read_text(encoding='utf-8')) or {}).get('nested', {})
        config = cls(
            remote=nested.get('remote', ''),
            branch=nested.get('branch', ''),
            commit=nested.get('commit', ''),
            filter=nested.get('filter'),
            exclude=nested.get('exclude'),
            path=nested.get('path') or '',
            parent=nested.get('parent', ''),
            method='rebase' if nested.get('method') == 'rebase' else 'merge',
            readonly=str(nested.get('readonly')).lower() == 'true',
        )
        if not config.remote:
            raise GitNestedError(f"{path.as_posix()} has no 'remote'")
        if not config.branch:
            raise GitNestedError(f"{path.as_posix()} has no 'branch'")
        return config


@dataclass
class CommandContext:
    """Everything a `cmd_*` handler is given, in one object.

    The handlers all take this instead of their own parameter list so that
    dispatch is a table lookup rather than a per-command lambda. Which
    fields are meaningful depends on the command: `nested_commit_ref` is
    only populated by the commands that take it as a positional,
    `upstream` only by `clone`, `completion_shell` only by `completion` and
    the `config_*` pair only by `config`.
    """

    git: GitRunner
    flags: Flags
    subdir: str | Path | None = None
    upstream: str | None = None
    nested_commit_ref: str | None = None
    # Spelled out rather than `shell`, which reads as subprocess's shell=
    # in a package whose every other module shells out to git.
    completion_shell: str | None = None
    config_key: str | None = None
    config_value: str | None = None
    git_args: list[str] | None = None
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
