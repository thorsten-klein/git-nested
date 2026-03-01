"""Tests for git nested error messages"""

import pytest
from conftest import cmd_git_nested, git_rev_parse


def test_help(env):
    """Test that the help is shown"""
    env.clone_init()

    # Test using --help without command
    result = cmd_git_nested('--help', cwd=env.workspace / 'init')
    assert result.returncode == 0
    assert 'usage: git nested [-h] [--version] [-q] [-v]' in result.stdout
    assert result.stderr.strip() == ""

    result = cmd_git_nested('clone --help', cwd=env.workspace / 'init')
    assert result.returncode == 0
    assert 'usage: git nested clone [-h]' in result.stdout
    assert result.stderr.strip() == ""

    result = cmd_git_nested('status --help', cwd=env.workspace / 'init')
    assert result.returncode == 0
    assert 'usage: git nested status [-h]' in result.stdout
    assert result.stderr.strip() == ""


def assert_argparse_error(cp, error_msg, returncode=2):
    assert cp.returncode == returncode
    assert cp.stdout.strip() == ""
    assert "usage: git nested" in cp.stderr
    assert error_msg in cp.stderr


def assert_stderr(cp, error_msg, returncode=2):
    assert cp.returncode == returncode
    assert cp.stdout.strip() == ""
    assert error_msg in cp.stderr


def test_error_branch_already_exists(foo_bar_cloned):
    """Test error when creating a branch that already exists"""
    env = foo_bar_cloned
    cmd_git_nested(f'clone {env.upstream}/foo', cwd=env.workspace / 'bar')
    env.add_new_files('foo/file', cwd=env.workspace / 'bar')
    cmd_git_nested('branch foo', cwd=env.workspace / 'bar')
    cp = cmd_git_nested('branch foo', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: Branch 'nested/foo' already exists. Use '--force' to override.", returncode=1)


def test_error_clone_missing_upstream(foo_bar_cloned):
    """Test error for missing clone upstream"""
    env = foo_bar_cloned
    cp = cmd_git_nested('clone', check=False, cwd=env.workspace / 'bar')
    assert_argparse_error(cp, "git nested clone: error: the following arguments are required: upstream")

    cp = cmd_git_nested('clone dummy --foo', check=False, cwd=env.workspace / 'bar')
    assert_argparse_error(cp, "git nested: error: unrecognized arguments: --foo")


def test_error_unknown_command(foo_bar_cloned):
    """Test error for unknown command"""
    env = foo_bar_cloned
    cp = cmd_git_nested('main 1 2 3', check=False, cwd=env.workspace / 'bar')
    assert_argparse_error(cp, "git nested: error: argument command: invalid choice: 'main'")

    # the following text depends on the python version. The single quotes might be missing.
    text = "(choose from 'branch', 'clean', 'clone', 'commit', 'fetch', 'init', 'pull', 'push', 'status', 'version')"
    assert (text in cp.stderr) or (text.replace("'", "") in cp.stderr)


def test_error_update_requires_branch_or_remote(foo_bar_cloned):
    """Test error when --update is used without --branch or --remote"""
    env = foo_bar_cloned
    cp = cmd_git_nested('pull --update', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: Can't use '--update' without '--branch' or '--remote'.", returncode=1)


def test_error_invalid_option_for_clone(foo_bar_cloned):
    """Test error for invalid option --all for clone command"""
    env = foo_bar_cloned
    cp = cmd_git_nested('clone xxx --all', check=False, cwd=env.workspace / 'bar')
    assert_argparse_error(cp, "git nested: error: unrecognized arguments: --all")


def test_error_subdir_is_absolute_path(foo_bar_cloned):
    """Test error when subdir is an absolute path"""
    env = foo_bar_cloned
    cp = cmd_git_nested('pull /home/user/bar/foo', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: The subdir '/home/user/bar/foo' should not be absolute path.", returncode=1)


@pytest.mark.parametrize('cmd', ['pull', 'push', 'fetch', 'branch', 'commit', 'clean'])
def test_error_command_requires_subdir(foo_bar_cloned, cmd):
    """Test error when command is called without required subdir argument"""
    env = foo_bar_cloned
    cp = env.run(f'git nested {cmd}', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: subdir not set", returncode=1)


def test_error_extra_arguments_for_clone(foo_bar_cloned):
    """Test error when clone command receives too many arguments"""
    env = foo_bar_cloned
    cp = cmd_git_nested('clone foo bar baz quux', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git nested: error: unrecognized arguments: baz quux")


def test_error_cannot_determine_subdir(foo_bar_cloned):
    """Test error when subdir cannot be determined from path"""
    env = foo_bar_cloned
    cp = cmd_git_nested('clone .git', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: subdir not set", returncode=1)


def test_error_invalid_nested_subdir(foo_bar_cloned):
    """Test error when operating on non-existent nested subdir"""
    env = foo_bar_cloned
    cp = cmd_git_nested('pull lala', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: No 'lala/.gitnested' file.", returncode=1)


def test_error_not_on_branch(foo_bar_cloned):
    """Test error when repo is in detached HEAD state"""
    env = foo_bar_cloned
    commit = git_rev_parse(['master'], cwd=env.workspace / 'bar')
    env.run(['git', 'checkout', '--quiet', commit], cwd=env.workspace / 'bar')
    cp = cmd_git_nested('status', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: Must be on a branch to run this command.", returncode=1)


def test_error_outside_working_tree(foo_bar_cloned):
    """Test error when command is run outside working tree"""
    env = foo_bar_cloned
    cp = cmd_git_nested('status', check=False, cwd=env.workspace / 'bar' / '.git')
    assert_stderr(cp, "git-nested: Must run inside a git working tree.", returncode=1)


def test_error_working_tree_has_changes(foo_bar_cloned):
    """Test error when trying to clone with uncommitted changes"""
    env = foo_bar_cloned
    (env.workspace / 'bar' / 'me').touch()
    env.run(['git', 'add', 'me'], cwd=env.workspace / 'bar')
    cp = env.run(f'git nested clone {env.upstream}/foo', check=False, cwd=env.workspace / 'bar')
    assert_stderr(
        cp, f"git-nested: Can't clone nested repository. Working tree has changes. ({env.workspace}/bar)", returncode=1
    )


def test_error_not_at_top_level(foo_bar_cloned):
    """Test error when command is run from subdirectory"""
    env = foo_bar_cloned
    (env.workspace / 'foo' / 'subdir').mkdir()
    cp = cmd_git_nested('status', check=False, cwd=env.workspace / 'foo' / 'subdir')
    assert_stderr(cp, "git-nested: Need to run nested command from top level directory of the repo.", returncode=1)


def test_error_clone_non_empty_subdir(foo_bar_cloned):
    """Test error when trying to clone into non-empty directory"""
    env = foo_bar_cloned
    cp = cmd_git_nested('clone dummy bard', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: The subdir 'bard' exists and is not empty.", returncode=1)


def test_error_clone_non_repo(foo_bar_cloned):
    """Test error when trying to clone from invalid repository"""
    env = foo_bar_cloned
    cp = cmd_git_nested('clone dummy-repo', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: Command failed: 'git ls-remote --symref dummy-repo'.", returncode=1)


def test_error_all_with_branch(foo_bar_cloned):
    """Test error when --all and --branch are used together"""
    env = foo_bar_cloned
    cmd_git_nested(f'clone {env.upstream}/foo', cwd=env.workspace / 'bar')
    cp = cmd_git_nested('pull --all --branch other', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: options --branch and --all are not compatible", returncode=1)


def test_error_message_and_file_together(foo_bar_cloned):
    """Test error when -m and --file are used together"""
    env = foo_bar_cloned
    cmd_git_nested(f'clone {env.upstream}/foo', cwd=env.workspace / 'bar')
    env.add_new_files('foo/newfile', cwd=env.workspace / 'bar')

    # Create a commit message file
    msg_file = env.workspace / 'bar' / 'commit_msg.txt'
    msg_file.write_text('Test commit message')

    cp = cmd_git_nested('commit foo -m "Test" --file commit_msg.txt', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: fatal: options '-m' and '--file' cannot be used together", returncode=1)


def test_error_missing_commit_msg_file(foo_bar_cloned):
    """Test error when commit message file doesn't exist"""
    env = foo_bar_cloned
    cmd_git_nested(f'clone {env.upstream}/foo', cwd=env.workspace / 'bar')
    env.add_new_files('foo/newfile', cwd=env.workspace / 'bar')

    cp = cmd_git_nested('commit foo --file nonexistent.txt', check=False, cwd=env.workspace / 'bar')
    assert_stderr(cp, "git-nested: Commit msg file at nonexistent.txt not found", returncode=1)
