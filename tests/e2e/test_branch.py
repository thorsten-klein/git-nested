"""Tests for git nested branch command"""

import subprocess

from conftest import (
    assert_commit,
    assert_commit_count,
    cmd_git_nested,
    git_get_commit_msg,
    git_read_head,
    git_rev_parse,
    update_env,
)

# A commit date comfortably after anything the fixtures create. Used where a
# test needs two git operations to land at distinguishable times -- git takes
# both dates from the environment, so this replaces a real sleep with an
# instant, deterministic jump.
_LATER_COMMIT_DATE = {
    'GIT_AUTHOR_DATE': '2030-01-01T00:00:00+00:00',
    'GIT_COMMITTER_DATE': '2030-01-01T00:00:00+00:00',
}


def test_branch(foo_bar_cloned_and_nested):
    """Test basic nested branch functionality"""
    env = foo_bar_cloned_and_nested

    assert_commit_count(env.workspace / 'foo', 2)
    assert_commit_count(env.workspace / 'bar', 2)

    # Get timestamp before
    before = (env.workspace / 'foo' / 'Foo').stat().st_mtime

    # Make changes
    env.add_new_files('bar/file', cwd=env.workspace / 'foo')
    env.add_new_files('.gitnested', cwd=env.workspace / 'foo')

    assert_commit_count(env.workspace / 'foo', 4)
    assert_commit(
        env.workspace / 'foo',
        'HEAD',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        changed_files=['.gitnested'],
    )

    assert_commit(
        env.workspace / 'foo',
        'HEAD~1',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        changed_files=['bar/file'],
    )

    # Save original state
    original_head_ref = (env.workspace / 'foo' / '.git' / 'HEAD').read_text().strip()
    original_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'foo')
    original_gitnested = (env.workspace / 'foo' / 'bar' / '.gitnested').read_text()

    # Make sure that time stamps differ. A fixed later date rather than a real
    # sleep: git reads these from the environment, so the clock never has to
    # actually advance for the commits to land at a distinct time.
    with update_env(_LATER_COMMIT_DATE):
        result = cmd_git_nested('branch bar', cwd=env.workspace / 'foo')
    assert result.output.strip() == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"

    # Check temporary directory exists
    tmp_worktree = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    assert tmp_worktree.exists()

    # Check that correct branch is checked out in the tmp worktree
    result = env.run(['git', 'branch'], cwd=tmp_worktree)
    current_branch = next(line for line in result.stdout.split('\n') if line.startswith('*'))
    assert current_branch.strip() == '* nested/bar'

    # Check that branch commits are correct
    assert_commit_count(tmp_worktree, 3)
    assert_commit(
        tmp_worktree,
        'HEAD',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        changed_files=['file'],
    )

    # Assert that original workspace remains untouched (HEAD is same and no changes in .gitnested file)
    assert (env.workspace / 'foo' / 'Foo').stat().st_mtime == before
    current_head_ref = git_read_head(env.workspace / 'foo')
    current_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'foo')
    current_gitnested = (env.workspace / 'foo' / 'bar' / '.gitnested').read_text()
    assert current_head_ref == original_head_ref
    assert current_head_commit == original_head_commit
    assert current_gitnested == original_gitnested


def test_branch_all(foo_bar_cloned):
    """Test commands work using --all flag"""
    env = foo_bar_cloned

    # Clone two nesteds
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix(), 'one'], cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'one').exists()
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix(), 'two'], cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'two').exists()
    env.add_new_files('two/file', cwd=env.workspace / 'foo')

    # Branch all (should work even when a nested has no new commits)
    result = cmd_git_nested(['branch', '--all'], cwd=env.workspace / 'foo')
    assert result.returncode == 0

    # Check that nested/one branch and worktree exist
    result = env.run(['git', 'branch', '--list', 'nested/one'], cwd=env.workspace / 'foo')
    assert result.stdout.strip() != ''
    one_worktree = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'two'
    assert (one_worktree).exists()
    assert_commit_count(one_worktree, 3)
    assert_commit(
        one_worktree,
        'HEAD',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        changed_files=['file'],
    )

    # Check that nested/two branch and worktree exist
    result = env.run(['git', 'branch', '--list', 'nested/two'], cwd=env.workspace / 'foo')
    assert result.stdout.strip() != ''
    two_worktree = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'two'
    assert (two_worktree).exists()
    assert_commit_count(two_worktree, 3)
    assert_commit(
        two_worktree,
        'HEAD',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        changed_files=['file'],
    )


def test_branch_rev_list(foo_bar_cloned_and_nested):
    """Test that commits with changes in a nested repository are correctly present when a nested branch is created"""
    env = foo_bar_cloned_and_nested

    # Create a complex merge scenario
    branchpoint = git_rev_parse(['HEAD'], cwd=env.workspace / 'foo')

    env.add_new_files('bar/file1', cwd=env.workspace / 'foo')

    # Push here to force nested repository to handle histories where it's not first parent
    cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')

    env.add_new_files('bar/file2', cwd=env.workspace / 'foo')

    env.run(['git', 'checkout', '-b', 'other', branchpoint], cwd=env.workspace / 'foo')
    env.add_new_files('bar/file3', cwd=env.workspace / 'foo')
    env.add_new_files('bar/file4', cwd=env.workspace / 'foo')
    env.add_new_files('bar/file5', cwd=env.workspace / 'foo')

    env.run(['git', 'merge', 'master'], cwd=env.workspace / 'foo')

    # Check files exist
    assert_commit_count(env.workspace / 'foo', 9)  # 7 more commits
    assert (env.workspace / 'foo' / 'bar' / 'file1').exists()
    assert (env.workspace / 'foo' / 'bar' / 'file2').exists()
    assert (env.workspace / 'foo' / 'bar' / 'file3').exists()
    assert (env.workspace / 'foo' / 'bar' / 'file4').exists()
    assert (env.workspace / 'foo' / 'bar' / 'file5').exists()

    # create nested branch to fetch new information
    result = cmd_git_nested('branch bar', cwd=env.workspace / 'foo')
    assert result.output.strip() == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"

    # assert branch is correctly created
    tmp_worktree = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    assert (tmp_worktree).exists()
    assert_commit_count(tmp_worktree, 5)
    assert_commit(
        cwd=tmp_worktree,
        ref='HEAD',
        commit_title="Merge branch 'master' into other",
        changed_files=['file3', 'file4', 'file5'],
    )
    assert_commit(tmp_worktree, 'HEAD~1', changed_files=['file2'])
    assert_commit(tmp_worktree, 'HEAD~2', changed_files=['file1'])


def test_branch_rev_list_one_path(foo_bar_cloned_and_nested):
    """Test branch command with merge history using one path"""
    env = foo_bar_cloned_and_nested
    assert_commit_count(env.workspace / 'foo', 2)

    # Create a merge scenario
    branchpoint = git_rev_parse(['HEAD'], cwd=env.workspace / 'foo')

    env.add_new_files('bar/file1', cwd=env.workspace / 'foo')
    env.add_new_files('bar/file2', cwd=env.workspace / 'foo')
    assert_commit_count(env.workspace / 'foo', 4)

    env.run(['git', 'checkout', '-b', 'other', branchpoint], cwd=env.workspace / 'foo')
    assert_commit_count(env.workspace / 'foo', 2)

    env.add_new_files('bar/file3', cwd=env.workspace / 'foo')
    env.add_new_files('bar/file4', cwd=env.workspace / 'foo')
    env.add_new_files('bar/file5', cwd=env.workspace / 'foo')
    assert_commit_count(env.workspace / 'foo', 5)

    env.run(['git', 'merge', 'master'], cwd=env.workspace / 'foo')
    assert_commit_count(env.workspace / 'foo', 8)  # 2 commits from master + 1 merge commit

    # Check files exist
    assert (env.workspace / 'foo' / 'bar' / 'file1').exists()
    assert (env.workspace / 'foo' / 'bar' / 'file2').exists()
    assert (env.workspace / 'foo' / 'bar' / 'file3').exists()
    assert (env.workspace / 'foo' / 'bar' / 'file4').exists()
    assert (env.workspace / 'foo' / 'bar' / 'file5').exists()

    # Branch
    result = cmd_git_nested('branch bar', cwd=env.workspace / 'foo')
    assert result.output.strip() == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"

    # Count commits
    assert_commit_count(env.workspace / 'foo', 8)  # no commit is added

    # assert branch is correctly created
    tmp_worktree = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    assert (tmp_worktree).exists()
    # The merged commits keep their own commits; the merge stays a merge.
    assert_commit_count(tmp_worktree, 8)
    assert_commit(cwd=tmp_worktree, ref='HEAD', commit_title="Merge branch 'master' into other")
    merged = env.run(['git', 'diff', '--name-only', 'HEAD^', 'HEAD'], cwd=tmp_worktree).output.split()
    assert merged == ['file1', 'file2']
    assert_commit(tmp_worktree, 'HEAD~1', changed_files=['file5'])
    assert_commit(tmp_worktree, 'HEAD~2', changed_files=['file4'])
    assert_commit(tmp_worktree, 'HEAD~3', changed_files=['file3'])
    assert_commit(tmp_worktree, 'HEAD^2', changed_files=['file2'])
    assert_commit(tmp_worktree, 'HEAD^2~1', changed_files=['file1'])


def test_branch_with_force(foo_bar_cloned_and_nested):
    """Test branch command with --force flag to recreate existing branch"""
    env = foo_bar_cloned_and_nested

    # Make changes
    env.add_new_files('bar/file1', cwd=env.workspace / 'foo')

    # Create branch
    result = cmd_git_nested('branch bar', cwd=env.workspace / 'foo')
    assert result.output.strip() == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"

    # assert branch is correctly created
    tmp_worktree = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    assert (tmp_worktree).exists()
    assert_commit_count(tmp_worktree, 3)
    assert_commit(tmp_worktree, 'HEAD', changed_files=['file1'])

    # store the branch commit
    branch_commits_1 = git_get_commit_msg(tmp_worktree, args=['--pretty=format:"%h %s"']).strip().splitlines()

    # Make more changes and create branch again after cleanup
    cmd_git_nested('clean bar', cwd=env.workspace / 'foo')
    env.add_new_files('bar/file2', cwd=env.workspace / 'foo')
    result = cmd_git_nested('branch bar', cwd=env.workspace / 'foo')

    # Make more changes and create branch again
    env.add_new_files('bar/file3', cwd=env.workspace / 'foo')

    # create nested branch
    result = cmd_git_nested('branch bar', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert "bar: branch nested/bar already exists" in result.output
    # bar/file3 came after the branch, so the branch no longer matches bar/
    assert "  content:   differs from bar/ in HEAD" in result.output
    assert "  created:   " in result.output

    # Create branch with --force
    result = cmd_git_nested('branch bar --force', cwd=env.workspace / 'foo')
    assert result.output.strip() == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"

    # Rebuild at a different timestamp. That is the whole point of the
    # assertion below: the rebuilt commits keep their hashes because they
    # take their dates from the source commits, not from 'now'.
    with update_env(_LATER_COMMIT_DATE):
        result = cmd_git_nested('branch bar --force', cwd=env.workspace / 'foo')
    assert result.output.strip() == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"

    branch_commits_2 = git_get_commit_msg(tmp_worktree, args=['--pretty=format:"%h %s"']).strip().splitlines()
    assert branch_commits_2[2:] == branch_commits_1


def test_branch_fetch_flag_refreshes_upstream_ref_first(foo_bar_cloned_and_nested):
    """Test that `branch --fetch` refreshes the upstream ref before building the branch"""
    env = foo_bar_cloned_and_nested

    result = cmd_git_nested('branch bar --fetch', cwd=env.workspace / 'foo')
    assert result.output.strip() == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"


def test_branch_dir_puts_the_worktree_there(foo_bar_cloned_and_nested):
    """`branch -d` checks the branch out where it is told, and the other commands find it there"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/file', cwd=foo)
    wt = env.workspace / 'bar-wt'

    result = cmd_git_nested(['branch', '-d', wt.as_posix(), 'bar'], cwd=foo)
    assert result.output.strip() == f"bar: branch nested/bar created, worktree at {wt.as_posix()}"
    assert (wt / 'file').is_file()
    assert not (foo / '.git' / 'tmp' / 'nested' / 'bar').exists()

    assert f"Worktree: {wt.as_posix()}" in cmd_git_nested('status', cwd=foo).output

    # an existing branch elsewhere is still reported, with where it is checked out
    result = cmd_git_nested('branch bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert f"  worktree:  {wt.as_posix()}" in result.output

    cmd_git_nested('clean bar', cwd=foo)
    assert not wt.exists()


def test_branch_dir_rebuilds_the_same_nested_in_place(foo_bar_cloned_and_nested):
    """Pointing -d at the worktree of the same nested rebuilds the branch there, without --force"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/file1', cwd=foo)
    wt = env.workspace / 'bar-wt'
    cmd_git_nested(['branch', '-d', wt.as_posix(), 'bar'], cwd=foo)

    env.add_new_files('bar/file2', cwd=foo)
    result = cmd_git_nested(['branch', '-d', wt.as_posix(), 'bar'], cwd=foo)
    assert result.output.strip() == f"bar: branch nested/bar created, worktree at {wt.as_posix()}"
    assert (wt / 'file2').is_file()


def test_branch_dir_refuses_the_worktree_of_another_nested(foo_bar_cloned):
    """-d never takes over a worktree of another nested repository, not even with --force"""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix(), 'one'], cwd=foo)
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix(), 'two'], cwd=foo)
    wt = env.workspace / 'wt'
    cmd_git_nested(['branch', '-d', wt.as_posix(), 'one'], cwd=foo)

    for args in (['branch', '-d', wt.as_posix(), 'two'], ['branch', '--force', '-d', wt.as_posix(), 'two']):
        result = cmd_git_nested(args, cwd=foo, check=False)
        assert result.returncode == 1
        assert f"{wt.as_posix()}: already a worktree, of branch nested/one -- not of two" in result.output
    assert env.run(['git', 'branch', '--list', 'nested/two'], cwd=foo).stdout.strip() == ''


def test_branch_dir_refuses_a_directory_with_files(foo_bar_cloned_and_nested):
    """A directory that is not a worktree is only used when it is empty"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    occupied = env.workspace / 'occupied'
    occupied.mkdir()
    (occupied / 'keep').write_text('mine')

    result = cmd_git_nested(['branch', '-d', occupied.as_posix(), 'bar'], cwd=foo, check=False)
    assert result.returncode == 1
    assert f"{occupied.as_posix()}: already exists and is not a worktree of bar" in result.output
    assert (occupied / 'keep').read_text() == 'mine'

    empty = env.workspace / 'empty'
    empty.mkdir()
    cmd_git_nested(['branch', '-d', empty.as_posix(), 'bar'], cwd=foo)
    assert (empty / '.git').exists()


def test_branch_dir_and_all_are_exclusive(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested(['branch', '--all', '-d', 'x'], cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert "--dir names one worktree, so it can't be used with --all" in result.output


def _git(args, cwd):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=False)


def test_branch_name_is_used_and_remembered(foo_bar_cloned_and_nested):
    """--name builds that branch, and the other commands follow it until clean"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/file', cwd=foo)

    result = cmd_git_nested('branch --name bar-fixes bar', cwd=foo)
    assert result.output.strip() == "bar: branch bar-fixes created, worktree at .git/tmp/bar-fixes"
    assert _git(['config', 'nested.bar.branchname'], foo).stdout.strip() == 'bar-fixes'
    assert _git(['branch', '--list', 'nested/bar'], foo).stdout.strip() == ''

    status = cmd_git_nested('status', cwd=foo).output
    assert "Nested Branch:  bar-fixes" in status
    assert "[bar-fixes]" in status

    # without --name again, the remembered branch is the one that already exists
    result = cmd_git_nested('branch bar', cwd=foo, check=False)
    assert "bar: branch bar-fixes already exists" in result.output

    cmd_git_nested(['run', 'bar', 'commit', '--allow-empty', '-m', 'in bar-fixes'], cwd=foo)
    assert _git(['log', '-1', '--format=%s', 'bar-fixes'], foo).stdout.strip() == 'in bar-fixes'

    assert "removed branch 'bar-fixes'" in cmd_git_nested('clean bar', cwd=foo).output
    assert _git(['config', 'nested.bar.branchname'], foo).returncode == 1
    assert cmd_git_nested('branch bar', cwd=foo).output.strip().startswith("bar: branch nested/bar created")


def test_branch_name_replaces_the_previous_branch_with_force(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested('branch bar', cwd=foo)

    result = cmd_git_nested('branch --name other bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: branch nested/bar already exists" in result.output

    cmd_git_nested('branch --force --name other bar', cwd=foo)
    assert _git(['branch', '--list', 'nested/bar'], foo).stdout.strip() == ''
    assert _git(['config', 'nested.bar.branchname'], foo).stdout.strip() == 'other'

    # back to the default name forgets the record
    cmd_git_nested('branch --force --name nested/bar bar', cwd=foo)
    assert _git(['config', 'nested.bar.branchname'], foo).returncode == 1
    assert _git(['branch', '--list', 'other'], foo).stdout.strip() == ''


def test_branch_name_never_takes_over_a_foreign_branch(foo_bar_cloned_and_nested):
    """Not even with --force: the branch would be one of the user's own"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _git(['branch', 'mine'], foo)
    mine = _git(['rev-parse', 'mine'], foo).stdout

    for args in ('branch --name mine bar', 'branch --force --name mine bar'):
        result = cmd_git_nested(args, cwd=foo, check=False)
        assert result.returncode == 1
        assert "branch mine already exists and is not the nested branch of bar" in result.output
    assert _git(['rev-parse', 'mine'], foo).stdout == mine


def test_branch_name_must_be_valid(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested(['branch', '--name', 'a..b', 'bar'], cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert "a..b: not a valid branch name" in result.output


def test_branch_name_and_all_are_exclusive(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested(['branch', '--all', '--name', 'x'], cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert "--name names one branch, so it can't be used with --all" in result.output


def test_a_branch_named_nested_is_reported(foo_bar_cloned_and_nested):
    """A branch 'nested' blocks every nested/<subdir> branch; say so, and how to get past it."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.run(['git', 'branch', 'nested'], cwd=foo)

    result = cmd_git_nested('branch bar', cwd=foo, check=False)

    assert result.returncode == 1
    assert result.output.strip() == (
        "git-nested: bar: the branch nested is in the way of nested/bar; "
        "rename it, or pick another name with 'git nested branch --name <name> bar'"
    )


def test_name_gets_past_a_branch_named_nested(foo_bar_cloned_and_nested):
    """With --name the nested branch lives elsewhere, and push uses it too."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.run(['git', 'branch', 'nested'], cwd=foo)
    env.add_new_files('bar/from-foo', cwd=foo)

    cmd_git_nested('branch --name bar-fixes bar', cwd=foo)
    cmd_git_nested('push bar', cwd=foo)

    env.run(['git', 'cat-file', '-e', 'foo-master:from-foo'], cwd=env.upstream / 'bar')


def test_worktrees_of_the_parent_do_not_block_each_other(foo_bar_cloned_and_nested):
    """Each worktree of the parent repository has its own nested branch and worktree."""
    env = foo_bar_cloned_and_nested
    foo, wt = env.workspace / 'foo', env.workspace / 'wt'
    env.run(['git', 'worktree', 'add', '-q', '-b', 'other', wt.as_posix()], cwd=foo)

    cmd_git_nested('branch bar', cwd=foo)
    result = cmd_git_nested('branch bar', cwd=wt)

    assert result.output.strip().startswith("bar: branch nested/bar@wt created, worktree at ")
    assert (foo / '.git' / 'worktrees' / 'wt' / 'tmp' / 'nested' / 'bar@wt').is_dir()
    cmd_git_nested('clean --force --all', cwd=wt)
    branches = env.run(['git', 'branch', '--list', 'nested/*', '--format=%(refname:short)'], cwd=foo).output.split()
    assert branches == ['nested/bar']


def test_clean_all_in_the_main_worktree_keeps_the_branches_of_others(foo_bar_cloned_and_nested):
    """clean --force --all only sweeps the nested branches of its own worktree."""
    env = foo_bar_cloned_and_nested
    foo, wt = env.workspace / 'foo', env.workspace / 'wt'
    env.run(['git', 'worktree', 'add', '-q', '-b', 'other', wt.as_posix()], cwd=foo)
    cmd_git_nested('branch bar', cwd=wt)

    cmd_git_nested('clean --force --all', cwd=foo)

    branches = env.run(['git', 'branch', '--list', 'nested/*', '--format=%(refname:short)'], cwd=foo).output.split()
    assert branches == ['nested/bar@wt']
