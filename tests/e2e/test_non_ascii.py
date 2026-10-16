"""Tests for paths with non-ASCII characters"""

from conftest import cmd_git_nested


def test_status_and_all_find_a_non_ascii_path(foo_bar_cloned):
    """git quotes such a path unless asked for -z; it must still be found."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix(), 'bibliothèk'], foo)

    assert cmd_git_nested('-q status', cwd=foo).stdout.strip() == 'bibliothèk'
    assert "bibliothèk: fetched from" in cmd_git_nested('fetch --all', cwd=foo).output


def test_a_regex_filter_matches_a_non_ascii_path(foo_bar_cloned):
    """A filter pattern is matched against the real path, not git's quoted one."""
    env = foo_bar_cloned
    env.add_new_files('Bär', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix(), '--filter', 'B.r'], env.workspace / 'foo')

    assert (env.workspace / 'foo' / 'bar' / 'Bär').is_file()
