"""Tests for git nested clone command"""

from conftest import assert_gitnested_field, git_rev_parse, cmd_git_nested
import textwrap
import git_nested


def test_clone_into_empty_repo(env):
    # Test clone into empty repository fails
    empty_dir = env.workspace / 'empty'
    empty_dir.mkdir(parents=True)
    env.run(['git', 'init'], cwd=empty_dir)
    assert (env.workspace / 'empty' / '.git').is_dir()
    result = cmd_git_nested(f'clone {env.upstream}/bar', cwd=empty_dir, check=False)
    assert result.stderr.strip() == "git-nested: You can't clone into an empty repository"

    # assert that repo has no changes
    result = env.run(['git', 'status', '-s'], cwd=empty_dir)
    assert result.stdout.strip() == ''


def test_basic_clone(foo_bar_cloned):
    """Test basic nested clone functionality"""
    env = foo_bar_cloned

    # Test that the repos look ok
    assert (env.workspace / 'foo' / '.git').is_dir()
    assert (env.workspace / 'foo' / 'Foo').is_file()
    assert not (env.workspace / 'foo' / 'bar').exists()
    assert (env.workspace / 'bar' / '.git').is_dir()
    assert (env.workspace / 'bar' / 'Bar').is_file()

    # Do the nested clone and test the output
    result = cmd_git_nested(f'clone {env.upstream}/bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository '{env.upstream}/bar' (master) cloned into 'bar'."

    # Check no remotes created
    result = env.run(['git', 'remote', '-v'], cwd=env.workspace / 'foo')
    assert result.stdout.strip() == textwrap.dedent(f"""\
        origin\t{env.upstream}/foo (fetch)
        origin\t{env.upstream}/foo (push)""")

    # Check that nested files look ok
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'
    assert (env.workspace / 'foo' / 'bar').is_dir()
    assert (env.workspace / 'foo' / 'bar' / 'Bar').is_file()
    assert gitnested.is_file()

    # Test foo/bar/.gitnested file contents
    foo_clone_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')

    assert_gitnested_field(
        gitnested,
        remote=str(env.upstream / 'bar'),
        branch='master',
        commit=bar_head_commit,
        parent=foo_clone_commit,
        method='merge',
        version=git_nested.VERSION,
    )

    # Make sure status is clean
    result = env.run(['git', 'status', '-s'], cwd=env.workspace / 'foo')
    assert result.stdout.strip() == ''


def test_clone_tags(foo_bar_cloned):
    """Test cloning nested with annotated and lightweight tags"""
    env = foo_bar_cloned

    # Create tags in bar repo
    env.run(['git', 'tag', '-a', 'annotated_tag', '-m', 'My annotated tag'], cwd=env.workspace / 'bar')
    env.run(['git', 'tag', 'lightweight_tag'], cwd=env.workspace / 'bar')
    env.run(['git', 'push', '--tags'], cwd=env.workspace / 'bar')

    # Clone with lightweight tag
    result = cmd_git_nested(
        f'clone {env.upstream}/bar light -b lightweight_tag ', cwd=env.workspace / 'foo', check=False
    )
    assert result.stdout.strip() == f"Nested repository '{env.upstream}/bar' (lightweight_tag) cloned into 'light'."

    # Clone with annotated tag
    result = cmd_git_nested(f'clone {env.upstream}/bar annotated -b annotated_tag', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository '{env.upstream}/bar' (annotated_tag) cloned into 'annotated'."


def test_clone_with_quiet_verbose(foo_bar_cloned):
    """Test clone command with --quiet and --verbose flags"""
    env = foo_bar_cloned

    # Test clone with --quiet
    result = cmd_git_nested(f'--quiet clone {env.upstream}/bar bar1', cwd=env.workspace / 'foo')
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == ""
    assert (env.workspace / 'foo' / 'bar1').is_dir()

    # Test clone with --verbose
    result = cmd_git_nested(f'--verbose clone {env.upstream}/bar bar2', cwd=env.workspace / 'foo')
    assert result.returncode == 0
    assert result.stdout.strip() == textwrap.dedent(f"""\
        * Check for worktree with branch nested/bar2
        * Determine the upstream head branch.
        * Fetch the upstream: {env.upstream}/bar (master).
        * Get the upstream nested HEAD commit.
        * Make the directory 'bar2/' for the clone.
        * Commit the new 'bar2/' content.
        * Checking that the nested repository commit exists.
        * Make sure that the commit contains the upstream HEAD.
        * Put remote nested content into 'bar2/'.
        * Put info into 'bar2/.gitnested' file.
        * Commit .gitnested update to the current branch.
        Nested repository '{env.upstream}/bar' (master) cloned into 'bar2'.""")
    assert result.stderr.strip() == ""
    assert (env.workspace / 'foo' / 'bar2').is_dir()
