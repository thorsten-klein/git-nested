"""The data git-nested passes around: parsed flags and .gitnested config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from . import configio
from .constants import PATCHES_FOLDER
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
    dry_run: bool = False
    dir: str | None = None
    exclude: list[str] | None = None
    filter: list[str] | None = None
    force: bool = False
    ignore: list[str] | None = None
    from_submodule: bool = False
    recurse_submodules: bool = False
    gpg_sign: bool = False
    signoff: bool = False
    single_commit: bool = False
    fetch: bool = False
    message: str | None = None
    message_file: str | None = None
    name: str | None = None
    path: str | None = None

    pin: str | None = None
    method: str | None = None
    remote: str | None = None
    short: bool = False
    squash: bool = False
    upstream_commit: str | None = None

    no_squash: bool = False
    keep: bool = False
    output_dir: str | None = None
    tag: str | None = None
    update: bool = False
    quiet: bool = False
    verbose: int = 0


def _paths(value: object) -> tuple[str, ...]:
    """A path or a list of paths from .gitnested."""
    if not value:
        return ()
    return tuple(str(path) for path in value) if isinstance(value, list) else (str(value),)


def _patches(value: object) -> str:
    """The patches folder from .gitnested: on by default, '' if set to false."""
    text = '' if value is None else str(value)
    if text.lower() == 'false':
        return ''
    return PATCHES_FOLDER if text.lower() in ('', 'true') else text


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
    pin: str = ''
    method: str = 'merge'
    squash: bool = True
    readonly: bool = False
    patches: str = PATCHES_FOLDER
    # Paths in subdir, relative to it, that stay local: no patch needs them.
    patches_ignore: tuple[str, ...] = ()

    @classmethod
    def from_file(cls, filepath: str | Path) -> NestedConfig:
        """Read config from a .gitnested file."""
        path = Path(filepath)
        if not path.is_file():
            raise GitNestedError(f"{path.as_posix()} does not exist")
        nested = configio.read(path).get('nested', {})
        config = cls(
            remote=nested.get('remote', ''),
            branch=nested.get('branch', ''),
            commit=nested.get('commit', ''),
            filter=nested.get('filter'),
            exclude=nested.get('exclude'),
            path=nested.get('path') or '',
            parent=nested.get('parent', ''),
            pin=nested.get('pin') or '',
            method='rebase' if nested.get('method') == 'rebase' else 'merge',
            squash=str(nested.get('squash', 'true')).lower() != 'false',
            readonly=str(nested.get('readonly')).lower() == 'true',
            patches=_patches(nested.get('patches')),
            patches_ignore=_paths(nested.get('patches-ignore')),
        )
        if not config.remote:
            raise GitNestedError(f"{path.as_posix()} has no 'remote'")
        if not config.branch:
            raise GitNestedError(f"{path.as_posix()} has no 'branch'")
        return config

    def patches_folder(self, subdir: Path) -> Path | None:
        """The folder with the patches, or None if they are off."""
        return subdir / self.patches if self.patches else None

    def patches_inside(self, subdir: Path) -> str | None:
        """The patches folder relative to subdir, if it is inside it.

        Such a folder is not part of the upstream content.
        """
        folder = self.patches_folder(subdir)
        if folder is None:
            return None
        try:
            return folder.resolve().relative_to(subdir.resolve()).as_posix()
        except ValueError:
            return None


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
    patches: list[str] | None = None
    verify_mode: str | None = None
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
