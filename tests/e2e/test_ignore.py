"""Tests for --ignore on pull and push"""

import pytest
from conftest import cmd_git_nested


def _upstream_show(env, path):
    return env.run(['git', 'show', f'master:{path}'], cwd=env.upstream / 'bar').output


def _upstream_files(env):
    return env.run(['git', 'ls-tree', '-r', '--name-only', 'master'], cwd=env.upstream / 'bar').output.split()


def _change_upstream(env, *files):
    bar = env.workspace / 'bar'
    env.modify_files(*files, text='from upstream', cwd=bar)
    env.run(['git', 'push'], cwd=bar)


@pytest.mark.parametrize('method', ['merge', 'rebase'])
def test_pull_ignore_keeps_the_local_path(foo_bar_cloned_and_nested, method):
    """Upstream's change to the path does not come in; the rest does."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.modify_files('bar/bard/Bard', text='local', cwd=foo)
    _change_upstream(env, 'Bar', 'bard/Bard')

    cmd_git_nested(['pull', f'--{method}', '--ignore', 'bar/bard', 'bar'], cwd=foo)

    assert 'from upstream' in (foo / 'bar' / 'Bar').read_text()
    bard = (foo / 'bar' / 'bard' / 'Bard').read_text()
    assert 'local' in bard
    assert 'from upstream' not in bard


def test_pull_ignore_a_path_upstream_adds(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo, bar = env.workspace / 'foo', env.workspace / 'bar'
    env.add_new_files('new/file', 'other', cwd=bar)
    env.run(['git', 'push'], cwd=bar)

    cmd_git_nested('pull --ignore bar/new bar', cwd=foo)

    assert (foo / 'bar' / 'other').is_file()
    assert not (foo / 'bar' / 'new').exists()


def test_pull_ignore_from_a_subdirectory(foo_bar_cloned_and_nested):
    """The path is given like <subdir>, relative to where the command runs."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _change_upstream(env, 'Bar', 'bard/Bard')

    cmd_git_nested('pull --ignore bard', cwd=foo / 'bar')

    assert 'from upstream' in (foo / 'bar' / 'Bar').read_text()
    assert 'from upstream' not in (foo / 'bar' / 'bard' / 'Bard').read_text()


def test_push_ignore_keeps_the_upstream_path(foo_bar_cloned_and_nested):
    """The local change to the path is not pushed; the rest is."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.modify_files('bar/Bar', 'bar/bard/Bard', text='local', cwd=foo)
    env.add_new_files('bar/bard/new', cwd=foo)

    cmd_git_nested('push -b master --ignore bar/bard bar', cwd=foo)

    assert 'local' in _upstream_show(env, 'Bar')
    assert 'local' not in _upstream_show(env, 'bard/Bard')
    assert sorted(_upstream_files(env)) == ['Bar', 'bard/Bard']


def test_push_ignore_only_ignored_changes_pushes_nothing(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.modify_files('bar/bard/Bard', text='local', cwd=foo)

    result = cmd_git_nested('push -b master --ignore bar/bard bar', cwd=foo)

    assert "bar: nothing to push" in result.output


@pytest.mark.parametrize(
    ('ignore', 'message'),
    [('elsewhere', "not inside bar"), ('bar', "that is all of bar")],
)
def test_ignore_must_be_inside_subdir(foo_bar_cloned_and_nested, ignore, message):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested(['pull', '--ignore', ignore, 'bar'], cwd=env.workspace / 'foo', check=False)
    assert result.returncode != 0
    assert message in result.output


def test_pull_ignore_with_force_is_refused(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('pull --force --ignore bar/bard bar', cwd=env.workspace / 'foo', check=False)
    assert result.returncode != 0
    assert "--ignore can't be combined with --force" in result.output


def test_push_with_an_explicit_branch_refuses_ignore(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('push --ignore bar/bard bar some-branch', cwd=env.workspace / 'foo', check=False)
    assert result.returncode != 0
    assert "--ignore can't be combined with an explicit branch" in result.output


def test_ignore_without_an_upstream_commit(foo_bar_cloned):
    """Without a recorded upstream commit, push leaves the path out and pull refuses."""
    env = foo_bar_cloned
    foo, empty = env.workspace / 'foo', env.upstream / 'new'
    env.run(['git', 'init', '-q', '--bare', empty.as_posix()])
    env.add_new_files('mine/file', 'mine/secret/key', cwd=foo)
    cmd_git_nested(['init', '-r', empty.as_posix(), '-b', 'master', 'mine'], foo)

    cmd_git_nested('push --ignore mine/secret mine', cwd=foo)
    files = env.run(['git', 'ls-tree', '-r', '--name-only', 'master'], cwd=empty).output.split()
    assert files == ['file']

    result = cmd_git_nested('pull --ignore mine/secret mine', cwd=foo, check=False)
    assert result.returncode != 0
    assert "--ignore needs the upstream commit in .gitnested" in result.output
