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
    assert result.output.strip() == "removed branch 'nested/bar'"

    # Check that branch ref was removed
    assert not (env.workspace / 'foo' / '.git' / 'refs' / 'heads' / 'nested' / 'bar').exists()

    # Check that fetch ref still exists
    assert (env.workspace / 'foo' / '.git' / 'refs' / 'nested' / 'bar' / 'fetch').exists()

    # Clean with --force
    cmd_git_nested('clean --force bar', cwd=env.workspace / 'foo')

    # Check that fetch ref is also removed now
    assert not (env.workspace / 'foo' / '.git' / 'refs' / 'nested' / 'bar' / 'fetch').exists()


def _undo_the_clone(env):
    """Clone bar, branch it, then reset the clone away: branch and worktree stay, .gitnested goes."""
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], foo)
    cmd_git_nested('branch bar', cwd=foo)
    env.run(['git', 'reset', '-q', '--hard', 'HEAD^'], cwd=foo)
    assert not (foo / 'bar' / '.gitnested').exists()
    return foo


def _leftovers(env, foo):
    branches = env.run(['git', 'for-each-ref', 'refs/heads/nested/', 'refs/nested/'], cwd=foo).output
    return branches, (foo / '.git' / 'tmp' / 'nested' / 'bar').exists()


def test_clean_without_gitnested(foo_bar_cloned):
    """clean needs no .gitnested to remove what a nested repository left behind."""
    env = foo_bar_cloned
    foo = _undo_the_clone(env)

    result = cmd_git_nested('clean bar', cwd=foo)

    assert result.output.strip() == "removed branch 'nested/bar'"
    assert not (foo / '.git' / 'tmp' / 'nested' / 'bar').exists()
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], foo)


def test_clean_force_all_without_gitnested(foo_bar_cloned):
    """clean --force --all also finds what is left of a repository that is no longer nested."""
    env = foo_bar_cloned
    foo = _undo_the_clone(env)

    result = cmd_git_nested('clean --force --all', cwd=foo)

    assert result.output.strip() == "removed branch 'nested/bar'"
    assert _leftovers(env, foo) == ('', False)
