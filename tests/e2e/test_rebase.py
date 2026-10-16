"""Tests for git nested with rebase"""

from conftest import cmd_git_nested


def test_rebase(foo_bar_cloned):
    """Test nested operations after rebase"""
    env = foo_bar_cloned
    # Setup foo with 2 branches, one before the nested
    # is added and one after so that we can rebase
    # thus destroying the parent in two ways

    # Create branch1, add file, clone nested, create branch2, add file
    env.run(['git', 'switch', '-c', 'branch1'], cwd=env.workspace / 'foo')
    env.add_new_files('foo1', cwd=env.workspace / 'foo')
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], env.workspace / 'foo')

    env.run(['git', 'branch', 'branch2'], cwd=env.workspace / 'foo')
    env.add_new_files('foo2', cwd=env.workspace / 'foo')

    # Add new file in bar and push
    env.add_new_files('bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Pull nested
    cmd_git_nested('pull bar', cwd=env.workspace / 'foo')

    # Rebase branch1 onto branch2
    env.run(['git', 'switch', 'branch2'], cwd=env.workspace / 'foo')
    env.add_new_files('foo-branch2', cwd=env.workspace / 'foo')

    env.run(['git', 'switch', 'branch1'], cwd=env.workspace / 'foo')
    env.run(['git', 'rebase', 'branch2'], cwd=env.workspace / 'foo')

    # The recorded sync point was rewritten; the one in this history is found
    cmd_git_nested('clean --force --all', cwd=env.workspace / 'foo')
    cp = env.run('git nested branch bar', check=False, cwd=env.workspace / 'foo')
    assert cp.returncode == 0
    lines = cp.output.strip().splitlines()
    assert lines[0].startswith("git-nested: bar: the recorded sync point is not in this history; using ")
    assert lines[0].endswith(" instead. 'git nested repair bar' records it")
    assert lines[1] == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"
