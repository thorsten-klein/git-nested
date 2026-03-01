"""Tests for git nested branch command"""

import time
from conftest import (
    assert_commit,
    assert_commit_count,
    cmd_git_nested,
    git_get_commit_msg,
    git_rev_parse,
    git_read_head,
)


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

    # Make sure that time stamps differ
    time.sleep(1)

    result = cmd_git_nested('branch bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Created branch 'nested/bar' and worktree '.git/tmp/nested/bar'."

    # Check temporary directory exists
    tmp_worktree = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    assert tmp_worktree.exists()

    # Check that correct branch is checked out in the tmp worktree
    result = env.run(['git', 'branch'], cwd=tmp_worktree)
    current_branch = [line for line in result.stdout.split('\n') if line.startswith('*')][0]
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
    cmd_git_nested(['clone', str(env.upstream / 'bar'), 'one'], cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'one').exists()
    cmd_git_nested(['clone', str(env.upstream / 'bar'), 'two'], cwd=env.workspace / 'foo')
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
    assert result.stdout.strip() == "Created branch 'nested/bar' and worktree '.git/tmp/nested/bar'."

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
    assert result.stdout.strip() == "Created branch 'nested/bar' and worktree '.git/tmp/nested/bar'."

    # Count commits
    assert_commit_count(env.workspace / 'foo', 8)  # no commit is added

    # assert branch is correctly created
    tmp_worktree = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    assert (tmp_worktree).exists()
    assert_commit_count(tmp_worktree, 6)
    assert_commit(
        cwd=tmp_worktree,
        ref='HEAD',
        commit_title="Merge branch 'master' into other",
        changed_files=['file1', 'file2'],
    )
    assert_commit(tmp_worktree, 'HEAD~1', changed_files=['file5'])
    assert_commit(tmp_worktree, 'HEAD~2', changed_files=['file4'])
    assert_commit(tmp_worktree, 'HEAD~3', changed_files=['file3'])


def test_branch_with_force(foo_bar_cloned_and_nested):
    """Test branch command with --force flag to recreate existing branch"""
    env = foo_bar_cloned_and_nested

    # Make changes
    env.add_new_files('bar/file1', cwd=env.workspace / 'foo')

    # Create branch
    result = cmd_git_nested('branch bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Created branch 'nested/bar' and worktree '.git/tmp/nested/bar'."

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
    assert "Branch 'nested/bar' already exists. Use '--force' to override" in result.stderr

    # Create branch with --force
    result = cmd_git_nested('branch bar --force', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Created branch 'nested/bar' and worktree '.git/tmp/nested/bar'."

    # sleep to have different timestamps in git
    time.sleep(1)

    # Create branch again with --force. The resulting branch should be deterministic.
    result = cmd_git_nested('branch bar --force', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Created branch 'nested/bar' and worktree '.git/tmp/nested/bar'."

    branch_commits_2 = git_get_commit_msg(tmp_worktree, args=['--pretty=format:"%h %s"']).strip().splitlines()
    assert branch_commits_2[2:] == branch_commits_1
