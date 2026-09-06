"""Tests for git nested init command"""

import textwrap

from conftest import assert_gitnested_field, cmd_git_nested


def test_init_no_remote(env):
    """Test basic nested init functionality"""
    env.clone_init()

    gitnested = env.workspace / 'init' / 'doc' / '.gitnested'
    assert not gitnested.exists()

    # init the nested repository
    result = cmd_git_nested('init doc', cwd=env.workspace / 'init')

    # Test init/doc/.gitnested file contents
    assert result.output.strip() == "doc: initialised as a nested repository with no remote"
    assert_gitnested_field(gitnested, remote='none', branch='master', commit='', parent='', method='merge')


def test_init_with_remote(env):
    """Test basic nested init functionality"""
    env.clone_init()

    gitnested = env.workspace / 'init' / 'doc' / '.gitnested'
    assert not gitnested.exists()

    # Init with options
    result = cmd_git_nested('init doc -r git@github.com:user/repo -b foo -M rebase', cwd=env.workspace / 'init')

    # Test init/doc/.gitnested file contents
    assert result.output.strip() == "doc: initialised as a nested repository with git@github.com:user/repo (foo)"
    assert_gitnested_field(
        gitnested, remote='git@github.com:user/repo', branch='foo', commit='', parent='', method='rebase'
    )


def test_verbose(env):
    """Test that --verbose works"""
    env.clone_init()

    # Test verbose mode with init command
    cp = cmd_git_nested('--verbose init doc', cwd=env.workspace / 'init')
    assert cp.returncode == 0
    assert cp.output.strip() == textwrap.dedent("""\
        * checking for a worktree on nested/doc
        * writing doc/.gitnested
        * staging doc/.gitnested
        * committing
        doc: initialised as a nested repository with no remote""")


def test_init_nonexistent_subdir(env):
    """Test that init fails when the subdir doesn't exist"""
    env.clone_init()
    result = cmd_git_nested('init nonexistent', cwd=env.workspace / 'init', check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: nonexistent: does not exist"


def test_init_already_a_nested_repository(env):
    """Test that init fails when the subdir is already a nested repository"""
    env.clone_init()
    cmd_git_nested('init doc', cwd=env.workspace / 'init')
    result = cmd_git_nested('init doc', cwd=env.workspace / 'init', check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: doc: is already a nested repository"


def test_init_untracked_subdir(env):
    """Test that init fails when the subdir exists but nothing is tracked by git"""
    env.clone_init()
    untracked = env.workspace / 'init' / 'untracked'
    untracked.mkdir()
    (untracked / 'scratch.txt').write_text('not tracked\n')
    result = cmd_git_nested('init untracked', cwd=env.workspace / 'init', check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: untracked: exists, but git tracks nothing in it"
