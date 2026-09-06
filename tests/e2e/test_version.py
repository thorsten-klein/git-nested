import sys

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


def test_python_m_git_nested_runs(env):
    """`python -m git_nested` is a supported entry point alongside the console script."""
    result = env.run([sys.executable, '-m', 'git_nested', '--version'], cwd=env.tmp)
    assert f"git-nested Version: {VERSION}" in result.stdout
