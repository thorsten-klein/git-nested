from conftest import VERSION, cmd_git_nested


def test_version_command(env):
    """Test that version command displays version info"""
    env.clone_init()

    result = cmd_git_nested('version', cwd=env.workspace / 'init')
    assert result.returncode == 0
    assert f'git-nested Version: {VERSION}' in result.stdout
    assert 'Copyright' in result.stdout
    assert 'Git Version:' in result.stdout
    assert result.stderr.strip() == ""
