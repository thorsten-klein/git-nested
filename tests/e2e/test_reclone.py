"""Tests for git nested reclone"""

import yaml
from conftest import cmd_git_nested


def test_reclone(foo_bar_cloned):
    """Test nested reclone functionality"""
    env = foo_bar_cloned

    # Clone bar
    cp = cmd_git_nested('clone ' + (env.upstream / 'bar').as_posix(), cwd=env.workspace / 'foo')
    assert cp.output.strip() == f"bar: cloned from {env.upstream.as_posix()}/bar (master)"
    assert (env.workspace / 'foo' / 'bar' / 'bard').exists()

    # Test that reclone is not done if not needed
    cp = cmd_git_nested('clone --force ' + (env.upstream / 'bar').as_posix(), cwd=env.workspace / 'foo')
    assert cp.output.strip() == f"bar: already up to date with {env.upstream.as_posix()}/bar (master)"

    # Test that reclone of a different ref works
    cmd_git_nested(f'clone --force {env.upstream.as_posix()}/bar --branch=refs/tags/A', cwd=env.workspace / 'foo')

    # Check that config has correct branch value
    with (env.workspace / 'foo' / 'bar' / '.gitnested').open() as f:
        gitnested = yaml.safe_load(f)
    assert gitnested.get('nested').get('branch') == 'refs/tags/A'

    # Test that reclone back to (implicit) master works
    cp = cmd_git_nested(f'clone -f {env.upstream.as_posix()}/bar', cwd=env.workspace / 'foo')
    assert cp.output.strip() == f"bar: cloned from {env.upstream.as_posix()}/bar (master)"
    assert (env.workspace / 'foo' / 'bar' / 'bard').exists()

    # Check that config has correct branch value
    with (env.workspace / 'foo' / 'bar' / '.gitnested').open() as f:
        gitnested = yaml.safe_load(f)
    assert gitnested.get('nested').get('branch') == 'master'
