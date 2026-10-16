"""Unit tests for GitNestedCommand's CLI plumbing that don't need a real nested repo"""

from pathlib import Path

import pytest

from git_nested import Flags, GitNestedCommand, GitNestedError
from git_nested.cli import setup
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


def test_parse_args_push_dry_run_sets_the_flag(cmd):
    _command, ctx = cmd.parse_args(['push', '--dry-run', 'sub'])
    assert ctx.flags.dry_run is True


def test_parse_args_missing_command_is_a_usage_error(cmd):
    with pytest.raises(GitNestedError, match='no command given'):
        cmd.parse_args([])


def test_parse_args_pull_no_squash_sets_the_flag(cmd):
    _, ctx = cmd.parse_args(['pull', '--no-squash', 'sub'])
    assert ctx.flags.no_squash is True


def test_parse_args_rejects_dry_run_with_commit(cmd):
    with pytest.raises(GitNestedError, match="--dry-run can't be combined with --commit"):
        cmd.parse_args(['push', '--dry-run', '--commit', 'sub'])


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
    ctx = CommandContext(git=cmd.git, flags=Flags())
    with pytest.raises(GitNestedError, match='unknown command bogus'):
        cmd.dispatch_command('bogus', ctx)


# ============================================================================
# setup_command
# ============================================================================


def test_setup_command_requires_subdir(cmd):
    flags = Flags()
    with pytest.raises(GitNestedError, match="no subdir given"):
        setup.setup_command(cmd.git, 'init', flags, subdir=None, upstream=None)


def test_setup_command_rejects_absolute_subdir(cmd):
    flags = Flags()
    with pytest.raises(GitNestedError, match='subdir must be a relative path'):
        setup.setup_command(cmd.git, 'init', flags, subdir='/absolute/path', upstream=None)


# ============================================================================
# _check_existing_worktree
# ============================================================================


def test_check_existing_worktree_errors_when_commit_has_no_worktree(cmd, monkeypatch):
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '')
    subdir = Path('sub')
    gitnested = Path('sub/.gitnested')
    with pytest.raises(GitNestedError, match="no worktree to commit from"):
        setup._check_existing_worktree(cmd.git, 'commit', subdir, gitnested, 'nested/sub')


def test_check_existing_worktree_errors_with_gitnested_present(cmd, monkeypatch, tmp_path):
    gitnested = tmp_path / '.gitnested'
    gitnested.write_text("nested:\n  remote: x\n  branch: y\n")
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '/tmp/wt sha [nested/sub]')
    subdir = Path('sub')
    with pytest.raises(GitNestedError, match="git nested clean"):
        setup._check_existing_worktree(cmd.git, 'pull', subdir, gitnested, 'nested/sub')


def test_check_existing_worktree_errors_without_gitnested(cmd, monkeypatch, tmp_path):
    gitnested = tmp_path / 'missing' / '.gitnested'
    monkeypatch.setattr(cmd.git, 'check_output', lambda *a, **k: '/tmp/wt sha [nested/sub]')
    subdir = Path('sub')
    with pytest.raises(GitNestedError, match="git worktree prune"):
        setup._check_existing_worktree(cmd.git, 'pull', subdir, gitnested, 'nested/sub')


@pytest.mark.parametrize(
    ('args', 'method'),
    [
        (['clone', '--rebase', 'https://example.com/lib'], 'rebase'),
        (['clone', '--merge', 'https://example.com/lib'], 'merge'),
        (['pull', '--rebase', 'lib'], 'rebase'),
        (['pull', '--merge', 'lib'], 'merge'),
        (['push', '--rebase', 'lib'], 'rebase'),
        (['push', '--merge', 'lib'], 'merge'),
    ],
)
def test_parse_args_method_shorthand_sets_the_method_flag(cmd, args, method):
    _command, ctx = cmd.parse_args(args)
    assert ctx.flags.method == method
