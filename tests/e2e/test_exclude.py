"""Tests for --exclude, and for what a push does with paths git-nested does not manage"""

import yaml
from conftest import cmd_git_nested


def _upstream_files(env):
    return env.run(['git', 'ls-tree', '-r', '--name-only', 'master'], cwd=env.upstream / 'bar').output.split()


def test_clone_exclude_leaves_a_path_out(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'

    cmd_git_nested(['clone', '--exclude', 'bard', (env.upstream / 'bar').as_posix()], foo)

    assert (foo / 'bar' / 'Bar').is_file()
    assert not (foo / 'bar' / 'bard').exists()
    assert yaml.safe_load((foo / 'bar' / '.gitnested').read_text())['nested']['exclude'] == ['bard']


def test_pull_keeps_the_excluded_path_out(foo_bar_cloned):
    """An upstream change to an excluded path neither comes in nor conflicts."""
    env = foo_bar_cloned
    foo, bar = env.workspace / 'foo', env.workspace / 'bar'
    cmd_git_nested(['clone', '--exclude', 'bard', (env.upstream / 'bar').as_posix()], foo)
    env.modify_files('bard/Bard', 'Bar', cwd=bar)
    env.run(['git', 'push'], cwd=bar)

    cmd_git_nested('pull bar', cwd=foo)

    assert 'a new line' in (foo / 'bar' / 'Bar').read_text()
    assert not (foo / 'bar' / 'bard').exists()


def test_push_keeps_the_excluded_path_upstream(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', '--exclude', 'bard', (env.upstream / 'bar').as_posix()], foo)
    env.add_new_files('bar/from-foo', cwd=foo)

    cmd_git_nested('push -b master bar', cwd=foo)

    assert sorted(_upstream_files(env)) == ['Bar', 'bard/Bard', 'from-foo']


def test_push_keeps_what_a_filter_leaves_out_upstream(foo_bar_cloned):
    """A filtered push must not delete the paths outside the filter."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', '--filter', 'Bar', (env.upstream / 'bar').as_posix()], foo)
    env.modify_files('bar/Bar', cwd=foo)

    cmd_git_nested('push -b master bar', cwd=foo)

    assert sorted(_upstream_files(env)) == ['Bar', 'bard/Bard']


def test_diff_ignores_the_excluded_path(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', '--exclude', 'bard', (env.upstream / 'bar').as_posix()], foo)

    result = cmd_git_nested('diff bar', cwd=foo)

    assert result.output.strip().startswith("bar: no differences from")


def test_status_compares_only_what_is_nested(foo_bar_cloned):
    """The excluded path is missing locally by design; the content is still the same as upstream's."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', '--exclude', 'bard', (env.upstream / 'bar').as_posix()], foo)

    assert cmd_git_nested('status --short', cwd=foo).stdout.strip() == "bar 0 0 same"
