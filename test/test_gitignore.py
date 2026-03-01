"""Tests for git nested with .gitignore"""

from conftest import assert_gitnested_field, git_rev_parse, cmd_git_nested


def test_gitignore(foo_bar_cloned_and_nested):
    """Test nested pull with .gitignore"""
    env = foo_bar_cloned_and_nested

    # Add new file to bar and push
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Add .gitignore to foo
    gitignore_path = env.workspace / 'foo' / '.gitignore'
    gitignore_path.write_text('.*\n')
    env.run(['git', 'add', '--force', '.gitignore'], cwd=env.workspace / 'foo')
    env.run(['git', 'commit', '-m', 'Ignore all files in gitignore'], cwd=env.workspace / 'foo')
    env.run(['git', 'push'], cwd=env.workspace / 'foo')

    # Pull nested repository "bar"
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."

    # Ensure nested repository files are present
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'
    assert gitnested.is_file()
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').is_file()

    # Test foo/bar/.gitnested file contents
    previous_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')

    assert_gitnested_field(
        gitnested,
        remote=str(env.upstream / 'bar'),
        branch='master',
        commit=bar_head_commit,
        parent=previous_commit,
        method='merge',
    )
