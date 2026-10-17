"""Tests for git nested fetch command"""

from conftest import cmd_git_nested, git_rev_parse


def test_fetch(foo_bar_cloned_and_nested):
    """Test basic nested fetch functionality"""
    env = foo_bar_cloned_and_nested

    # Add new file with annotated tag to bar and push
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'tag', '-a', 'CoolTag', '-m', 'Should stay in nested'], cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Fetch information
    result = cmd_git_nested('fetch bar', cwd=env.workspace / 'foo')
    assert result.output.strip() == f"bar: fetched from {env.upstream.as_posix()}/bar (master)"

    # Check that there is no tags fetched
    result = env.run(['git', 'tag', '-l', 'CoolTag'], cwd=env.workspace / 'foo')
    assert result.stdout.strip() == ''


def test_fetch_with_no_remote(env):
    """Test fetch command when nested has no remote"""
    env.clone_init()

    # Initialize the nested with no remote
    cmd_git_nested('init doc', cwd=env.workspace / 'init')

    # Try to fetch - should skip with message
    result = cmd_git_nested('fetch doc', cwd=env.workspace / 'init')
    assert result.output.strip() == "doc: skipped, it has no remote"


def test_fetch_all_with_branch_skips_repositories_missing_it(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    bar = env.workspace / 'bar'
    bar_upstream = env.upstream / 'bar'
    branch = 'release/2.0'

    cmd_git_nested(['clone', bar_upstream.as_posix(), 'bar-lib'], cwd=foo)
    cmd_git_nested(['clone', (env.upstream / 'foo').as_posix(), 'foo-lib'], cwd=foo)

    env.run(['git', 'checkout', '-b', branch], cwd=bar)
    env.add_new_files('release-note', cwd=bar)
    env.run(['git', 'push', '--set-upstream', 'origin', branch], cwd=bar)
    release_commit = git_rev_parse(['HEAD'], cwd=bar)
    foo_lib_fetched = git_rev_parse(['refs/nested/foo-lib/fetch'], cwd=foo)

    result = cmd_git_nested(['fetch', '--all', '-b', branch], cwd=foo)

    assert result.output.strip().splitlines() == [
        f"bar-lib: fetched from {bar_upstream.as_posix()} ({branch})",
        f"foo-lib: skipped, {env.upstream.as_posix()}/foo has no branch {branch}",
    ]
    fetched = git_rev_parse(['refs/nested/bar-lib/fetch'], cwd=foo)
    assert fetched == release_commit
    assert git_rev_parse(['refs/nested/foo-lib/fetch'], cwd=foo) == foo_lib_fetched
