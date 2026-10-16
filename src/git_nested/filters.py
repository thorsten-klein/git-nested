"""Applying a nested repo's `filter` to its content.

Two drivers that deliberately stay separate because they write to
different sinks -- the index side builds a tree with `git update-index`,
the placement side writes files into the worktree. They agree on what a
filter entry means through `_classify`.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .errors import GitNestedError
from .git import GitRunner


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


def build_filtered_commit(git: GitRunner, cwd: Path, entries: list[str], commit: str) -> str:
    """Build a throwaway commit whose tree only contains the filtered paths.

    The new commit keeps `commit` as its sole parent so its ancestry (and
    thus merge-base detection against the local nested branch) is unaffected.

    Returns:
        sha of the filtered commit
    """
    literal, patterns = _classify(git, commit, entries, cwd)
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        git.run(['read-tree', '--empty'], cwd=cwd, env=env)

        for path, obj_type in literal:
            if obj_type == 'tree':
                git.run(['read-tree', f'--prefix={path}', f'{commit}:{path}'], cwd=cwd, env=env)
                continue
            mode, _, blob_sha = git.check_output(['ls-tree', commit, '--', path]).split()[:3]
            git.run(['update-index', '--add', '--cacheinfo', f'{mode},{blob_sha},{path}'], cwd=cwd, env=env)

        listing = git.check_output(['ls-tree', '-r', '-z', commit], may_fail=True, cwd=cwd) if patterns else ''
        for line in filter(None, listing.split('\0')):
            meta, path = line.split('\t', 1)
            if _matches(patterns, path) and not git.check_output(
                ['ls-files', '--stage', '--', path], cwd=cwd, env=env, may_fail=True
            ):
                mode, _, blob_sha = meta.split()
                git.run(['update-index', '--add', '--cacheinfo', f'{mode},{blob_sha},{path}'], cwd=cwd, env=env)

        filtered_tree = git.check_output(['write-tree'], cwd=cwd, env=env)
        return git.check_output(
            ['commit-tree', '-p', commit, '-m', 'git-nested: filtered view for merge', filtered_tree], cwd=cwd
        )


def _matches(patterns: list[re.Pattern], path: str) -> bool:
    """Whether `path` matches one of the regex filter patterns in full."""
    return any(pattern.fullmatch(path) for pattern in patterns)


def _place_blob(git: GitRunner, subdir: Path, nested_commit_ref: str, blob_path: str) -> None:
    """Place one blob of nested_commit_ref into subdir/ through the index.

    Going through the index rather than writing the file keeps what a plain
    write loses: the executable bit, symlinks and non-UTF-8 content.
    """
    entry = git.check_output(['ls-tree', '-z', nested_commit_ref, '--', blob_path]).rstrip('\0')
    mode, _obj_type, blob_sha = entry.split('\t', 1)[0].split()
    target = (subdir / blob_path).as_posix()
    git.run(['update-index', '--add', '--cacheinfo', f'{mode},{blob_sha},{target}'])
    git.run(['checkout-index', '--force', '--', target])


def place_filtered_content(git: GitRunner, subdir: Path, entries: list[str], nested_commit_ref: str) -> None:
    """Place only the filtered upstream paths into subdir/ (literal paths + regex patterns)."""
    literal, patterns = _classify(git, nested_commit_ref, entries)
    for path, obj_type in literal:
        if obj_type == 'tree':
            git.run(['read-tree', f'--prefix={subdir.as_posix()}/{path}', '-u', f'{nested_commit_ref}:{path}'])
            continue
        _place_blob(git, subdir, nested_commit_ref, path)

    listing = (
        git.check_output(['ls-tree', '-r', '-z', '--name-only', nested_commit_ref], may_fail=True) if patterns else ''
    )
    for path in filter(None, listing.split('\0')):
        if _matches(patterns, path) and not (subdir / path).exists():
            _place_blob(git, subdir, nested_commit_ref, path)
