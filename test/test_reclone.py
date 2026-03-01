"""Tests for git nested reclone"""

from conftest import cmd_git_nested
import yaml


def test_reclone(foo_bar_cloned):
    """Test nested reclone functionality"""
    env = foo_bar_cloned

    # Clone bar
    cp = cmd_git_nested('clone ' + str(env.upstream / 'bar'), cwd=env.workspace / 'foo')
    assert cp.stdout.strip() == f"Nested repository '{env.upstream}/bar' (master) cloned into 'bar'."
    assert cp.stderr.strip() == ""
    assert (env.workspace / 'foo' / 'bar' / 'bard').exists()

    # Test that reclone is not done if not needed
    cp = cmd_git_nested('clone --force ' + str(env.upstream / 'bar'), cwd=env.workspace / 'foo')
    assert cp.stdout.strip() == "Nested repository 'bar' is up to date with upstream branch 'master'."

    # Test that reclone of a different ref works
    cmd_git_nested(f'clone --force {env.upstream}/bar --branch=refs/tags/A', cwd=env.workspace / 'foo')

    # Check that config has correct branch value
    with open(env.workspace / 'foo' / 'bar' / '.gitnested') as f:
        gitnested = yaml.safe_load(f)
    assert gitnested.get('nested').get('branch') == 'refs/tags/A'

    # Test that reclone back to (implicit) master works
    cp = cmd_git_nested(f'clone -f {env.upstream}/bar', cwd=env.workspace / 'foo')
    assert cp.stdout.strip() == f"Nested repository '{env.upstream}/bar' (master) cloned into 'bar'."
    assert cp.stderr.strip() == ""
    assert (env.workspace / 'foo' / 'bar' / 'bard').exists()

    # Check that config has correct branch value
    with open(env.workspace / 'foo' / 'bar' / '.gitnested') as f:
        gitnested = yaml.safe_load(f)
    assert gitnested.get('nested').get('branch') == 'master'
