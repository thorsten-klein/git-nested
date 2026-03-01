"""Tests for git nested clean command"""

from conftest import cmd_git_nested


def test_clean(foo_bar_cloned_and_nested):
    """Test basic nested clean functionality"""
    env = foo_bar_cloned_and_nested

    # Make changes and create branch
    env.add_new_files('bar/file', cwd=env.workspace / 'foo')
    cmd_git_nested('--quiet branch bar', cwd=env.workspace / 'foo')

    # Check refs exist
    assert (env.workspace / 'foo' / '.git' / 'refs' / 'heads' / 'nested' / 'bar').exists()
    assert (env.workspace / 'foo' / '.git' / 'refs' / 'nested' / 'bar' / 'fetch').exists()

    # Do the clean and check output
    result = cmd_git_nested('clean bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Removed branch 'nested/bar'."

    # Check that branch ref was removed
    assert not (env.workspace / 'foo' / '.git' / 'refs' / 'heads' / 'nested' / 'bar').exists()

    # Check that fetch ref still exists
    assert (env.workspace / 'foo' / '.git' / 'refs' / 'nested' / 'bar' / 'fetch').exists()

    # Clean with --force
    cmd_git_nested('clean --force bar', cwd=env.workspace / 'foo')

    # Check that fetch ref is also removed now
    assert not (env.workspace / 'foo' / '.git' / 'refs' / 'nested' / 'bar' / 'fetch').exists()
