"""Tests for git nested init command"""

from conftest import assert_gitnested_field, cmd_git_nested
import textwrap


def test_init_no_remote(env):
    """Test basic nested init functionality"""
    env.clone_init()

    gitnested = env.workspace / 'init' / 'doc' / '.gitnested'
    assert not gitnested.exists()

    # init the nested repository
    result = cmd_git_nested('init doc', cwd=env.workspace / 'init')

    # Test init/doc/.gitnested file contents
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == "Nested repository created from 'doc' (with no remote)."
    assert_gitnested_field(gitnested, remote='none', branch='master', commit='', parent='', method='merge')


def test_init_with_remote(env):
    """Test basic nested init functionality"""
    env.clone_init()

    gitnested = env.workspace / 'init' / 'doc' / '.gitnested'
    assert not gitnested.exists()

    # Init with options
    result = cmd_git_nested('init doc -r git@github.com:user/repo -b foo -M rebase', cwd=env.workspace / 'init')

    # Test init/doc/.gitnested file contents
    assert result.stderr.strip() == ""
    assert result.stdout.strip() == "Nested repository created from 'doc' with remote 'git@github.com:user/repo' (foo)."
    assert_gitnested_field(
        gitnested, remote='git@github.com:user/repo', branch='foo', commit='', parent='', method='rebase'
    )


def test_verbose(env):
    """Test that --verbose works"""
    env.clone_init()

    # Test verbose mode with init command
    cp = cmd_git_nested('--verbose init doc', cwd=env.workspace / 'init')
    assert cp.returncode == 0
    assert cp.stdout.strip() == textwrap.dedent("""\
        * Check for worktree with branch nested/doc
        * Put info into 'doc/.gitnested' file.
        * Add the new 'doc/.gitnested' file.
        * Commit the changes.
        Nested repository created from 'doc' (with no remote).""")
    assert cp.stderr.strip() == ""
