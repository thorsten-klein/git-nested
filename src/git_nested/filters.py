"""Applying a nested repo's `filter` to its content.

Two drivers that deliberately stay separate because they write to
different sinks -- the index side builds a tree with `git update-index`,
the placement side writes files into the worktree.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from .errors import GitNestedError
from .git import GitRunner
from .models import NestedConfig


def build_filtered_commit(git: GitRunner, cwd: Path, config: NestedConfig, commit: str) -> str:
    """Build a throwaway commit whose tree only contains the filtered paths.

    Applies the exact same literal/regex rules used when the filtered
    content is written into the working tree.

    The new commit keeps `commit` as its sole parent so its ancestry (and
    thus merge-base detection against the local nested branch) is unaffected.

    Returns:
        sha of the filtered commit
    """
    with tempfile.TemporaryDirectory() as tmp:
        index_file = Path(tmp) / 'index'
        env = os.environ.copy()
        env['GIT_INDEX_FILE'] = str(index_file)

        git.run(['read-tree', '--empty'], cwd=cwd, env=env)

        def already_indexed(path: str) -> bool:
            return bool(git.check_output(['ls-files', '--stage', '--', path], cwd=cwd, env=env, may_fail=True))

        # Callers only reach this method when config.filter is truthy (see
        # do_pull/commit_nested_branch's `if config.filter:` guards).
        if config.filter is None:
            raise AssertionError(
                'config.filter must be set when build_filtered_commit is called'
            )  # pragma: no cover -- invariant guard, unreachable via the public API
        regex_patterns: list[re.Pattern] = []
        for p in config.filter:
            _index_literal_filter_entry(git, cwd, env, commit, p, regex_patterns)

        if regex_patterns:
            _index_regex_matches(git, cwd, env, commit, regex_patterns, already_indexed)

        filtered_tree = git.check_output(['write-tree'], cwd=cwd, env=env)
        return git.check_output(
            ['commit-tree', '-p', commit, '-m', 'git-nested: filtered view for merge', filtered_tree], cwd=cwd
        )


def _index_literal_filter_entry(
    git: GitRunner, cwd: Path, env: dict, commit: str, p: str, regex_patterns: list[re.Pattern]
) -> None:
    """Index one filter entry: a tree or a blob, else collect it as a regex pattern."""
    obj_type = git.check_output(['cat-file', '-t', f'{commit}:{p}'], may_fail=True, cwd=cwd)
    if obj_type == 'tree':
        git.run(['read-tree', f'--prefix={p}', f'{commit}:{p}'], cwd=cwd, env=env)
    elif obj_type == 'blob':
        mode = git.check_output(['ls-tree', commit, '--', p]).split()[0]
        blob_sha = git.check_output(['rev-parse', f'{commit}:{p}'], cwd=cwd)
        git.run(['update-index', '--add', '--cacheinfo', f'{mode},{blob_sha},{p}'], cwd=cwd, env=env)
    else:
        try:
            regex_patterns.append(re.compile(p))
        except re.error as e:
            raise GitNestedError(f"invalid filter pattern {p}: {e}") from e


def _index_regex_matches(
    git: GitRunner,
    cwd: Path,
    env: dict,
    commit: str,
    regex_patterns: list[re.Pattern],
    already_indexed: Callable[[str], bool],
) -> None:
    """Index every blob in `commit` whose path matches a regex filter pattern and isn't indexed yet."""
    tree_listing = git.check_output(['ls-tree', '-r', commit], may_fail=True, cwd=cwd) or ''
    for line in tree_listing.splitlines():
        meta, blob_path = line.split('\t', 1)
        if not _blob_needs_regex_index(blob_path, regex_patterns, already_indexed):
            continue
        mode, _obj_type, blob_sha = meta.split()
        git.run(['update-index', '--add', '--cacheinfo', f'{mode},{blob_sha},{blob_path}'], cwd=cwd, env=env)


def _blob_needs_regex_index(
    blob_path: str, regex_patterns: list[re.Pattern], already_indexed: Callable[[str], bool]
) -> bool:
    """Check whether blob_path matches a regex filter pattern and isn't already indexed."""
    if not any(pattern.fullmatch(blob_path) for pattern in regex_patterns):
        return False
    return not already_indexed(blob_path)


def _place_literal_filter_entry(
    git: GitRunner, subdir: Path, nested_commit_ref: str, p: str, regex_patterns: list[re.Pattern]
) -> None:
    """Place one filter entry (a tree or a blob) into subdir/, else collect it as a regex pattern."""
    obj_type = git.check_output(['cat-file', '-t', f'{nested_commit_ref}:{p}'], may_fail=True)
    if obj_type == 'tree':
        git.run(['read-tree', f'--prefix={subdir}/{p}', '-u', f'{nested_commit_ref}:{p}'])
    elif obj_type == 'blob':
        file_path = subdir / p
        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = git.run(['cat-file', 'blob', f'{nested_commit_ref}:{p}']).stdout
        file_path.write_text(content)
        git.run(['add', '-f', '--', str(file_path)])
    else:
        try:
            regex_patterns.append(re.compile(p))
        except re.error as e:
            raise GitNestedError(f"invalid filter pattern {p}: {e}") from e


def _blob_needs_placement(blob_path: str, subdir: Path, regex_patterns: list[re.Pattern]) -> bool:
    """Check whether blob_path matches a regex filter pattern and hasn't been placed yet."""
    if not any(pattern.fullmatch(blob_path) for pattern in regex_patterns):
        return False
    return not (subdir / blob_path).exists()


def _place_regex_matches(
    git: GitRunner, subdir: Path, nested_commit_ref: str, regex_patterns: list[re.Pattern]
) -> None:
    """Place every blob matching a regex filter pattern that hasn't already been placed."""
    all_blobs = (
        git.check_output(['ls-tree', '-r', '--name-only', nested_commit_ref], may_fail=True) or ''
    ).splitlines()
    for blob_path in all_blobs:
        if not _blob_needs_placement(blob_path, subdir, regex_patterns):
            continue
        file_path = subdir / blob_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = git.run(['cat-file', 'blob', f'{nested_commit_ref}:{blob_path}']).stdout
        file_path.write_text(content)
        git.run(['add', '-f', '--', str(file_path)])


def _place_filtered_content(git: GitRunner, subdir: Path, config: NestedConfig, nested_commit_ref: str) -> None:
    """Place only the filtered upstream paths into subdir/ (literal paths + regex patterns)."""
    # Callers only reach this method when config.filter is truthy (see
    # commit_nested_branch's `if not config.filter: ... else:` guard).
    if config.filter is None:
        raise AssertionError(
            'config.filter must be set when _place_filtered_content is called'
        )  # pragma: no cover -- invariant guard, unreachable via the public API
    regex_patterns: list[re.Pattern] = []
    for p in config.filter:
        _place_literal_filter_entry(git, subdir, nested_commit_ref, p, regex_patterns)

    if regex_patterns:
        _place_regex_matches(git, subdir, nested_commit_ref, regex_patterns)
