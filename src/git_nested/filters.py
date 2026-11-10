"""Applying a nested repo's `filter` to its content.

Two drivers that deliberately stay separate because they write to
different sinks -- the index side builds a tree with `git update-index`,
the placement side writes files into the worktree. They agree on what a
filter entry means through `_classify`.
"""

from __future__ import annotations

import os
import posixpath
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from . import output
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags


def _classify(
    git: GitRunner, commit: str, entries: list[str], cwd: Path | None = None
) -> tuple[list[tuple[str, str]], list[re.Pattern]]:
    """Split filter entries into the paths `commit` has a tree or blob at, and regex patterns for the rest.

    Returns:
        tuple: ([(path, 'tree' or 'blob')], patterns)
    """
    literal: list[tuple[str, str]] = []
    patterns: list[re.Pattern] = []
    for entry in entries:
        obj_type = git.check_output(['cat-file', '-t', f'{commit}:{entry}'], may_fail=True, cwd=cwd)
        if obj_type in ('tree', 'blob'):
            literal.append((entry, obj_type))
            continue
        try:
            patterns.append(re.compile(entry))
        except re.error as e:
            raise GitNestedError(f"invalid filter pattern {entry}: {e}") from e
    return literal, patterns


def _included(git: GitRunner, commit: str, entries: list[str], cwd: Path | None) -> Callable[[str], bool]:
    """Whether a path of `commit` matches the filter; every path does without one."""
    if not entries:
        return lambda _path: True
    literal, patterns = _classify(git, commit, entries, cwd)
    exact = {path for path, _ in literal}
    prefixes = tuple(f'{path}/' for path, obj_type in literal if obj_type == 'tree')
    return lambda path: path in exact or path.startswith(prefixes) or _matches(patterns, path)


def split(
    git: GitRunner, commit: str, entries: list[str], exclude: list[str], cwd: Path | None = None
) -> tuple[list[str], list[str]]:
    """The files of `commit`: those git-nested manages, and the rest.

    It manages what the filter selects (all, without one), minus what
    `exclude` leaves out.

    Returns:
        tuple: (managed, rest), each as 'mode type sha<TAB>path' lines, as ls-tree gives them
    """
    included = _included(git, commit, entries, cwd)
    excluded = tuple(path.rstrip('/') for path in exclude)
    managed: list[str] = []
    rest: list[str] = []
    for line in filter(None, git.check_output(['ls-tree', '-r', '-z', commit], may_fail=True, cwd=cwd).split('\0')):
        path = line.split('\t', 1)[1]
        out = path in excluded or path.startswith(tuple(f'{e}/' for e in excluded))
        (managed if included(path) and not out else rest).append(line)
    return managed, rest


def build_filtered_commit(git: GitRunner, cwd: Path, entries: list[str], exclude: list[str], commit: str) -> str:
    """Build a throwaway commit whose tree only holds the files git-nested manages.

    The new commit keeps `commit` as its sole parent so its ancestry (and
    thus merge-base detection against the local nested branch) is unaffected.

    Returns:
        sha of the filtered commit
    """
    managed, _ = split(git, commit, entries, exclude, cwd)
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        git.run(['read-tree', '--empty'], cwd=cwd, env=env)
        git.run(
            ['update-index', '-z', '--index-info'], cwd=cwd, env=env, input=''.join(f'{line}\0' for line in managed)
        )
        filtered_tree = git.check_output(['write-tree'], cwd=cwd, env=env)
        return git.check_output(
            ['commit-tree', '-p', commit, '-m', 'git-nested: filtered view for merge', filtered_tree], cwd=cwd
        )


def _matches(patterns: list[re.Pattern], path: str) -> bool:
    """Whether `path` matches one of the regex filter patterns in full."""
    return any(pattern.fullmatch(path) for pattern in patterns)


def place_filtered_content(
    git: GitRunner, subdir: Path, entries: list[str], exclude: list[str], nested_commit_ref: str
) -> None:
    """Place the files git-nested manages into subdir/, through the index.

    Going through the index rather than writing the files keeps what a
    plain write loses: the executable bit, symlinks and non-UTF-8 content.
    """
    managed, _ = split(git, nested_commit_ref, entries, exclude)
    if not managed:
        return
    meta_and_paths = [line.split('\t', 1) for line in managed]
    targets = [f'{subdir.as_posix()}/{path}' for _, path in meta_and_paths]
    info = ''.join(f'{meta}\t{target}\0' for (meta, _), target in zip(meta_and_paths, targets, strict=True))
    git.run(['update-index', '-z', '--index-info'], input=info)
    git.run(['checkout-index', '-f', '-z', '--stdin'], input=''.join(f'{target}\0' for target in targets))


def ignored_paths(flags: Flags, subdir: Path) -> list[str]:
    """The --ignore paths, relative to subdir.

    They are given like subdir. With --all, a path outside subdir belongs
    to another nested repository and is skipped.
    """
    top = posixpath.normpath(subdir.as_posix())
    paths = []
    for given in flags.ignore or []:
        path = posixpath.normpath(Path(given).as_posix())
        if path.startswith(f'{top}/'):
            paths.append(path.removeprefix(f'{top}/'))
        elif path == top:
            output.usage_error(f"--ignore {given}: that is all of {top}")
        elif not flags.all:
            output.usage_error(f"--ignore {given}: not inside {top}")
    return paths


def with_paths_from(git: GitRunner, cwd: Path, commit: str, source: str, paths: list[str]) -> str:
    """A commit on top of `commit`, with `paths` as `source` has them.

    A path `source` does not have is left out.

    Returns:
        sha of the new commit
    """
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        git.run(['read-tree', commit], cwd=cwd, env=env)
        replace_paths(git, source, paths, env, cwd)
        tree = git.check_output(['write-tree'], cwd=cwd, env=env)
        return git.check_output(['commit-tree', '-p', commit, '-m', 'git-nested: ignored paths kept', tree], cwd=cwd)


def replace_paths(git: GitRunner, source: str, paths: list[str], env: dict[str, str], cwd: Path | None = None) -> None:
    """Make `paths` in the index of `env` what they are in `source`."""
    # -f: this index has nothing to do with the working tree
    git.run(['rm', '--cached', '-r', '-q', '-f', '--ignore-unmatch', '--', *paths], cwd=cwd, env=env)
    entries = git.check_output(['ls-tree', '-r', '-z', '--full-tree', source, '--', *paths], cwd=cwd)
    git.run(
        ['update-index', '-z', '--index-info'],
        cwd=cwd,
        env=env,
        input=''.join(f'{e}\0' for e in entries.split('\0') if e),
    )
