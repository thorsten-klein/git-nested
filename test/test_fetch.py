"""Tests for git nested fetch command"""

from conftest import cmd_git_nested


def test_fetch(foo_bar_cloned_and_nested):
    """Test basic nested fetch functionality"""
    env = foo_bar_cloned_and_nested

    # Add new file with annotated tag to bar and push
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'tag', '-a', 'CoolTag', '-m', 'Should stay in nested'], cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Fetch information
    result = cmd_git_nested('fetch bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Fetched 'bar' from '{env.upstream}/bar' (master)."

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
    assert result.stdout.strip() == "Ignored 'doc', no remote."
    assert result.stderr.strip() == ''
