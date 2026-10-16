"""Unit tests for git-nested business-logic branches, using FakeGit instead of real git repos"""

from pathlib import Path

import pytest
from fakes import NO_GIT, FakeGit

from git_nested import (
    Flags,
    GitNestedError,
    NestedConfig,
    checks,
    content,
    discovery,
    filters,
    history,
)
from git_nested.commands import fetch, push, status

# ============================================================================
# do_fetch
# ============================================================================


def test_do_fetch_raises_when_remote_is_none():
    config = NestedConfig(remote='none', branch='main')
    with pytest.raises(GitNestedError, match="the remote is 'none'"):
        fetch.do_fetch(git=NO_GIT, config=config, subref='sub')


# ============================================================================
# _recorded_commit
# ============================================================================


def test_recorded_commit_is_none_when_missing():
    git = FakeGit().respond('cat-file', '-p', stdout='')
    assert history._recorded_commit(git, 'deadbeef', Path('sub/.gitnested')) is None


def test_recorded_commit_is_none_on_invalid_yaml():
    git = FakeGit().respond('cat-file', '-p', stdout='nested: [unterminated')
    assert history._recorded_commit(git, 'deadbeef', Path('sub/.gitnested')) is None


def test_recorded_commit_is_none_when_commit_field_empty():
    git = FakeGit().respond('cat-file', '-p', stdout='nested:\n  remote: x\n')
    assert history._recorded_commit(git, 'deadbeef', Path('sub/.gitnested')) is None


def test_recorded_commit_is_stripped():
    git = FakeGit().respond('cat-file', '-p', stdout='nested:\n  commit: deadbeef\n')
    assert history._recorded_commit(git, 'somecommit', Path('sub/.gitnested')) == 'deadbeef'


# ============================================================================
# _fetch_push_target
# ============================================================================


def test_fetch_push_target_is_none_when_the_branch_is_not_upstream_yet():
    # Exit code 2 means "no such ref", in any language.
    git = FakeGit().respond('ls-remote', returncode=2, stderr="fatal: Konnte Remote-Referenz foo nicht finden\n")
    assert push._fetch_push_target(git, Flags(), NestedConfig(remote='x', branch='main'), 'foo') is None


def test_do_push_refuses_a_branch_without_the_upstream_head(monkeypatch):
    monkeypatch.setattr(push, '_fetch_push_target', lambda *_args: 'upstream')
    monkeypatch.setattr(push, '_build_push_branch', lambda *_args: 'nested/sub')
    git = (
        FakeGit()
        .respond('rev-list', 'refs/heads/nested/sub')
        .respond('rev-parse', 'nested/sub', stdout='new')
        .respond('merge-base', '--is-ancestor', returncode=1)
    )
    args = (git, Flags(), NestedConfig(remote='x', branch='main'), Path('sub'), Path('sub/.gitnested'), Path('tmp'))
    with pytest.raises(GitNestedError, match="does not contain the upstream HEAD upstream"):
        push.do_push(*args, 'sub', 'foo', None)


def test_fetch_push_target_raises_on_other_errors():
    git = FakeGit().respond('ls-remote', returncode=128, stderr="fatal: unable to access remote\n")
    flags, config = Flags(), NestedConfig(remote='x', branch='main')
    with pytest.raises(GitNestedError, match="the fetch before the push failed"):
        push._fetch_push_target(git, flags, config, 'foo')


# ============================================================================
# format_refs / _format_ref_line
# ============================================================================


def test_format_refs_empty_when_no_matching_refs():
    git = FakeGit().respond('show-ref', stdout='')
    assert status.format_refs(git, 'sub') == ""


def test_format_refs_formats_known_ref_types():
    show_ref_output = "\n".join([
        "1111111111111111111111111111111111111111 refs/nested/sub/branch",
        "2222222222222222222222222222222222222222 refs/nested/sub/commit",
        "3333333333333333333333333333333333333333 refs/nested/sub/fetch",
        "4444444444444444444444444444444444444444 refs/nested/sub/pull",
        "5555555555555555555555555555555555555555 refs/nested/sub/push",
        "6666666666666666666666666666666666666666 refs/nested/sub/unknown",
        "7777777777777777777777777777777777777777 refs/heads/main",
    ])
    git = (
        FakeGit()
        .respond('show-ref', stdout=show_ref_output)
        .respond('rev-parse', '--short', '1111111111111111111111111111111111111111', stdout='1111111')
        .respond('rev-parse', '--short', '2222222222222222222222222222222222222222', stdout='2222222')
        .respond('rev-parse', '--short', '3333333333333333333333333333333333333333', stdout='3333333')
        .respond('rev-parse', '--short', '4444444444444444444444444444444444444444', stdout='4444444')
        .respond('rev-parse', '--short', '5555555555555555555555555555555555555555', stdout='5555555')
        .respond('rev-parse', '--short', '6666666666666666666666666666666666666666', stdout='6666666')
    )
    output = status.format_refs(git, 'sub')
    assert "Branch Ref" in output
    assert "Commit Ref" in output
    assert "Fetch Ref" in output
    assert "Pull Ref" in output
    assert "Push Ref" in output
    assert "unknown" not in output
    assert "refs/heads/main" not in output


# ============================================================================
# get_status / _status_for_subdir
# ============================================================================


def test_get_status_no_nested_repositories():
    git = FakeGit().respond('ls-files', stdout='')
    assert status.get_status(git, Flags(quiet=False)) == "No nested repositories.\n"


def test_get_status_quiet_has_no_header():
    git = FakeGit().respond('ls-files', stdout='')
    assert status.get_status(git, Flags(quiet=True)) == ""


@pytest.mark.parametrize(
    ('files', 'header'),
    [
        ('a/.gitnested\0', "1 nested repository:\n"),
        ('a/.gitnested\0b/.gitnested\0', "2 nested repositories:\n"),
    ],
)
def test_get_status_header_singular_vs_plural(tmp_path, monkeypatch, files, header):
    monkeypatch.chdir(tmp_path)
    git = FakeGit().respond('ls-files', stdout=files).respond('check-ref-format', returncode=0)
    assert status.get_status(git, Flags()).startswith(header)


def test_status_for_subdir_not_a_nested_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subdir = Path('plainsub')
    subdir.mkdir()
    git = FakeGit().respond('check-ref-format', returncode=0)
    assert status._status_for_subdir(git, Flags(), subdir) == f"'{subdir}' is not a nested repository\n"


def test_status_for_subdir_fetches_when_flag_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subdir = Path('sub')
    subdir.mkdir()
    (subdir / '.gitnested').write_text("nested:\n  remote: https://example.com/x.git\n  branch: main\n")
    git = (
        FakeGit()
        .respond('check-ref-format', returncode=0)
        .respond('rev-parse', '--short', 'refs/nested/sub/fetch', stdout='', returncode=1)
        .respond('fetch', returncode=0)
        .respond('rev-parse', 'FETCH_HEAD^0', stdout='deadbeef')
        .respond('update-ref', returncode=0)
    )
    assert status._status_for_subdir(git, Flags(fetch=True, quiet=True), subdir) == f"{subdir}\n"
    assert ('fetch', '--no-tags', '--quiet', 'https://example.com/x.git', 'main') in git.calls


def test_status_for_subdir_lists_the_refs_when_verbose(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / '.gitnested').write_text("nested:\n  remote: x\n  branch: main\n")
    git = (
        FakeGit()
        .respond('check-ref-format')
        .respond('rev-parse', '--git-dir', '--git-common-dir', stdout='.git\n.git')
        .respond('rev-parse', '--short', 'refs/nested/sub/fetch', returncode=1)
        .respond('rev-parse', '--short', 'abc', stdout='abc')
        .respond('config', returncode=1)
        .respond('rev-list', returncode=1)
        .respond('worktree', 'list', stdout='')
        .respond('show-ref', stdout='abc refs/nested/sub/fetch')
    )
    assert "  Refs:\n    Fetch Ref      abc (refs/nested/sub/fetch)\n" in status._status_for_subdir(
        git, Flags(verbose=1), Path('sub')
    )


def test_status_details_with_branch_and_remote_present():
    git = (
        FakeGit()
        .respond('config', '--get', 'nested.sub.branchname', returncode=1)
        .respond('rev-parse', '--git-dir', '--git-common-dir', stdout='.git\n.git')
        .respond('rev-list', 'refs/heads/nested/sub', returncode=0)
        .respond('config', 'remote.nested/sub.url', stdout='https://example.com/x.git')
        .respond('worktree', 'list', stdout='')
    )
    config = NestedConfig(remote='https://example.com/x.git', branch='main')
    details = status._details(git, Path('sub'), 'sub', config, upstream_head='abc1234')
    assert "Nested Branch:  nested/sub" in details
    assert "Remote Name:     nested/sub" in details


# ============================================================================
# commit_nested_branch
# ============================================================================


def _commit(git):
    content.commit_nested_branch(
        git,
        Flags(),
        NestedConfig(remote='x', branch='main'),
        Path('sub'),
        Path('sub/.gitnested'),
        'deadbeef',
        'upstream',
        'head',
        None,
        'pull',
    )


def test_commit_nested_branch_raises_when_commit_missing():
    git = FakeGit().respond('rev-list', returncode=1)
    with pytest.raises(GitNestedError, match="no such commit"):
        _commit(git)


def test_commit_nested_branch_raises_when_missing_upstream_head():
    git = FakeGit().respond('rev-list', 'deadbeef', returncode=0).respond('merge-base', '--is-ancestor', returncode=1)
    with pytest.raises(GitNestedError, match="does not contain the upstream HEAD"):
        _commit(git)


# ============================================================================
# create_nested_branch (existing-branch shortcut)
# ============================================================================


def test_create_nested_branch_reuses_existing_branch(tmp_path):
    git = FakeGit().respond('rev-list', 'refs/heads/nested/sub', returncode=0).respond('worktree', 'list', stdout='')
    config = NestedConfig(remote='https://example.com/x.git', branch='main')
    worktree = content.create_nested_branch(
        git=git,
        flags=Flags(),
        config=config,
        branch='nested/sub',
        subdir=Path('sub'),
        gitnested=Path('sub/.gitnested'),
        git_tmp=tmp_path,
        subref='sub',
        command='branch',
    )
    assert worktree == tmp_path / 'nested/sub'


# ============================================================================
# _create_branch_from_parent
# ============================================================================


def test_create_branch_from_parent_raises_when_no_commit_touches_subdir():
    git = FakeGit().respond('merge-base', '--is-ancestor', returncode=0).respond('rev-list', '--reverse', stdout='')
    config = NestedConfig(remote='x', branch='main', parent='deadbeef')
    flags = Flags()
    subdir = Path('sub')
    with pytest.raises(GitNestedError, match="no nested history to rebuild"):
        history._create_branch_from_parent(
            git, flags, config, subdir, Path('sub/.gitnested'), 'sub', 'pull', 'nested/sub'
        )


# ============================================================================
# _chain_commits
# ============================================================================


def test_create_chain_commit_skips_a_commit_without_the_subdir():
    git = FakeGit().respond('cat-file', '-e', returncode=1)
    assert history._create_chain_commit(git, 'deadbeef', Path('sub'), 'prev', 'upstream') == 'prev'


def test_chain_commits_skips_a_commit_without_gitnested_data():
    git = FakeGit().respond('cat-file', '-p', stdout='')
    assert history._chain_commits(git, ['deadbeef'], Path('sub/.gitnested')) == []


# ============================================================================
# _check_rebase_safety
# ============================================================================


def test_check_rebase_safety_raises_when_gitrepo_commit_unreachable_locally():
    git = (
        FakeGit()
        .respond('rev-list', 'refs/nested/sub/fetch', returncode=0)
        .respond('merge-base', '--is-ancestor', returncode=1)
        .respond('rev-list', 'deadbeef', returncode=1)
    )
    with pytest.raises(GitNestedError, match="is missing locally"):
        history._check_rebase_safety(git, 'pull', Path('sub'), 'sub', 'deadbeef')


# ============================================================================
# _classify
# ============================================================================


def test_classify_raises_on_invalid_regex():
    git = FakeGit().respond('cat-file', '-t', returncode=1)
    with pytest.raises(GitNestedError, match="invalid filter pattern"):
        filters._classify(git, 'deadbeef', ['['])


# ============================================================================
# check_repository / check_worktree_clean
# ============================================================================


def test_check_repository_raises_on_nested_branch_checked_out():
    git = (
        FakeGit()
        .respond('rev-parse', '--git-dir')
        .respond('rev-parse', '--git-common-dir', stdout='.git')
        .respond('symbolic-ref', stdout='nested/sub')
    )
    with pytest.raises(GitNestedError, match="while the nested branch"):
        checks.check_repository(git, 'pull')


def _clean_up_to_head(**head_responses):
    git = FakeGit().respond('update-index').respond('diff-files', '--quiet', '--ignore-submodules')
    for args, returncode in head_responses.values():
        git.respond(*args, returncode=returncode)
    return git


def test_check_worktree_clean_raises_when_head_unverifiable():
    git = _clean_up_to_head(verify=(('rev-parse', '--verify', 'HEAD'), 1))
    with pytest.raises(GitNestedError, match="HEAD cannot be verified"):
        checks.check_worktree_clean(git, 'pull')


def test_check_worktree_clean_raises_when_index_has_changes():
    git = _clean_up_to_head(
        verify=(('rev-parse', '--verify', 'HEAD'), 0),
        tree=(('diff-index', '--quiet', '--ignore-submodules', 'HEAD'), 0),
        index=(('diff-index', '--quiet', '--cached', '--ignore-submodules', 'HEAD'), 1),
    )
    with pytest.raises(GitNestedError, match="the index has changes"):
        checks.check_worktree_clean(git, 'pull')


def test_check_worktree_clean_raises_on_unstaged_changes():
    git = (
        FakeGit()
        .respond('update-index', returncode=0)
        .respond('diff-files', '--quiet', '--ignore-submodules', returncode=1)
    )
    with pytest.raises(GitNestedError, match="there are unstaged changes"):
        checks.check_worktree_clean(git, 'pull')


# ============================================================================
# get_upstream_branch
# ============================================================================


def test_get_upstream_branch_raises_when_head_ref_not_found():
    git = FakeGit().respond('ls-remote', '--symref', stdout='some unrelated output\n')
    config = NestedConfig(remote='https://example.com/x.git', branch='')
    with pytest.raises(GitNestedError, match="can't determine the default branch"):
        discovery.get_upstream_branch(git, config)
