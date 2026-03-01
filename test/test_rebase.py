"""Tests for git nested with rebase"""

from conftest import cmd_git_nested

import textwrap


def test_rebase(foo_bar_cloned):
    """Test nested operations after rebase"""
    env = foo_bar_cloned
    # Setup foo with 2 branches, one before the nested
    # is added and one after so that we can rebase
    # thus destroying the parent in two ways

    # Create branch1, add file, clone nested, create branch2, add file
    env.run(['git', 'switch', '-c', 'branch1'], cwd=env.workspace / 'foo')
    env.add_new_files('foo1', cwd=env.workspace / 'foo')
    cmd_git_nested(['clone', str(env.upstream / 'bar')], env.workspace / 'foo')

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

    # Force clean to search for the parent SHA
    # Validate it found the previous merge point
    cmd_git_nested('clean --force --all', cwd=env.workspace / 'foo')
    cp = env.run('git nested branch bar', check=False, cwd=env.workspace / 'foo')
    assert cp.stdout.strip() == ""
    assert cp.stderr.strip() == textwrap.dedent("""\
        git-nested: The last sync point (where upstream and the nested were equal) is not an ancestor.
        This is usually caused by a rebase affecting that commit.
        To recover set the nested parent in 'bar/.gitnested'
        to ''
        and validate the nested by comparing with 'git nested branch bar'""")
