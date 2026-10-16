"""Tests for git nested run command"""

import subprocess

from conftest import cmd_git_nested, cmd_git_nested_subprocess


def _subject(cwd):
    """Subject line of HEAD in the repository or worktree at `cwd`"""
    return subprocess.run(
        ['git', 'log', '-1', '--format=%s'], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_run_runs_git_in_the_worktree(foo_bar_cloned_and_nested):
    """git sees the worktree, not the parent repository"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/file', cwd=foo)
    cmd_git_nested('branch bar', cwd=foo)
    worktree = foo / '.git' / 'tmp' / 'nested' / 'bar'

    cmd_git_nested(['run', 'bar', 'commit', '--allow-empty', '-m', 'made by run'], cwd=foo)

    assert _subject(worktree) == 'made by run'
    assert _subject(foo) != 'made by run'


def test_run_finds_a_worktree_put_elsewhere(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    wt = env.workspace / 'bar-wt'
    cmd_git_nested(['branch', '-d', wt.as_posix(), 'bar'], cwd=foo)

    cmd_git_nested(['run', 'bar', 'commit', '--allow-empty', '-m', 'made by run'], cwd=foo)

    assert _subject(wt) == 'made by run'


def test_run_passes_git_output_and_exit_code_through(foo_bar_cloned_and_nested):
    """Through a real process, the only way to see what git itself printed"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested('branch bar', cwd=foo)

    result = cmd_git_nested_subprocess(['run', 'bar', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=foo)
    assert result.stdout.strip() == 'nested/bar'

    result = cmd_git_nested_subprocess(['run', 'bar', 'rev-parse', '--verify', 'no-such-rev'], cwd=foo, check=False)
    assert result.returncode == 128


def test_run_without_a_worktree_points_at_branch(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested(['run', 'bar', 'status'], cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert "bar: no worktree of nested/bar to run in; create one with 'git nested branch bar'" in result.output


def test_run_without_a_git_command(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested(['run', 'bar'], cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert "no git command given; e.g. 'git nested run bar log'" in result.output


def test_run_exit_code_becomes_ours(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested('branch bar', cwd=foo)
    # 128 rather than git-nested's own 1: the code is git's, not a translation of it
    result = cmd_git_nested(['run', 'bar', 'rev-parse', '--verify', 'no-such-rev'], cwd=foo, check=False)
    assert result.returncode == 128
