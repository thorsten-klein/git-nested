"""Unit tests for small, git-repo-independent (or nearly so) git_nested helpers"""

import contextlib
import io
import subprocess
import sys

import git_nested
import pytest
from git_nested import Flags, GitNestedError, GitNestedRepo, GitRunner, NestedConfig

# ============================================================================
# Version detection
# ============================================================================


def test_detect_version_falls_back_when_package_not_installed(monkeypatch):
    """_detect_version() returns the placeholder when the package isn't installed"""

    def raise_not_found(name):
        raise git_nested.PackageNotFoundError(name)

    monkeypatch.setattr(git_nested, "_pkg_version", raise_not_found)
    assert git_nested._detect_version() == "0.99.99"


def test_detect_version_returns_installed_version():
    """_detect_version() returns whatever importlib.metadata reports when installed"""
    assert git_nested._detect_version() == git_nested._pkg_version("git-nested")


# ============================================================================
# NestedConfig.from_file
# ============================================================================


def test_nested_config_from_file_missing_file(tmp_path):
    with pytest.raises(GitNestedError, match=r"No '.*' file"):
        NestedConfig.from_file(tmp_path / "does-not-exist" / ".gitnested")


def test_nested_config_from_file_missing_remote(tmp_path):
    gitnested = tmp_path / ".gitnested"
    gitnested.write_text("nested:\n  branch: main\n")
    with pytest.raises(GitNestedError, match="Missing required 'remote'"):
        NestedConfig.from_file(gitnested)


def test_nested_config_from_file_missing_branch(tmp_path):
    gitnested = tmp_path / ".gitnested"
    gitnested.write_text("nested:\n  remote: https://example.com/repo.git\n")
    with pytest.raises(GitNestedError, match="Missing required 'branch'"):
        NestedConfig.from_file(gitnested)


# ============================================================================
# GitRunner
# ============================================================================


def test_git_runner_raises_when_git_not_on_path(monkeypatch):
    monkeypatch.setattr(git_nested.shutil, "which", lambda name: None)
    with pytest.raises(GitNestedError, match="Can't find 'git' in PATH"):
        GitRunner()


def test_git_runner_raises_when_git_version_too_old(monkeypatch):
    monkeypatch.setattr(GitRunner, "get_version", lambda self: "1.0.0")
    with pytest.raises(GitNestedError, match="Requires git version"):
        GitRunner()


def test_git_runner_squelches_the_filter_branch_warning(monkeypatch):
    """git filter-branch sleeps 10s per call unless this is set -- see _git_env."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs['env'])
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

    runner = object.__new__(GitRunner)
    monkeypatch.setattr(git_nested.subprocess, "run", fake_run)
    runner.run(['status'])
    assert seen['FILTER_BRANCH_SQUELCH_WARNING'] == '1'


def test_git_runner_keeps_a_caller_supplied_env(monkeypatch):
    """A caller passing env= (the GIT_INDEX_FILE paths) must not lose it, or gain os.environ."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs['env'])
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

    runner = object.__new__(GitRunner)
    monkeypatch.setattr(git_nested.subprocess, "run", fake_run)
    runner.run(['status'], env={'GIT_INDEX_FILE': '/tmp/idx'})
    assert seen['GIT_INDEX_FILE'] == '/tmp/idx'
    assert seen['FILTER_BRANCH_SQUELCH_WARNING'] == '1'


def test_git_runner_get_version_raises_when_unparseable(monkeypatch):
    runner = object.__new__(GitRunner)
    monkeypatch.setattr(GitRunner, "check_output", lambda self, args, **kw: "not a version string")
    with pytest.raises(GitNestedError, match="Can't determine git version"):
        runner.get_version()


# ============================================================================
# GitNestedRepo
# ============================================================================


def test_repo_say_prints_when_not_quiet():
    stdout = io.StringIO()
    repo = GitNestedRepo()
    with contextlib.redirect_stdout(stdout):
        repo.say("hello", Flags(quiet=False))
    assert stdout.getvalue().strip() == "hello"


def test_repo_say_silent_when_quiet():
    stdout = io.StringIO()
    repo = GitNestedRepo()
    with contextlib.redirect_stdout(stdout):
        repo.say("hello", Flags(quiet=True))
    assert stdout.getvalue() == ""


def test_extract_level_number_rejects_non_digit_suffix():
    repo = GitNestedRepo()
    assert repo._extract_level_number('nested1/.gitnested.levelX', 'nested1') is None


def test_create_one_level_file_returns_when_source_missing(tmp_path):
    """The recursive level-file writer is a no-op when its source .gitnested is gone"""
    repo = GitNestedRepo()
    result = repo._create_one_level_file(
        git=None,
        flags=Flags(),
        gitnested_path=str(tmp_path / "sub" / ".gitnested"),
        level=2,
        head_commit="deadbeef",
    )
    assert result is None


def test_guess_subdir_raises_without_remote():
    repo = GitNestedRepo()
    with pytest.raises(GitNestedError, match="No remote specified"):
        repo.guess_subdir("")


def test_sanitize_subref_raises_when_unsanitizable(monkeypatch):
    """Force the 'even sanitized, still not a valid ref' guard for an input we can't otherwise construct"""
    repo = GitNestedRepo()
    monkeypatch.setattr(GitNestedRepo, "_is_valid_ref", lambda self, git, ref: False)
    with pytest.raises(GitNestedError, match="Can't determine valid subref"):
        repo.sanitize_subref(git=None, ref="whatever")


def test_get_default_branch_falls_back_to_main(tmp_path, monkeypatch):
    """When init.defaultbranch isn't configured anywhere, fall back to 'main'"""
    empty_home = tmp_path / "home"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_home / ".gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    git = object.__new__(GitRunner)
    repo = GitNestedRepo()
    assert repo.get_default_branch(git) == "main"


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

    monkeypatch.setattr(git_nested, "GitNestedCommand", RaisingCommand)
    with pytest.raises(SystemExit) as exc_info:
        git_nested.main()
    assert exc_info.value.code == 130
