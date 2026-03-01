"""Tests for git nested pull command"""

import pytest
import textwrap

from conftest import (
    assert_gitnested_field,
    git_get_commit_msg,
    git_rev_parse,
    cmd_git_nested,
)


@pytest.fixture
def prepare_pull_test(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested

    # Add new file to bar in the workspace and push
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    yield env


def test_pull(prepare_pull_test):
    """Test basic nested pull functionality"""
    env = prepare_pull_test

    # Do the pull and check output
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."

    # Test that files are correctly pulled
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').is_file()

    # Test foo/bar/.gitnested file contents
    previous_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')
    bar_head_commit_short = git_rev_parse(['--short', 'HEAD'], cwd=env.workspace / 'bar')

    # Get version
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'
    assert_gitnested_field(
        gitnested,
        remote=str(env.upstream / 'bar'),
        branch='master',
        commit=bar_head_commit,
        parent=previous_commit,
    )

    # Check commit messages
    foo_new_commit_message = git_get_commit_msg(env.workspace / 'foo').strip()
    assert foo_new_commit_message == textwrap.dedent(f'''\
        git nested pull

        nested:
          subdir:   "bar"
          merged:   "{bar_head_commit_short}"
        upstream:
          remote:   "{env.upstream}/bar"
          branch:   "master"
          commit:   "{bar_head_commit_short}"
        git-nested:
          version:  "1.0.0"''')

    # Check that we detect that we don't need to pull
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Nested repository 'bar' is up to date with upstream branch 'master'."

    # Test pull after rebasing the original bar repository so that our clone commit is no longer present in the history
    env.run(['git', 'reset', '--hard', 'HEAD^^'], cwd=env.workspace / 'bar')
    env.add_new_files('Bar3', cwd=env.workspace / 'bar')
    env.run(['git', 'push', '--force'], cwd=env.workspace / 'bar')

    # Check that pull_failed doesn't exist yet
    assert not (env.workspace / 'foo' / 'pull_failed').exists()

    # Try to pull (should fail)
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert (
        result.stderr.strip()
        == f"git-nested: Upstream history has been rewritten. Commit {bar_head_commit} is not in the upstream history. Try to 'git nested fetch bar' or add the '-F' flag."
    )


def test_pull_all(foo_bar_cloned):
    """Test nested pull --all functionality"""
    env = foo_bar_cloned

    # Clone two nesteds
    env.run(['git', 'nested', 'clone', '../bar', 'bar1'], cwd=env.workspace / 'foo')
    env.run(['git', 'nested', 'clone', '../bar', 'bar2'], cwd=env.workspace / 'foo')

    # Make changes in bar repository
    env.modify_files('Bar', text="some changes xyz", cwd=env.workspace / 'bar')

    # Pull all nested repositories
    env.run(['git', 'nested', 'pull', '--all'], cwd=env.workspace / 'foo')

    # Check that both nested repositories were updated
    bar1_content = (env.workspace / 'foo' / 'bar1' / 'Bar').read_text()
    assert bar1_content.strip() == 'some changes xyz'

    bar2_content = (env.workspace / 'foo' / 'bar2' / 'Bar').read_text()
    assert bar2_content.strip() == 'some changes xyz'


def create_pull_conflict(env):
    # foo: make modifications in bar (nested repository in foo)
    env.modify_files('bar/Bar2', text='bar/Bar2', cwd=env.workspace / 'foo')

    # Make modifications directly in bar and push them
    env.modify_files('Bar2', text='Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Try to pull the nested repository in foo (will conflict)
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert result.stdout.strip() == textwrap.dedent("""\
        The "git merge" command failed:
        Command failed: 'git merge refs/nested/bar/fetch'.""")
    assert result.stderr.strip() == textwrap.dedent(f'''\
            You will need to finish the pull by hand. A new working tree has been
            created at .git/tmp/nested/bar so that you can resolve the conflicts
            shown in the output above.
            
            This is the common conflict resolution workflow:
            
              1. cd .git/tmp/nested/bar
              2. Resolve the conflicts (see "git status").
              3. "git add" the resolved files.
              4. git commit
              5. If there are more conflicts, restart at step 2.
              6. cd {env.workspace}/foo
              7. git nested commit bar
            
            See "git help merge" for details.
            
            Alternatively, you can abort the pull and reset back to where you started:
            
              1. git nested clean bar
            
            See "git help nested" for more help.''')


def test_pull_conflict(prepare_pull_test):
    """Test conflict when nested repository is pulled"""
    env = prepare_pull_test

    # Test foo/bar/.gitnested file contents before
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'
    foo_initial_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    foo_pull_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'bar')

    assert_gitnested_field(
        gitnested,
        commit=bar_head_commit,
        parent=foo_initial_commit,
    )

    # pull nested repository
    cmd_git_nested('pull bar', cwd=env.workspace / 'foo')

    create_pull_conflict(env)

    # Resolve conflict in the tmp worktree
    worktree_dir = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    (worktree_dir / 'Bar2').write_text('Merged Bar2\n')
    env.run(['git', 'add', 'Bar2'], cwd=worktree_dir)
    merge_msg_file = env.workspace / 'foo' / '.git' / 'worktrees' / 'bar' / 'MERGE_MSG'
    env.run(['git', 'commit', f'--file={merge_msg_file}'], cwd=worktree_dir)

    # commit the resolved conflicts in the nested repository
    cmd_git_nested('commit bar', cwd=env.workspace / 'foo')

    # The pull should be done. Check if files exist with expected content
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').exists()
    assert (env.workspace / 'bar' / 'Bar2').exists()
    bar2_content = (env.workspace / 'foo' / 'bar' / 'Bar2').read_text()
    assert bar2_content.strip() == 'Merged Bar2'

    # Check commit message
    foo_new_commit_message = git_get_commit_msg(env.workspace / 'foo').strip()
    expected_nested_merged_commit = git_rev_parse(['--short', 'nested/bar'], cwd=env.workspace / 'foo')
    expected_upstream_commit = git_rev_parse(['--short', 'HEAD'], cwd=env.workspace / 'bar')
    assert foo_new_commit_message == textwrap.dedent(f'''\
        git nested commit

        nested:
          subdir:   "bar"
          merged:   "{expected_nested_merged_commit}"
        upstream:
          remote:   "{env.upstream}/bar"
          branch:   "master"
          commit:   "{expected_upstream_commit}"
        git-nested:
          version:  "1.0.0"''')

    # Test foo/bar/.gitnested file contents
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')
    assert_gitnested_field(
        gitnested,
        commit=bar_head_commit,
        parent=foo_pull_commit,
    )

    # Check commit message after push
    foo_head_commit_before = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')

    # Push
    result = cmd_git_nested('push bar --branch master', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."
    assert result.stderr.strip() == ""

    # Check commit message after push
    foo_head_commit_after = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    assert foo_head_commit_after == foo_head_commit_before

    # Pull in bar and check files
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').exists()
    assert (env.workspace / 'bar' / 'Bar2').exists()

    # Check content in both repos
    foo_bar2_content = (env.workspace / 'foo' / 'bar' / 'Bar2').read_text()
    assert foo_bar2_content.strip() == 'Merged Bar2'
    bar_bar2_content = (env.workspace / 'bar' / 'Bar2').read_text()
    assert bar_bar2_content.strip() == 'Merged Bar2'


def test_pull_message(prepare_pull_test):
    """Test nested pull with -m and -e options"""
    env = prepare_pull_test

    # Do the pull with -m option
    result = cmd_git_nested("pull -m 'Hello World' bar", cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."

    # Check commit message
    foo_new_commit_message = git_get_commit_msg(env.workspace / 'foo').strip()

    assert foo_new_commit_message == 'Hello World'

    # Add another file to bar and push
    env.add_new_files('Bar3', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Add another file to bar and push
    env.add_new_files('Bar4', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')


def test_pull_new_branch(foo_bar_cloned_and_nested):
    """Test nested pull switching to a new branch"""
    env = foo_bar_cloned_and_nested

    # Create and push new branch in bar
    env.run(['git', 'checkout', '-b', 'branch1'], cwd=env.workspace / 'bar')
    env.run(['git', 'push', '--set-upstream', 'origin', 'branch1'], cwd=env.workspace / 'bar')

    # Test nested file content
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'

    foo_pull_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')

    assert_gitnested_field(
        gitnested,
        remote=str(env.upstream / 'bar'),
        branch='master',
        commit=bar_head_commit,
        parent=foo_pull_commit,
    )

    # Pull with new branch
    cmd_git_nested('pull bar -b branch1 -u', cwd=env.workspace / 'foo')

    # Verify branch was updated
    foo_pull_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')

    assert_gitnested_field(
        gitnested,
        remote=str(env.upstream / 'bar'),
        branch='branch1',
        commit=bar_head_commit,
        parent=foo_pull_commit,
    )

    # Check that we detect that we don't need to pull
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Nested repository 'bar' is up to date with upstream branch 'branch1'."


def test_pull_ours(prepare_pull_test):
    """Test nested pull - conflict - use ours - push"""
    env = prepare_pull_test

    # Note: When you perform rebase ours/theirs are reversed, so this test case will
    # test using local change (ours) although in the step below
    # we actually use git checkout --theirs to accomplish this

    create_pull_conflict(env)

    # Get timestamp before
    foo_file = env.workspace / 'foo' / 'Foo'
    before = foo_file.stat().st_mtime

    # Resolve conflict using ours
    worktree_dir = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    env.run(['git', 'checkout', '--ours', 'Bar2'], cwd=worktree_dir)
    env.run(['git', 'add', 'Bar2'], cwd=worktree_dir)

    merge_msg_file = env.workspace / 'foo' / '.git' / 'worktrees' / 'bar' / 'MERGE_MSG'
    env.run(['git', 'commit', f'--file={merge_msg_file}'], cwd=worktree_dir)

    cmd_git_nested('commit bar', cwd=env.workspace / 'foo')

    after = foo_file.stat().st_mtime
    assert before == after

    # Check files exist
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').exists()
    assert (env.workspace / 'bar' / 'Bar2').exists()

    # Check result (should be ours)
    bar2_content = (env.workspace / 'foo' / 'bar' / 'Bar2').read_text()
    expected = 'bar/Bar2\n'
    assert bar2_content == expected

    # Push
    cmd_git_nested('push bar --branch master', cwd=env.workspace / 'foo')

    # Pull in bar
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')

    # Check files
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').exists()
    assert (env.workspace / 'bar' / 'Bar2').exists()

    # Check result in nested
    bar2_content = (env.workspace / 'bar' / 'Bar2').read_text()
    assert bar2_content == expected


def test_pull_theirs(prepare_pull_test):
    """Test nested pull - conflict - use theirs - push"""
    env = prepare_pull_test

    # Note: When you perform rebase ours/theirs are reversed, so this test case will
    # test using the nested change (theirs) although in the step below
    # we actually use git checkout --ours to accomplish this

    # Pull, modify in foo, and push
    cmd_git_nested('pull bar', cwd=env.workspace / 'foo')

    create_pull_conflict(env)

    # Resolve conflict using theirs
    worktree_dir = env.workspace / 'foo' / '.git' / 'tmp' / 'nested' / 'bar'
    env.run(['git', 'checkout', '--theirs', 'Bar2'], cwd=worktree_dir)
    env.run(['git', 'add', 'Bar2'], cwd=worktree_dir)

    merge_msg_file = env.workspace / 'foo' / '.git' / 'worktrees' / 'bar' / 'MERGE_MSG'
    env.run(['git', 'commit', f'--file={merge_msg_file}'], cwd=worktree_dir)

    cmd_git_nested('commit bar', cwd=env.workspace / 'foo')
    cmd_git_nested('clean bar', cwd=env.workspace / 'foo')

    # Check files exist
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').exists()
    assert (env.workspace / 'bar' / 'Bar2').exists()

    # Check result (should be theirs)
    bar2_content = (env.workspace / 'foo' / 'bar' / 'Bar2').read_text()
    expected = 'new file Bar2\nBar2\n'
    assert bar2_content == expected

    # Push nested repo
    cmd_git_nested('push bar', cwd=env.workspace / 'foo')

    # Pull in bar
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')

    # Check files
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').exists()
    assert (env.workspace / 'bar' / 'Bar2').exists()

    # Check result in nested
    bar2_content = (env.workspace / 'bar' / 'Bar2').read_text()
    assert bar2_content == expected


def test_pull_twice(prepare_pull_test):
    """Test pulling nested twice after each other"""
    env = prepare_pull_test

    # Make changes in foo and pull
    env.add_new_files('bar/Foo2', cwd=env.workspace / 'foo')
    env.run(['git', 'push'], cwd=env.workspace / 'foo')

    result = cmd_git_nested(['pull', 'bar'], cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."
    assert result.stderr.strip() == ""

    # Add another file to bar and push
    env.add_new_files('Bar3', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Pull again
    result = cmd_git_nested(['pull', 'bar'], cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."
    assert result.stderr.strip() == ""

    # Check all files exist
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').is_file()
    assert (env.workspace / 'foo' / 'bar' / 'Bar3').is_file()
    assert (env.workspace / 'foo' / 'bar' / 'Foo2').is_file()


def test_pull_worktree(foo_bar_cloned_and_nested):
    """Test nested pull with git worktree"""
    env = foo_bar_cloned_and_nested

    # Clone bar nested and create worktree
    worktree = env.workspace / 'worktree'
    env.run(['git', 'worktree', 'add', '-b', 'test', worktree], cwd=env.workspace / 'foo')

    # Modify bar
    env.modify_files('Bar', cwd=env.workspace / 'bar', text="added some line")
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Pull from worktree
    result = cmd_git_nested(['pull', '--all'], cwd=worktree)
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."
    assert result.stderr.strip() == ""

    # Merge into foo
    env.run(['git', 'merge', 'test'], cwd=env.workspace / 'foo')

    # Check that bar was updated
    bar_content = (env.workspace / 'foo' / 'bar' / 'Bar').read_text()
    assert bar_content.strip() == 'added some line'


def test_pull_after_merge(foo_bar_cloned_and_nested):
    """Pull after merge with feature branch"""
    env = foo_bar_cloned_and_nested

    # Create a branch in foo and make some changes in it
    env.run(['git', 'checkout', '-b', 'feature'], cwd=env.workspace / 'foo')
    env.add_new_files('feature', cwd=env.workspace / 'foo')
    env.run(['git', 'push', '--set-upstream', 'origin', 'feature'], cwd=env.workspace / 'foo')
    env.run(['git', 'checkout', env.defaultbranch], cwd=env.workspace / 'foo')

    # Commit directly to bar
    with open(env.workspace / 'bar' / 'Bar', 'w') as f:
        f.write("direct change in bar\n")
    env.run(['git', 'commit', '-a', '-m', 'direct change in bar'], cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Pull nested changes
    cmd_git_nested('pull bar', cwd=env.workspace / 'foo')

    # Commit directly to bar
    with open(env.workspace / 'bar' / 'Bar', 'a') as f:
        f.write("another direct change in bar\n")
    env.run(['git', 'commit', '-a', '-m', 'another direct change in bar'], cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Commit to foo/bar
    (env.workspace / 'foo' / 'bar' / 'nested-bar').write_text("change from host\n")
    env.run(['git', 'add', 'bar/nested-bar'], cwd=env.workspace / 'foo')
    env.run(['git', 'commit', '-m', 'change from foo'], cwd=env.workspace / 'foo')

    # Merge previously created feature branch
    env.run(['git', 'merge', '--no-ff', '--no-edit', 'feature'], cwd=env.workspace / 'foo')

    # Pull nested changes - expected: successful pull without conflicts
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."


def test_pull_rebase(prepare_pull_test):
    """Test nested pull with -M rebase method"""
    env = prepare_pull_test

    # Get the gitnested file
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'
    assert_gitnested_field(gitnested, method='merge')

    # Do the pull with -M rebase to change the method and check output
    result = cmd_git_nested('pull -M rebase bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."

    # Test nested file content
    assert (env.workspace / 'foo' / 'bar' / 'Bar2').is_file()
    assert gitnested.is_file()

    # Test foo/bar/.gitnested file contents
    foo_pull_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')

    assert_gitnested_field(
        gitnested,
        remote=str(env.upstream / 'bar'),
        branch='master',
        commit=bar_head_commit,
        parent=foo_pull_commit,
        method='rebase',
    )

    # Check commit messages
    foo_new_commit_message = git_get_commit_msg(env.workspace / 'foo').strip()
    bar_head_commit_short = git_rev_parse(['--short', bar_head_commit], cwd=env.workspace / 'foo')
    assert foo_new_commit_message == textwrap.dedent(f'''\
        git nested pull

        nested:
          subdir:   "bar"
          merged:   "{bar_head_commit_short}"
        upstream:
          remote:   "{env.upstream}/bar"
          branch:   "master"
          commit:   "{bar_head_commit_short}"
        git-nested:
          version:  "1.0.0"''')

    # Check that we detect that we don't need to pull again
    result = cmd_git_nested('pull -M rebase bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Nested repository 'bar' is up to date with upstream branch 'master'."


def test_pull_rebase_conflict(prepare_pull_test):
    """Test nested pull with -M rebase method that results in a conflict"""
    env = prepare_pull_test

    # Get the gitnested file
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'
    assert_gitnested_field(gitnested, method='merge')

    # Pull with rebase method to set the method
    result = cmd_git_nested('pull -M rebase bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."

    # Verify method changed to rebase
    assert_gitnested_field(gitnested, method='rebase')

    # Modify Bar2 in foo and push
    env.modify_files('bar/Bar2', text='bar/Bar2 from foo', cwd=env.workspace / 'foo')
    env.run(['git', 'push'], cwd=env.workspace / 'foo')

    # Modify Bar2 in bar with conflicting content and push
    env.modify_files('Bar2', text='Bar2 from bar', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Try to pull (will conflict with rebase method)
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert 'The "git rebase" command failed:' in result.stdout
    assert "Command failed: 'git rebase refs/nested/bar/fetch nested/bar'" in result.stdout


def test_pull_with_force(prepare_pull_test):
    """Test pull --force triggers a reclone"""
    env = prepare_pull_test

    # Do a pull without --force flag
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."

    # Do a pull without --force flag should do nothing
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Nested repository 'bar' is up to date with upstream branch 'master'."

    # Enforce a pull with --force flag
    result = cmd_git_nested('pull --force bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."
