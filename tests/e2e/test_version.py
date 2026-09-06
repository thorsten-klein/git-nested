import sys

from conftest import VERSION, cmd_git_nested

import git_nested


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
    # git_nested.VERSION, not conftest.VERSION: the subprocess runs the module
    # from this interpreter's environment, which is what the import here is
    # too. conftest.VERSION is the version of whatever is under test, and in
    # GIT_NESTED_EXE mode that is the frozen binary -- built from a checkout
    # with tags, while the module here may come from one without.
    result = env.run([sys.executable, '-m', 'git_nested', '--version'], cwd=env.tmp)
    assert f"git-nested Version: {git_nested.VERSION}" in result.stdout
