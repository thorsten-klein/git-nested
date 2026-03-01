"""Tests for git nested with submodules"""

from conftest import cmd_git_nested


def test_submodule(foo_bar_cloned):
    """Test that a nested that contains a submodule retains the submodule reference"""
    env = foo_bar_cloned

    # Add submodule reference along with a new file to the bar repo
    env.run(['git', 'clone', '../foo', 'submodule'], cwd=env.workspace / 'bar')
    env.add_new_files('file', cwd=env.workspace / 'bar')
    env.run(['git', 'add', 'submodule', 'file'], cwd=env.workspace / 'bar')
    env.run(['git', 'commit', '--amend', '-C', 'HEAD'], cwd=env.workspace / 'bar')

    # Clone bar into foo
    cmd_git_nested('clone ../bar', cwd=env.workspace / 'foo')

    # Modify file in bar
    env.modify_files('file', cwd=env.workspace / 'bar')

    # Pull and verify
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')

    assert result.stdout.strip() == "Nested repository 'bar' pulled from '../bar' (master)."
