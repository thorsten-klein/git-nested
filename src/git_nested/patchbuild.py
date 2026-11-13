"""Patches built and checked in a temporary worktree.

The worktree is at the upstream commit. The patches go on top with
`git am`. Then the result is compared with what
HEAD has in the subdir, and the patches can be written again from it.
"""

from __future__ import annotations

import contextlib
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

from . import output, patches, worktree
from .errors import GitNestedError
from .git import GitRunner

# Placeholders in a new patch, for the user to fill in.
TODO_TITLE = "TODO: title"
TODO_DESCRIPTION = "TODO: description"

_LEADING_NUMBER = re.compile(r'^(\d+)-')


def shown(path: Path) -> str:
    """`path`, relative to the current directory if inside it."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


@contextlib.contextmanager
def worktree_at(git: GitRunner, path: Path, base: str, keep: bool = False) -> Iterator[None]:
    """A temporary worktree at `base`, removed afterwards unless `keep`."""
    worktree.remove_worktree(git, path)
    # --no-checkout and reset: skip the parent's post-checkout hook
    git.run(['worktree', 'add', '--quiet', '--detach', '--no-checkout', path, base])
    try:
        git.run(['reset', '-q', '--hard'], cwd=path)
        yield
    finally:
        if keep:
            output.say(f"kept the worktree at {path.as_posix()}")
        else:
            worktree.remove_worktree(git, path)


def commit_in(git: GitRunner, path: Path, *message: str) -> None:
    """Commit in the worktree at `path`, without hooks or signing."""
    paragraphs = [arg for paragraph in message for arg in ('-m', paragraph)]
    git.run(
        [*patches.identity(git), 'commit', '--quiet', '--allow-empty', '--no-verify', '--no-gpg-sign', *paragraphs],
        cwd=path,
    )


def apply(git: GitRunner, path: Path, files: list[Path]) -> None:
    """`git am` the patches in the worktree at `path`, one commit each.

    Raises:
        GitNestedError: a file is not a patch, or does not apply.
    """
    if not files:
        return
    with tempfile.TemporaryDirectory() as scratch:
        failed = patches.apply_in_worktree(git, path, files, Path(scratch))
    if not failed:
        return
    name = shown(next(file for file in files if file.name == failed))
    if patches.am_open(git, path):
        raise GitNestedError(f"{name}: does not apply")
    raise GitNestedError(f"{name}: is not a patch. A patch has a header, as `git format-patch` writes it")


def diff(git: GitRunner, path: Path, base: str, local_tree: str, pathspec: list[str], *options: str) -> str:
    """The diff from `base` to `local_tree`, for `pathspec`."""
    return git.run(['diff', *options, base, local_tree, '--', *pathspec], cwd=path).stdout


def differs(git: GitRunner, path: Path, local_tree: str, pathspec: list[str]) -> bool:
    """Whether the worktree at `path` differs from `local_tree`."""
    return git.run(['diff', '--quiet', 'HEAD', local_tree, '--', *pathspec], cwd=path, may_fail=True).returncode != 0


def commit_missing(git: GitRunner, path: Path, local_tree: str, pathspec: list[str]) -> None:
    """Commit what `local_tree` has on top of the worktree at `path`, with a TODO message."""
    # A file, not a pipe: text mode would drop the CRs.
    missing = path.parent / f'{path.name}.diff'
    diff(git, path, 'HEAD', local_tree, pathspec, '--binary', '--full-index', f'--output={missing.resolve()}')
    git.run(['apply', '--index', missing.resolve()], cwd=path)
    missing.unlink()
    commit_in(git, path, TODO_TITLE, TODO_DESCRIPTION)


def next_number(directory: Path) -> int:
    """The next free patch number in `directory`."""
    numbers = [
        int(match.group(1))
        for patch in directory.glob(patches.PATCH_GLOB)
        if (match := _LEADING_NUMBER.match(patch.name))
    ]
    return max(numbers, default=0) + 1


def write_last(git: GitRunner, path: Path, directory: Path) -> Path:
    """Write the last commit of the worktree at `path` as a patch into `directory`, numbered after the others."""
    directory.mkdir(parents=True, exist_ok=True)
    number = next_number(directory)
    return Path(
        git.check_output(
            [*patches.FORMAT_PATCH, '-1', f'--start-number={number}', '-o', directory.resolve(), 'HEAD'], cwd=path
        )
    )


def write_all(git: GitRunner, path: Path, base: str, directory: Path) -> list[Path]:
    """Write the commits of the worktree at `path` since `base` as patches into `directory`."""
    git.run([*patches.FORMAT_PATCH, '--quiet', '-o', directory.resolve(), f'{base}..HEAD'], cwd=path)
    return sorted(directory.glob(patches.PATCH_GLOB))


def stored(git: GitRunner, file: Path) -> bytes:
    """The bytes git stores for the patch `file`: a CRLF checkout counts as LF."""
    with patches.as_written(git, file) as plain:
        return plain.read_bytes()
