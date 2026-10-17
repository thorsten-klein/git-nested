"""Tests for --path: nest one directory of upstream at the root of the subdir"""

import yaml
from conftest import cmd_git_nested


def _clone_bard(env):
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', '--path', 'bard', (env.upstream / 'bar').as_posix(), 'lib'], foo)
    return foo


def test_clone_path_puts_the_directory_at_the_root(foo_bar_cloned):
    env = foo_bar_cloned
    foo = _clone_bard(env)

    assert (foo / 'lib' / 'Bard').is_file()
    assert not (foo / 'lib' / 'Bar').exists()
    assert yaml.safe_load((foo / 'lib' / '.gitnested').read_text())['nested']['path'] == 'bard'
    assert cmd_git_nested('diff lib', cwd=foo).output.strip().startswith("lib: no differences from")


def test_pull_takes_only_the_directory(foo_bar_cloned):
    env = foo_bar_cloned
    foo, bar = _clone_bard(env), env.workspace / 'bar'
    env.modify_files('bard/Bard', 'Bar', cwd=bar)
    env.run(['git', 'push'], cwd=bar)

    cmd_git_nested('pull lib', cwd=foo)

    assert 'a new line' in (foo / 'lib' / 'Bard').read_text()
    assert not (foo / 'lib' / 'Bar').exists()


def test_push_puts_the_changes_back_under_the_directory(foo_bar_cloned):
    env = foo_bar_cloned
    foo = _clone_bard(env)
    env.add_new_files('lib/from-foo', cwd=foo)

    cmd_git_nested('push -b master lib', cwd=foo)

    files = env.run(['git', 'ls-tree', '-r', '--name-only', 'master'], cwd=env.upstream / 'bar').output.split()
    assert sorted(files) == ['Bar', 'bard/Bard', 'bard/from-foo']


def test_clone_path_must_be_a_directory_of_upstream(foo_bar_cloned):
    env = foo_bar_cloned

    result = cmd_git_nested(
        ['clone', '--path', 'nope', (env.upstream / 'bar').as_posix(), 'lib'], env.workspace / 'foo', check=False
    )

    assert result.returncode == 1
    assert "upstream has no directory nope" in result.output


def test_clone_path_and_filter_do_not_go_together(foo_bar_cloned):
    env = foo_bar_cloned
    args = ['clone', '--path', 'bard', '--filter', 'Bard', (env.upstream / 'bar').as_posix(), 'lib']

    result = cmd_git_nested(args, env.workspace / 'foo', check=False)

    assert result.returncode == 1
    assert result.output.strip() == "git-nested: --path and --filter can't be used together"
