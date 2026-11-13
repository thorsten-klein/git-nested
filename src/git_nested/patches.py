"""Local changes of a nested repo, kept as patch files.

The `patches` field of .gitnested names the folder, relative to the subdir.
The patches are the local changes on top of the upstream commit.
Nested repos inside the subdir are not part of them. They can have their
own patches.
"""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from . import history, output
from .errors import GitNestedError
from .git import GitRunner
from .models import NestedConfig

# `git commit` and `git am` need an identity; CI often has none.
_FALLBACK_IDENTITY = ['-c', 'user.name=git-nested', '-c', 'user.email=git-nested@localhost']

# The patch files in the patches folder.
PATCH_GLOB = '*.patch'

# How every patch is written, so that a patch written again is the same.
FORMAT_PATCH = ['format-patch', '--zero-commit', '--no-signature', '--no-numbered', '--no-cover-letter']

# .gitnested files are not part of the upstream content.
GITNESTED_EXCLUDE = ':(exclude,glob)**/.gitnested*'


def identity(git: GitRunner) -> list[str]:
    """A stand-in identity if git has none."""
    return [] if git.check_output(['config', 'user.email'], may_fail=True) else _FALLBACK_IDENTITY


def files(config: NestedConfig, subdir: Path) -> list[Path]:
    """The patch files, in order."""
    folder = config.patches_folder(subdir)
    return sorted(folder.glob(PATCH_GLOB)) if folder and folder.is_dir() else []


def local_paths(git: GitRunner, config: NestedConfig, subdir: Path) -> list[str]:
    """The paths in subdir the patches leave out.

    The patches folder and the inner nested repos.
    """
    inside = config.patches_inside(subdir)
    return [*([inside] if inside else []), *history.inner_repos(git, config, subdir)]


def pathspec(local: list[str], ignored: list[str] | None = None) -> list[str]:
    """All paths but .gitnested files, the `local` and the `ignored` ones."""
    return ['.', GITNESTED_EXCLUDE, *(f':(exclude,literal){path}' for path in [*local, *(ignored or [])])]


def supported(config: NestedConfig) -> bool:
    """Whether the patches work with this setup yet."""
    return config.squash and not (config.path or config.filter or config.exclude)


def check(config: NestedConfig, subdir: Path, patches: list[Path]) -> None:
    """Refuse a patches setup that can't be, and `patches` with a setup they do not work with yet."""
    if not config.patches:
        return
    problem = _folder_problem(config, subdir)
    if not problem and patches and (config.path or config.filter or config.exclude):
        problem = "patches do not work with filter, exclude or path yet"
    if problem:
        raise GitNestedError(f"{subdir.as_posix()}: {problem}")


def _folder_problem(config: NestedConfig, subdir: Path) -> str | None:
    """What is wrong with the patches folder, if anything."""
    if PurePosixPath(config.patches).is_absolute() or Path(config.patches).is_absolute():
        return "patches must be a path relative to the subdir"
    if config.patches_inside(subdir) == '.':
        return "patches can't be the subdir itself"
    return None


@contextlib.contextmanager
def as_written(git: GitRunner, patch: Path) -> Iterator[Path]:
    """`patch` with the bytes git stores for it, as an absolute path.

    A checkout with core.autocrlf or an eol attribute turns the LF line
    ends of a patch file into CRLF. git's clean filter undoes that; then
    this is a temporary copy with LF again. Else the file is taken as it
    is, and a CR in it is content.
    """
    patch = patch.resolve()
    raw = git.check_output(['hash-object', '--no-filters', patch])
    if git.check_output(['hash-object', patch]) == raw:
        yield patch
        return
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / patch.name
        copy.write_bytes(patch.read_bytes().replace(b'\r\n', b'\n'))
        yield copy


def _am(git: GitRunner, path: Path, patches: list[Path], no_hooks: Path) -> str | None:
    """`git am -3` the patches in the worktree at `path`, without hooks or signing.

    One `git am` for all patches: after a conflict, `git am --continue`
    goes on with the rest.

    --keep-cr: a CR in a patch is content.

    A patch that upstream already has is dropped.

    Returns:
        None, or the name of the patch that does not apply.
    """
    no_hooks.mkdir(parents=True, exist_ok=True)
    output.verbose(f"applying {', '.join(patch.as_posix() for patch in patches)}")
    hooks = ['-c', f'core.hooksPath={no_hooks.as_posix()}']
    am = ['am', '-3', '--quiet', '--no-gpg-sign', '--keep-cr']
    with contextlib.ExitStack() as stack:
        # git am copies the patches before it starts, so the copies can go after it.
        written = [stack.enter_context(as_written(git, patch)) for patch in patches]
        if git.run([*identity(git), *hooks, *am, *written], cwd=path, may_fail=True).returncode == 0:
            return None
    return patches[_stopped_at(git, path) - 1].name


def _stopped_at(git: GitRunner, path: Path) -> int:
    """The number of the patch the open `git am` in `path` stopped at, from 1.

    No open `git am`: the first patch failed the format detection.
    """
    state = _am_next(git, path)
    return int(state.read_text()) if state.is_file() else 1


def am_open(git: GitRunner, path: Path) -> bool:
    """Whether a `git am` is open in the worktree at `path`.

    After a failed `git am`: if not, the patch is not a patch at all.
    """
    return _am_next(git, path).is_file()


def _am_next(git: GitRunner, path: Path) -> Path:
    """The file where an open `git am` in `path` keeps the number of its next patch."""
    return path / git.check_output(['rev-parse', '--git-path', 'rebase-apply/next'], cwd=path)


def apply_in_worktree(git: GitRunner, path: Path, patches: list[Path], git_tmp: Path) -> str | None:
    """Apply the patches in the worktree at `path`, one commit each.

    On a conflict the `git am` stays open in the worktree.

    Returns:
        None, or the name of the patch that does not apply.
    """
    return _am(git, path, patches, git_tmp / 'no-hooks')
