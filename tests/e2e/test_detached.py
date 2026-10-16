"""Tests on a detached HEAD, as CI systems and jj have it"""

from conftest import cmd_git_nested


def test_commands_work_on_a_detached_head(foo_bar_cloned_and_nested):
    """Commits land on the detached HEAD, as git commit does it."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.run(['git', 'checkout', '-q', '--detach'], cwd=foo)
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    cmd_git_nested('pull bar', cwd=foo)
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix(), 'bar2'], foo)
    env.add_new_files('bar/from-foo', cwd=foo)
    cmd_git_nested('push -b master bar', cwd=foo)

    assert (foo / 'bar' / 'Bar2').is_file()
    assert (foo / 'bar2' / '.gitnested').is_file()
    assert env.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=foo, check=False).returncode == 1
