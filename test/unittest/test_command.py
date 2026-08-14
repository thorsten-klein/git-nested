"""Unit tests for GitNestedCommand's CLI plumbing that don't need a real nested repo"""

from pathlib import Path

import pytest
from git_nested import Flags, GitNestedCommand, GitNestedError


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
    with pytest.raises(SystemExit) as exc_info:
        cmd.parse_args([])
    assert exc_info.value.code == 1


# ============================================================================
# dispatch_command
# ============================================================================


def test_dispatch_command_unknown_command_is_a_usage_error(cmd):
    flags = Flags()
    with pytest.raises(SystemExit) as exc_info:
        cmd.dispatch_command('bogus', flags, None, None, None, None, None)
    assert exc_info.value.code == 1


# ============================================================================
# _handle_push_failure
# ============================================================================


def test_handle_push_failure_rebase_failed_exits(cmd):
    subdir_worktree = Path('/tmp/wt')
    subdir = Path('sub')
    flags = Flags()
    with pytest.raises(SystemExit) as exc_info:
        cmd._handle_push_failure(success=False, subdir_worktree=subdir_worktree, subdir=subdir, flags=flags)
    assert exc_info.value.code == 1


def test_handle_push_failure_nothing_to_push_returns_true(cmd):
    assert cmd._handle_push_failure(success=False, subdir_worktree=None, subdir=Path('sub'), flags=Flags()) is True


def test_handle_push_failure_success_returns_false(cmd):
    assert cmd._handle_push_failure(success=True, subdir_worktree=None, subdir=Path('sub'), flags=Flags()) is False


# ============================================================================
# setup_command
# ============================================================================


def test_setup_command_requires_subdir(cmd):
    flags = Flags()
    with pytest.raises(GitNestedError, match="subdir not set"):
        cmd.setup_command('init', flags, subdir=None, upstream=None)


def test_setup_command_rejects_absolute_subdir(cmd):
    flags = Flags()
    with pytest.raises(SystemExit) as exc_info:
        cmd.setup_command('init', flags, subdir='/absolute/path', upstream=None)
    assert exc_info.value.code == 1


# ============================================================================
# _check_existing_worktree
# ============================================================================


def test_check_existing_worktree_errors_when_commit_has_no_worktree(cmd, monkeypatch):
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '')
    flags = Flags()
    subdir = Path('sub')
    gitnested = Path('sub/.gitnested')
    with pytest.raises(GitNestedError, match="no worktree available"):
        cmd._check_existing_worktree(flags, 'commit', subdir, gitnested)


def test_check_existing_worktree_errors_with_gitnested_present(cmd, monkeypatch, tmp_path):
    gitnested = tmp_path / '.gitnested'
    gitnested.write_text("nested:\n  remote: x\n  branch: y\n")
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '/tmp/wt sha [nested/sub]')
    flags = Flags()
    subdir = Path('sub')
    with pytest.raises(GitNestedError, match="perform a nested clean"):
        cmd._check_existing_worktree(flags, 'pull', subdir, gitnested)


def test_check_existing_worktree_errors_without_gitnested(cmd, monkeypatch, tmp_path):
    gitnested = tmp_path / 'missing' / '.gitnested'
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '/tmp/wt sha [nested/sub]')
    flags = Flags()
    subdir = Path('sub')
    with pytest.raises(GitNestedError, match="git worktree prune"):
        cmd._check_existing_worktree(flags, 'pull', subdir, gitnested)
