"""Unit tests for GitNestedCommand's CLI plumbing that don't need a real nested repo"""

from pathlib import Path

import pytest

from git_nested import Flags, GitNestedCommand, GitNestedError
from git_nested.cli import setup
from git_nested.commands import push
from git_nested.models import CommandContext


@pytest.fixture
def cmd():
    return GitNestedCommand()


# ============================================================================
# parse_args
# ============================================================================


def test_parse_args_version_flag_selects_version_command(cmd):
    command, *_ = cmd.parse_args(['--version'])
    assert command == 'version'


def test_parse_args_missing_command_is_a_usage_error(cmd):
    with pytest.raises(GitNestedError, match='no command given'):
        cmd.parse_args([])


# ============================================================================
# main
# ============================================================================


def test_main_answers_a_completion_request_before_the_parser(cmd, capsys):
    """__complete is not a subcommand, so the parser must never see it."""
    cmd.main(['__complete', 'git-nested', 'vers'])
    assert capsys.readouterr().out == 'version\n'


# ============================================================================
# dispatch_command
# ============================================================================


def test_dispatch_command_unknown_command_is_a_usage_error(cmd):
    with pytest.raises(GitNestedError, match='unknown command bogus'):
        cmd.dispatch_command('bogus', CommandContext(git=cmd.git, flags=Flags()))


# ============================================================================
# _handle_push_failure
# ============================================================================


def test_handle_push_failure_rebase_failed_raises():
    subdir_worktree = Path('/tmp/wt')
    subdir = Path('sub')
    with pytest.raises(GitNestedError, match='git rebase failed'):
        push._handle_push_failure(success=False, subdir_worktree=subdir_worktree, subdir=subdir)


def test_handle_push_failure_nothing_to_push_returns_true():
    assert push._handle_push_failure(success=False, subdir_worktree=None, subdir=Path('sub')) is True


def test_handle_push_failure_success_returns_false():
    assert push._handle_push_failure(success=True, subdir_worktree=None, subdir=Path('sub')) is False


# ============================================================================
# setup_command
# ============================================================================


def test_setup_command_requires_subdir(cmd):
    flags = Flags()
    with pytest.raises(GitNestedError, match="no subdir given"):
        cmd.setup_command('init', flags, subdir=None, upstream=None)


def test_setup_command_rejects_absolute_subdir(cmd):
    flags = Flags()
    with pytest.raises(GitNestedError, match='subdir must be a relative path'):
        cmd.setup_command('init', flags, subdir='/absolute/path', upstream=None)


# ============================================================================
# _check_existing_worktree
# ============================================================================


def test_check_existing_worktree_errors_when_commit_has_no_worktree(cmd, monkeypatch):
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '')
    subdir = Path('sub')
    gitnested = Path('sub/.gitnested')
    with pytest.raises(GitNestedError, match="no worktree to commit from"):
        setup._check_existing_worktree(cmd.git, 'commit', subdir, gitnested)


def test_check_existing_worktree_errors_with_gitnested_present(cmd, monkeypatch, tmp_path):
    gitnested = tmp_path / '.gitnested'
    gitnested.write_text("nested:\n  remote: x\n  branch: y\n")
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '/tmp/wt sha [nested/sub]')
    subdir = Path('sub')
    with pytest.raises(GitNestedError, match="git nested clean"):
        setup._check_existing_worktree(cmd.git, 'pull', subdir, gitnested)


def test_check_existing_worktree_errors_without_gitnested(cmd, monkeypatch, tmp_path):
    gitnested = tmp_path / 'missing' / '.gitnested'
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '/tmp/wt sha [nested/sub]')
    subdir = Path('sub')
    with pytest.raises(GitNestedError, match="git worktree prune"):
        setup._check_existing_worktree(cmd.git, 'pull', subdir, gitnested)
