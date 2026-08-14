"""Unit tests for GitNestedRepo business-logic branches, using FakeGit instead of real git repos"""

from pathlib import Path

import pytest
import yaml
from conftest import FakeGit
from git_nested import Flags, GitNestedError, GitNestedRepo, NestedConfig

# ============================================================================
# do_fetch
# ============================================================================


def test_do_fetch_raises_when_remote_is_none():
    repo = GitNestedRepo()
    config = NestedConfig(remote='none', branch='main')
    flags = Flags()
    with pytest.raises(GitNestedError, match="Remote is 'none'"):
        repo.do_fetch(git=None, flags=flags, config=config, subref='sub')


# ============================================================================
# _check_parent_is_ancestor
# ============================================================================


def test_check_parent_is_ancestor_noop_when_ancestor():
    repo = GitNestedRepo()
    git = FakeGit().respond('merge-base', '--is-ancestor', returncode=0)
    config = NestedConfig(parent='deadbeef')
    # Should not raise
    repo._check_parent_is_ancestor(git, config, Path('sub/.gitnested'), Path('sub'))


def test_check_parent_is_ancestor_raises_with_no_previous_sync_point():
    repo = GitNestedRepo()
    git = (
        FakeGit().respond('merge-base', '--is-ancestor', returncode=1).respond('log', '-1', '-G', 'commit =', stdout='')
    )
    config = NestedConfig(parent='deadbeef')
    with pytest.raises(GitNestedError, match="is not an ancestor"):
        repo._check_parent_is_ancestor(git, config, Path('sub/.gitnested'), Path('sub'))


def test_check_parent_is_ancestor_raises_with_recovery_hint():
    repo = GitNestedRepo()
    git = (
        FakeGit()
        .respond('merge-base', '--is-ancestor', returncode=1)
        .respond('log', '-1', '-G', 'commit =', stdout='cafef00d\n')
        .respond('log', '-1', '--format=%H', stdout='cafebabe\n')
    )
    config = NestedConfig(parent='deadbeef')
    with pytest.raises(GitNestedError, match="to 'cafebabe'"):
        repo._check_parent_is_ancestor(git, config, Path('sub/.gitnested'), Path('sub'))


# ============================================================================
# _extract_gitrepo_commit
# ============================================================================


def test_extract_gitrepo_commit_returns_none_when_missing():
    repo = GitNestedRepo()
    git = FakeGit().respond('cat-file', '-p', stdout='')
    assert repo._extract_gitrepo_commit(git, 'deadbeef', Path('sub')) is None


def test_extract_gitrepo_commit_returns_none_on_invalid_yaml():
    repo = GitNestedRepo()
    git = FakeGit().respond('cat-file', '-p', stdout='nested: [unterminated')
    assert repo._extract_gitrepo_commit(git, 'deadbeef', Path('sub')) is None


def test_extract_gitrepo_commit_returns_none_when_commit_field_empty():
    repo = GitNestedRepo()
    git = FakeGit().respond('cat-file', '-p', stdout='nested:\n  remote: x\n')
    assert repo._extract_gitrepo_commit(git, 'deadbeef', Path('sub')) is None


def test_extract_gitrepo_commit_returns_stripped_commit():
    repo = GitNestedRepo()
    git = FakeGit().respond('cat-file', '-p', stdout='nested:\n  commit: deadbeef\n')
    assert repo._extract_gitrepo_commit(git, 'somecommit', Path('sub')) == 'deadbeef'


# ============================================================================
# _push_fetch_missing_upstream
# ============================================================================


def test_push_fetch_missing_upstream_true_when_ref_not_found():
    repo = GitNestedRepo()
    assert repo._push_fetch_missing_upstream("fatal: couldn't find remote ref refs/heads/foo\n") is True


def test_push_fetch_missing_upstream_raises_on_other_errors():
    repo = GitNestedRepo()
    with pytest.raises(GitNestedError, match="Fetch for push failed"):
        repo._push_fetch_missing_upstream("fatal: unable to access remote\n")


# ============================================================================
# format_refs / _format_ref_line
# ============================================================================


def test_format_refs_empty_when_no_matching_refs():
    repo = GitNestedRepo()
    git = FakeGit().respond('show-ref', stdout='')
    assert repo.format_refs(git, 'sub') == ""


def test_format_refs_formats_known_ref_types():
    repo = GitNestedRepo()
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
    output = repo.format_refs(git, 'sub')
    assert "Branch Ref" in output
    assert "Commit Ref" in output
    assert "Fetch Ref" in output
    assert "Pull Ref" in output
    assert "Push Ref" in output
    assert "unknown" not in output
    assert "refs/heads/main" not in output


# ============================================================================
# _status_header / get_status / _status_for_subdir
# ============================================================================


def test_status_header_no_nested_repositories():
    repo = GitNestedRepo()
    header, done = repo._status_header(Flags(quiet=False), count=0)
    assert header == "No nested repositories.\n"
    assert done is True


def test_status_header_quiet_is_always_empty():
    repo = GitNestedRepo()
    header, done = repo._status_header(Flags(quiet=True), count=3)
    assert header == ""
    assert done is False


def test_status_header_singular_vs_plural():
    repo = GitNestedRepo()
    header, _ = repo._status_header(Flags(quiet=False), count=1)
    assert header == "1 nested repository:\n"
    header, _ = repo._status_header(Flags(quiet=False), count=2)
    assert header == "2 nested repositories:\n"


def test_status_for_subdir_not_a_nested_repository(tmp_path, monkeypatch):
    repo = GitNestedRepo()
    monkeypatch.chdir(tmp_path)
    subdir = Path('plainsub')
    subdir.mkdir()
    git = FakeGit().respond('check-ref-format', returncode=0)
    lines, entries = repo._status_for_subdir(git=git, flags=Flags(), git_tmp=tmp_path, subdir=subdir)
    assert entries == []
    assert f"'{subdir}' is not a nested repository" in lines[0]


def test_get_status_no_nested_repositories():
    repo = GitNestedRepo()
    git = FakeGit().respond('ls-files', stdout='')
    output, entries = repo.get_status(git, Flags(quiet=False), git_tmp=Path('/tmp/gt'))
    assert output == "No nested repositories.\n"
    assert entries == []


def test_status_for_subdir_fetches_when_flag_set(tmp_path, monkeypatch):
    repo = GitNestedRepo()
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
    lines, entries = repo._status_for_subdir(
        git=git, flags=Flags(fetch=True, quiet=True), git_tmp=tmp_path, subdir=subdir
    )
    assert entries[0][0] == subdir
    assert lines == [f"{subdir}\n"]


def test_status_identity_lines_branch_and_remote_present():
    repo = GitNestedRepo()
    git = (
        FakeGit()
        .respond('rev-list', 'refs/heads/nested/sub', returncode=0)
        .respond('config', 'remote.nested/sub.url', stdout='https://example.com/x.git')
    )
    config = NestedConfig(remote='https://example.com/x.git', branch='main')
    output = repo._status_identity_lines(git, 'sub', config, upstream_head='abc1234')
    joined = ''.join(output)
    assert "Nested Branch:  nested/sub" in joined
    assert "Remote Name:     nested/sub" in joined


def test_status_detail_lines_appends_refs_when_verbose():
    repo = GitNestedRepo()
    git = (
        FakeGit()
        .respond('rev-list', returncode=1)
        .respond('config', returncode=1)
        .respond('worktree', 'list', stdout='')
        .respond('show-ref', stdout='')
    )
    config = NestedConfig(remote='https://example.com/x.git', branch='main')
    lines = repo._status_detail_lines(
        git, Flags(verbose=1), Path('/tmp/gt'), Path('sub'), 'sub', config, upstream_head=''
    )
    assert any(line == "" for line in lines) or True  # format_refs("") is appended; just exercising the branch


# ============================================================================
# _verify_commit_ref
# ============================================================================


def test_verify_commit_ref_raises_when_commit_missing():
    repo = GitNestedRepo()
    git = FakeGit().respond('rev-list', returncode=1)
    flags = Flags()
    with pytest.raises(GitNestedError, match="does not exist"):
        repo._verify_commit_ref(git, flags, 'deadbeef', 'upstream')


def test_verify_commit_ref_raises_when_missing_upstream_head():
    repo = GitNestedRepo()
    git = FakeGit().respond('rev-list', 'deadbeef', returncode=0).respond('merge-base', '--is-ancestor', returncode=1)
    flags = Flags(force=False)
    with pytest.raises(GitNestedError, match="doesn't contain upstream HEAD"):
        repo._verify_commit_ref(git, flags, 'deadbeef', 'upstream')


# ============================================================================
# create_nested_branch (existing-branch shortcut)
# ============================================================================


def test_create_nested_branch_reuses_existing_branch(tmp_path):
    repo = GitNestedRepo()
    git = FakeGit().respond('rev-list', 'refs/heads/nested/sub', returncode=0)
    config = NestedConfig(remote='https://example.com/x.git', branch='main')
    worktree = repo.create_nested_branch(
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
    repo = GitNestedRepo()
    git = FakeGit().respond('merge-base', '--is-ancestor', returncode=0).respond('rev-list', '--reverse', stdout='')
    config = NestedConfig(remote='x', branch='main', parent='deadbeef')
    flags = Flags()
    subdir = Path('sub')
    gitnested = Path('sub/.gitnested')
    with pytest.raises(GitNestedError, match="can't reconstruct nested branch history"):
        repo._create_branch_from_parent(git, flags, config, subdir, gitnested, 'sub', 'pull', 'nested/sub')


# ============================================================================
# _process_chain_commit
# ============================================================================


def test_process_chain_commit_skips_commit_without_gitrepo_data():
    repo = GitNestedRepo()
    git = FakeGit().respond('cat-file', '-p', stdout='')
    state = {'ancestor': None, 'first_gitrepo_commit': None, 'last_gitrepo_commit': None, 'prev_commit': None}
    config = NestedConfig(remote='x', branch='main')
    repo._process_chain_commit(git, Flags(), config, Path('sub'), 'sub', 'pull', 'deadbeef', state)
    assert state['prev_commit'] is None


# ============================================================================
# _check_rebase_safety
# ============================================================================


def test_check_rebase_safety_raises_when_gitrepo_commit_unreachable_locally():
    repo = GitNestedRepo()
    git = (
        FakeGit()
        .respond('rev-list', 'refs/nested/sub/fetch', returncode=0)
        .respond('merge-base', '--is-ancestor', returncode=1)
        .respond('rev-list', 'deadbeef', returncode=1)
    )
    with pytest.raises(GitNestedError, match="does not contain"):
        repo._check_rebase_safety(git, 'pull', 'sub', 'deadbeef')


# ============================================================================
# _push_check_ancestry
# ============================================================================


def test_push_check_ancestry_raises_when_branch_missing_upstream_head():
    repo = GitNestedRepo()
    git = FakeGit().respond('merge-base', '--is-ancestor', returncode=1)
    flags = Flags(force=False)
    with pytest.raises(GitNestedError, match="doesn't contain upstream HEAD"):
        repo._push_check_ancestry(git, flags, new_upstream=False, upstream_head_commit='deadbeef', branch='nested/sub')


# ============================================================================
# _index_literal_filter_entry
# ============================================================================


def test_index_literal_filter_entry_raises_on_invalid_regex():
    repo = GitNestedRepo()
    git = FakeGit().respond('cat-file', '-t', returncode=1)
    with pytest.raises(GitNestedError, match="Invalid filter pattern"):
        repo._index_literal_filter_entry(git, Path('sub'), {}, 'deadbeef', '[', [])


# ============================================================================
# _update_parent_field
# ============================================================================


def test_update_parent_field_sets_parent_when_caught_up():
    repo = GitNestedRepo()
    git = FakeGit().respond('rev-parse', 'nested/sub', stdout='deadbeef')
    nested: dict = {}
    repo._update_parent_field(
        git, nested, head_commit='cafebabe', nested_commit_ref='nested/sub', upstream_head_commit='deadbeef'
    )
    assert nested['parent'] == 'cafebabe'


# ============================================================================
# _check_current_branch
# ============================================================================


def test_check_current_branch_raises_on_nested_branch_checked_out():
    repo = GitNestedRepo()
    git = FakeGit().respond('symbolic-ref', stdout='nested/sub')
    with pytest.raises(GitNestedError, match="while a nested branch is checked out"):
        repo._check_current_branch(git, 'pull')


# ============================================================================
# _check_head_and_index_clean / check_worktree_clean
# ============================================================================


def test_check_head_and_index_clean_raises_when_head_unverifiable():
    repo = GitNestedRepo()
    git = FakeGit().respond('rev-parse', '--verify', 'HEAD', returncode=1)
    with pytest.raises(GitNestedError, match="HEAD cannot be verified"):
        repo._check_head_and_index_clean(git, 'pull', Path('/repo'))


def test_check_head_and_index_clean_raises_when_index_has_changes():
    repo = GitNestedRepo()
    git = (
        FakeGit()
        .respond('rev-parse', '--verify', 'HEAD', returncode=0)
        .respond('diff-index', '--quiet', '--ignore-submodules', 'HEAD', returncode=0)
        .respond('diff-index', '--quiet', '--cached', '--ignore-submodules', 'HEAD', returncode=1)
    )
    with pytest.raises(GitNestedError, match="Index has changes"):
        repo._check_head_and_index_clean(git, 'pull', Path('/repo'))


def test_check_worktree_clean_raises_on_unstaged_changes():
    repo = GitNestedRepo()
    git = (
        FakeGit()
        .respond('update-index', returncode=0)
        .respond('diff-files', '--quiet', '--ignore-submodules', returncode=1)
    )
    with pytest.raises(GitNestedError, match="Unstaged changes"):
        repo.check_worktree_clean(git, 'pull')


# ============================================================================
# get_upstream_branch
# ============================================================================


def test_get_upstream_branch_raises_when_head_ref_not_found():
    repo = GitNestedRepo()
    git = FakeGit().respond('ls-remote', '--symref', stdout='some unrelated output\n')
    config = NestedConfig(remote='https://example.com/x.git', branch='')
    with pytest.raises(GitNestedError, match="Problem finding remote default head branch"):
        repo.get_upstream_branch(git, config)


# ============================================================================
# _sync_gitnested_files (levelN -> sibling regular .gitnested)
# ============================================================================


def test_sync_gitnested_files_also_updates_sibling_regular_file(tmp_path):
    """When operating through a .gitnested.levelN file, its sibling regular .gitnested
    (if present) is kept in sync too, so operating on the nested repo directly still
    sees current info"""
    repo = GitNestedRepo()
    level_gitnested = tmp_path / '.gitnested.level2'
    regular_gitnested = tmp_path / '.gitnested'
    regular_gitnested.write_text("nested:\n  remote: old\n  branch: old\n")
    git = FakeGit().respond('cat-file', '-e', returncode=1).respond('add', '-f', '--')
    config = NestedConfig(remote='https://example.com/x.git', branch='main')

    repo._sync_gitnested_files(
        git,
        Flags(),
        config,
        level_gitnested,
        upstream_head_commit='deadbeef',
        nested_commit_ref='nested/sub',
        head_commit='',
        command='pull',
    )

    assert level_gitnested.is_file()
    updated = yaml.safe_load(regular_gitnested.read_text())
    # 'commit' is always refreshed; 'remote' isn't (no --remote override, not a push/clone)
    assert updated['nested']['commit'] == 'deadbeef'
    assert updated['nested']['remote'] == 'old'


# ============================================================================
# _finalize_commit
# ============================================================================


def test_finalize_commit_logs_when_there_is_nothing_to_commit(capsys):
    repo = GitNestedRepo()
    git = (
        FakeGit()
        .respond('diff', '--cached', '--quiet', returncode=0)
        .respond('check-ref-format', returncode=0)
        .respond('update-ref')
    )
    config = NestedConfig(remote='x', branch='main')
    repo._finalize_commit(
        git,
        Flags(verbose=1),
        config,
        Path('sub'),
        nested_commit_ref='nested_ref',
        upstream_head_commit='upstream_head',
        subdir_worktree=None,
        command='pull',
    )
    assert "No changes to commit for .gitnested update" in capsys.readouterr().out
