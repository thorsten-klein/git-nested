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


def _branch_dev_like_master(env):
    """Create 'dev' upstream, on the very commit 'master' is on."""
    env.run(['git', 'push', 'origin', 'master:dev'], cwd=env.workspace / 'bar')


def _recorded_branch(env):
    return yaml.safe_load((env.workspace / 'foo' / 'bar' / '.gitnested').read_text())['nested']['branch']


def test_clone_force_switches_to_a_branch_on_the_same_commit(foo_bar_cloned_and_nested):
    """The branch to track changes even when the content does not."""
    env = foo_bar_cloned_and_nested
    _branch_dev_like_master(env)

    cp = cmd_git_nested(f'clone -f -b dev {env.upstream.as_posix()}/bar', cwd=env.workspace / 'foo')

    assert cp.output.strip() == f"bar: cloned from {env.upstream.as_posix()}/bar (dev)"
    assert _recorded_branch(env) == 'dev'


def test_pull_force_switches_to_a_branch_on_the_same_commit(foo_bar_cloned_and_nested):
    """`pull -f -b` records the new branch, and commits that, with the content unchanged."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _branch_dev_like_master(env)
    head = env.run(['git', 'rev-parse', 'HEAD'], cwd=foo).output.strip()

    cmd_git_nested('pull -f -b dev bar', cwd=foo)

    assert _recorded_branch(env) == 'dev'
    assert env.run(['git', 'rev-parse', 'HEAD^'], cwd=foo).output.strip() == head
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).output == ''


def test_pull_force_switches_to_a_remote_on_the_same_commit(foo_bar_cloned_and_nested):
    """A mirror of the upstream is another remote to record, though nothing else changes."""
    env = foo_bar_cloned_and_nested
    mirror = (env.upstream / 'bar-mirror').as_posix()
    env.run(['git', 'clone', '--quiet', '--bare', (env.upstream / 'bar').as_posix(), mirror])

    cmd_git_nested(['pull', '-f', '-r', mirror, 'bar'], cwd=env.workspace / 'foo')

    gitnested = yaml.safe_load((env.workspace / 'foo' / 'bar' / '.gitnested').read_text())['nested']
    assert gitnested['remote'] == mirror
