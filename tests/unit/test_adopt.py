"""Unit tests for adopting existing directories."""

from pathlib import Path

import pytest
from fakes import NO_GIT, FakeGit

from git_nested import GitNestedError
from git_nested.commands.clone import _adopt_existing_subdir, _matching_upstream_commit
from git_nested.commands.init import _resolve_upstream_commit
from git_nested.models import Flags, NestedConfig


def test_matching_upstream_commit_returns_the_newest_exact_tree():
    """A vendored copy should anchor to the newest matching upstream commit."""
    git = (
        FakeGit()
        .respond('rev-parse', 'HEAD:vendor/bar', stdout='tree-local')
        .respond(
            'log',
            '--format=%H %T',
            'upstream-head',
            stdout='new tree-other\nmatch tree-local\nold tree-local\n',
        )
    )

    assert _matching_upstream_commit(git, Path('vendor/bar'), 'upstream-head') == 'match'


def test_matching_upstream_commit_errors_without_a_match():
    """The command should tell the user to fall back to init --commit."""
    git = (
        FakeGit()
        .respond('rev-parse', 'HEAD:vendor/bar', stdout='tree-local')
        .respond(
            'log',
            '--format=%H %T',
            'upstream-head',
            stdout='new tree-other\nold tree-else\n',
        )
    )

    with pytest.raises(GitNestedError, match=r'use .*init -r <url> --commit <sha> <subdir>'):
        _matching_upstream_commit(git, Path('vendor/bar'), 'upstream-head')


@pytest.mark.parametrize(
    ('flags', 'message'),
    [
        (Flags(adopt=True, filter=['src']), "--adopt can't be used with --filter"),
        (Flags(adopt=True, recurse_submodules=True), "--adopt can't be used with --recurse-submodules"),
    ],
)
def test_adopt_existing_subdir_rejects_incompatible_flags(tmp_path, flags, message):
    """Unsupported adopt modes fail before any git call happens."""
    vendored = tmp_path / 'vendor' / 'bar'
    vendored.mkdir(parents=True)
    (vendored / 'Bar').touch()
    config = NestedConfig(remote='r', branch='main')
    gitnested = vendored / '.gitnested'

    with pytest.raises(GitNestedError, match=message):
        _adopt_existing_subdir(NO_GIT, flags, config, vendored, gitnested, 'vendor/bar', 'head')


def test_adopt_existing_subdir_rejects_empty_directory(tmp_path):
    """There has to be content to adopt."""
    vendored = tmp_path / 'vendor' / 'bar'
    vendored.mkdir(parents=True)
    config = NestedConfig(remote='r', branch='main')
    gitnested = vendored / '.gitnested'

    with pytest.raises(GitNestedError, match='does not exist or is empty'):
        _adopt_existing_subdir(NO_GIT, Flags(adopt=True), config, vendored, gitnested, 'vendor/bar', 'head')


def test_adopt_existing_subdir_rejects_existing_gitnested(tmp_path):
    """A nested repository cannot be adopted again."""
    vendored = tmp_path / 'vendor' / 'bar'
    vendored.mkdir(parents=True)
    (vendored / 'Bar').touch()
    gitnested = vendored / '.gitnested'
    gitnested.write_text('nested:\n  remote: r\n  branch: main\n')
    config = NestedConfig(remote='r', branch='main')

    with pytest.raises(GitNestedError, match='is already a nested repository'):
        _adopt_existing_subdir(NO_GIT, Flags(adopt=True), config, vendored, gitnested, 'vendor/bar', 'head')


def test_adopt_existing_subdir_requires_tracked_content(tmp_path):
    """Only tracked content can keep its history."""
    vendored = tmp_path / 'vendor' / 'bar'
    vendored.mkdir(parents=True)
    (vendored / 'Bar').touch()
    git = FakeGit().respond('ls-files', '--', vendored, stdout='')
    config = NestedConfig(remote='r', branch='main')
    gitnested = vendored / '.gitnested'

    with pytest.raises(GitNestedError, match='git tracks nothing in it'):
        _adopt_existing_subdir(git, Flags(adopt=True), config, vendored, gitnested, 'vendor/bar', 'head')


def test_resolve_upstream_commit_needs_remote():
    """A commit without a remote says nothing useful."""
    flags = Flags(upstream_commit='abc')
    config = NestedConfig()

    with pytest.raises(GitNestedError, match='--commit needs --remote'):
        _resolve_upstream_commit(NO_GIT, flags, config, 'vendor/bar')


def test_resolve_upstream_commit_requires_an_existing_commit():
    """The named sync point has to exist after the fetch."""
    git = (
        FakeGit()
        .respond('fetch', '--no-tags', '--quiet', 'origin', 'main')
        .respond('rev-parse', 'FETCH_HEAD^0', stdout='fetched-head')
        .respond('update-ref', 'refs/nested/vendor/bar/fetch', 'FETCH_HEAD^0')
        .respond('rev-list', 'abc', '-1', returncode=1)
    )
    flags = Flags(upstream_commit='abc')
    config = NestedConfig(remote='origin', branch='main')

    with pytest.raises(GitNestedError, match='no such upstream commit: abc'):
        _resolve_upstream_commit(git, flags, config, 'vendor/bar')


def test_resolve_upstream_commit_requires_commit_on_tracked_branch():
    """The recorded sync point must belong to the branch that will be pulled."""
    git = (
        FakeGit()
        .respond('fetch', '--no-tags', '--quiet', 'origin', 'main')
        .respond('rev-parse', 'FETCH_HEAD^0', stdout='fetched-head')
        .respond('update-ref', 'refs/nested/vendor/bar/fetch', 'FETCH_HEAD^0')
        .respond('rev-list', 'abc', '-1', stdout='abc\n')
        .respond('merge-base', '--is-ancestor', 'abc', 'fetched-head', returncode=1)
    )
    flags = Flags(upstream_commit='abc')
    config = NestedConfig(remote='origin', branch='main')

    with pytest.raises(GitNestedError, match='abc: is not part of origin \\(main\\)'):
        _resolve_upstream_commit(git, flags, config, 'vendor/bar')
