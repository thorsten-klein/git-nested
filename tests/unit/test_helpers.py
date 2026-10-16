"""Unit tests for small, git-repo-independent (or nearly so) git_nested helpers"""

import subprocess
import sys
from pathlib import Path

import pytest
from fakes import NO_GIT, FakeGit

import git_nested
from git_nested import (
    GitNestedError,
    GitRunner,
    NestedConfig,
    _version,
    gitfile,
    refs,
    submodules,
    yamlio,
)
from git_nested import __main__ as dunder_main
from git_nested import git as git_module
from git_nested import worktree as worktree_module
from git_nested.cli import main as cli_main
from git_nested.commands import branch as branch_command

# ============================================================================
# Version detection
# ============================================================================


def test_detect_version_falls_back_when_package_not_installed(monkeypatch):
    """_detect_version() returns the placeholder when the package isn't installed"""

    def raise_not_found(name):
        raise _version.PackageNotFoundError(name)

    monkeypatch.setattr(_version, "_pkg_version", raise_not_found)
    assert _version._detect_version() == "0.99.99"


def test_detect_version_returns_installed_version():
    """_detect_version() returns whatever importlib.metadata reports when installed"""
    assert _version._detect_version() == _version._pkg_version("git-nested")


# ============================================================================
# NestedConfig.from_file
# ============================================================================


def test_nested_config_from_file_missing_file(tmp_path):
    with pytest.raises(GitNestedError, match=r"\.gitnested does not exist"):
        NestedConfig.from_file(tmp_path / "does-not-exist" / ".gitnested")


def test_nested_config_from_file_missing_remote(tmp_path):
    gitnested = tmp_path / ".gitnested"
    gitnested.write_text("nested:\n  branch: main\n")
    with pytest.raises(GitNestedError, match="has no 'remote'"):
        NestedConfig.from_file(gitnested)


def test_nested_config_from_file_missing_branch(tmp_path):
    gitnested = tmp_path / ".gitnested"
    gitnested.write_text("nested:\n  remote: https://example.com/repo.git\n")
    with pytest.raises(GitNestedError, match="has no 'branch'"):
        NestedConfig.from_file(gitnested)


def test_dunder_main_is_wired_to_the_package_entry_point():
    """`python -m git_nested` must reach the same main() the console script does."""
    assert dunder_main.main is git_nested.main


# ============================================================================
# GitRunner
# ============================================================================


def test_git_runner_raises_when_git_not_on_path(monkeypatch):
    monkeypatch.setattr(git_module.shutil, "which", lambda name: None)
    git = GitRunner()
    with pytest.raises(GitNestedError, match="git is not on PATH"):
        git.check()


def test_git_runner_raises_when_git_version_too_old(monkeypatch):
    monkeypatch.setattr(GitRunner, "get_version", lambda self: "1.0.0")
    git = GitRunner()
    with pytest.raises(GitNestedError, match="or newer is required"):
        git.check()


def test_git_runner_squelches_the_filter_branch_warning(monkeypatch):
    """git filter-branch sleeps 10s per call unless this is set -- see GitRunner.run."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs['env'])
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

    runner = object.__new__(GitRunner)
    monkeypatch.setattr(git_module.subprocess, "run", fake_run)
    runner.run(['status'])
    assert seen['FILTER_BRANCH_SQUELCH_WARNING'] == '1'


def test_git_runner_keeps_a_caller_supplied_env(monkeypatch):
    """A caller passing env= (the GIT_INDEX_FILE paths) must not lose it, or gain os.environ."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs['env'])
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

    runner = object.__new__(GitRunner)
    monkeypatch.setattr(git_module.subprocess, "run", fake_run)
    runner.run(['status'], env={'GIT_INDEX_FILE': '/tmp/idx'})
    assert seen['GIT_INDEX_FILE'] == '/tmp/idx'
    assert seen['FILTER_BRANCH_SQUELCH_WARNING'] == '1'


def test_git_runner_get_version_raises_when_unparseable(monkeypatch):
    runner = object.__new__(GitRunner)
    monkeypatch.setattr(GitRunner, "check_output", lambda self, args, **kw: "not a version string")
    with pytest.raises(GitNestedError, match="can't parse the version git reports"):
        runner.get_version()


# ============================================================================
# Business-logic helpers
# ============================================================================


def test_next_level_ignores_a_non_digit_suffix():
    assert gitfile._next_level(Path('nested1'), ['nested1/.gitnested.levelX']) == 2


def test_create_one_level_file_returns_when_source_missing(tmp_path):
    """The recursive level-file writer is a no-op when its source .gitnested is gone"""
    gitfile._create_one_level_file(NO_GIT, tmp_path / "sub" / ".gitnested", level=2)
    assert not (tmp_path / "sub").exists()


def test_guess_subdir_raises_without_remote():
    with pytest.raises(GitNestedError, match="no remote to guess one from"):
        refs.guess_subdir("")


def test_sanitize_subref_raises_when_unsanitizable(monkeypatch):
    """Force the 'even sanitized, still not a valid ref' guard for an input we can't otherwise construct"""
    # Patch the definition in git_nested.refs, not any re-export of it: only
    # the definition is what sanitize_subref's own call resolves through.
    monkeypatch.setattr(refs, "_is_valid_ref", lambda git, ref: False)
    with pytest.raises(GitNestedError, match="can't derive a git ref name"):
        refs.sanitize_subref(git=NO_GIT, ref="whatever")


def test_sanitize_subref_drops_a_trailing_dot():
    """A ref name cannot end with a dot.

    The e2e encoding tests reach this too, but with directory names Windows
    cannot create, so there it is only covered here.
    """
    git = FakeGit().respond('check-ref-format', 'nested/trailing-dots...', returncode=1).respond('check-ref-format')
    assert refs.sanitize_subref(git, 'trailing-dots...') == 'trailing-dots_'


# ============================================================================
# module-level main()
# ============================================================================


def test_main_success_returns_normally(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["git-nested", "--version"])
    git_nested.main()  # does not raise/exit on success
    assert "git-nested Version" in capsys.readouterr().out


def test_main_exits_1_on_git_nested_error(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["git-nested", "status"])
    monkeypatch.chdir(tmp_path)  # not inside a git repository
    with pytest.raises(SystemExit) as exc_info:
        git_nested.main()
    assert exc_info.value.code == 1


def test_main_exits_130_on_keyboard_interrupt(monkeypatch):
    class RaisingCommand:
        def __init__(self):
            pass

        def main(self, args):
            raise KeyboardInterrupt

    # Patch where main() looks the class up, not the git_nested re-export --
    # patching the re-export would succeed and change nothing.
    monkeypatch.setattr(cli_main, "GitNestedCommand", RaisingCommand)
    with pytest.raises(SystemExit) as exc_info:
        git_nested.main()
    assert exc_info.value.code == 130


def test_branch_created_is_none_without_a_reflog():
    git = FakeGit()
    git.respond('reflog', stdout='', returncode=128)
    assert branch_command._created(git, 'nested/foo') is None


def test_branch_exists_error_reports_a_branch_not_built_on_the_recorded_upstream():
    git = FakeGit()
    git.respond('log', '-1', stdout='abc1234 foo: change')
    git.respond('rev-list', 'deadbeefcafe', '-1', stdout='deadbeefcafe')
    git.respond('merge-base', '--is-ancestor', returncode=1)
    git.respond('diff', '--quiet', returncode=1)
    git.respond('reflog', stdout='nested/foo@{2 days ago}')
    git.respond('worktree', 'list', stdout='')
    config = NestedConfig(commit='deadbeefcafe')

    msg = branch_command._branch_exists_error(git, config, 'nested/foo', Path('foo'))

    assert "  upstream:  not based on deadbeefc recorded in .gitnested (outdated)" in msg
    assert "  content:   differs from foo/ in HEAD" in msg
    assert "  branch:    nested/foo" in msg
    assert "  created:   2 days ago" in msg
    assert "worktree:" not in msg


def test_branch_upstream_fact_is_none_without_a_recorded_commit():
    assert branch_command._upstream_fact(NO_GIT, NestedConfig(commit=''), 'nested/foo') is None


def test_branch_content_fact_is_none_when_git_cannot_compare():
    git = FakeGit()
    git.respond('diff', '--quiet', returncode=128)
    assert branch_command._content_fact(git, 'nested/foo', Path('foo')) is None


def test_worktree_paths_outside_the_repository_stay_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / 'elsewhere'
    assert worktree_module._relative(outside) == outside
    assert worktree_module._relative(tmp_path / '.git' / 'tmp') == Path('.git/tmp')


def test_gitnested_is_written_with_lf(tmp_path):
    """No CRLF, also on Windows, so the file is the same on every platform."""
    gitnested = tmp_path / '.gitnested'
    yamlio._write_yaml_config(gitnested, {'nested': {'remote': 'x', 'branch': 'main'}})
    assert b'\r\n' not in gitnested.read_bytes()


@pytest.mark.parametrize(
    ('url', 'base', 'resolved'),
    [
        ('../foo.git', '/srv/git/bar.git', '/srv/git/foo.git'),
        ('./foo.git', '/srv/git/bar.git', '/srv/git/bar.git/foo.git'),
        ('../foo.git', 'https://example.com/group/bar.git', 'https://example.com/group/foo.git'),
        ('https://example.com/x.git', '/srv/git/bar.git', 'https://example.com/x.git'),
    ],
)
def test_a_relative_submodule_url_is_resolved_like_git_does(url, base, resolved):
    assert submodules.resolve(url, base) == resolved
