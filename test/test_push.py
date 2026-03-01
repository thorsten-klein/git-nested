"""Tests for git nested push command"""

from conftest import (
    assert_commit,
    assert_gitnested_field,
    assert_commit_count,
    git_get_commit_msg,
    git_rev_parse,
    cmd_git_nested,
)


def test_nested_push(foo_bar_cloned_and_nested):
    """Test basic nested push functionality"""
    env = foo_bar_cloned_and_nested
    assert_commit_count(env.workspace / 'bar', 2)

    # In the main repo, clone the nested and make a series of commits
    env.add_new_files('bar/FooBar', cwd=env.workspace / 'foo')
    env.add_new_files('./FooBar', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar', cwd=env.workspace / 'foo')
    env.modify_files('./FooBar', cwd=env.workspace / 'foo')
    env.modify_files('./FooBar', 'bar/FooBar', cwd=env.workspace / 'foo')
    assert_commit(
        env.workspace / 'foo',
        'HEAD',
        author_email='foo@foo',
        author_name='FooUser',
        committer_email='foo@foo',
        committer_name='FooUser',
    )

    # Add new file in bar and push
    env.add_new_files('bargy', cwd=env.workspace / 'bar')
    assert_commit(
        env.workspace / 'bar',
        'HEAD',
        author_email='bar@bar',
        author_name='BarUser',
        committer_email='bar@bar',
        committer_name='BarUser',
    )

    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Change the user in foo when changes are pushed
    env.run(['git', 'config', 'user.name', 'PushUser'], cwd=env.workspace / 'foo')
    env.run(['git', 'config', 'user.email', 'push@push'], cwd=env.workspace / 'foo')

    # Do the nested pull and push
    cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    result = cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."

    # Pull changes in bar
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')

    # Check commit author/committer in bar
    bar_commits = git_get_commit_msg(env.workspace / 'bar', args=['--pretty=format:"%h %s"']).strip().splitlines()
    assert len(bar_commits) == 7

    assert_commit(
        env.workspace / 'bar',
        'HEAD',
        author_email='push@push',
        author_name='PushUser',
        committer_email='push@push',
        committer_name='PushUser',
        commit_title='git nested pull',
        changed_files=[],
    )
    assert_commit(
        env.workspace / 'bar',
        'HEAD^1',
        author_email='foo@foo',
        author_name='FooUser',
        committer_email='foo@foo',
        committer_name='FooUser',
        commit_title='modified file: bar/FooBar',
        changed_files=['FooBar'],
    )
    assert_commit(
        env.workspace / 'bar',
        'HEAD^2',
        author_email='bar@bar',
        author_name='BarUser',
        committer_email='bar@bar',
        committer_name='BarUser',
        commit_title='add new file: bargy',
        changed_files=['bargy'],
    )
    assert_commit(
        env.workspace / 'bar',
        'HEAD~2',
        author_email='foo@foo',
        author_name='FooUser',
        committer_email='foo@foo',
        committer_name='FooUser',
        commit_title='modified file: bar/FooBar',
        changed_files=['FooBar'],
    )
    assert_commit(
        env.workspace / 'bar',
        'HEAD~3',
        author_email='foo@foo',
        author_name='FooUser',
        committer_email='foo@foo',
        committer_name='FooUser',
        commit_title='add new file: bar/FooBar',
        changed_files=['FooBar'],
    )

    # Check that all commits arrived in nested
    assert_commit_count(env.workspace / 'bar', 7)

    # Test foo/bar/.gitnested file contents
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'
    foo_pull_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')

    assert_gitnested_field(
        gitnested,
        remote=str(env.upstream / 'bar'),
        branch='master',
        commit=bar_head_commit,
        parent=foo_pull_commit,
        method=None,
    )

    # Make more commits in foo repo
    env.add_new_files('bar/FooBar2', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar', cwd=env.workspace / 'foo')

    result = cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."

    # Pull the changes from UPSTREAM/bar in OWNER/bar
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')

    assert (env.workspace / 'bar' / 'Bar').is_file()
    assert (env.workspace / 'bar' / 'FooBar').is_file()
    assert (env.workspace / 'bar' / 'bard').exists()
    assert (env.workspace / 'bar' / 'bargy').is_file()
    assert not (env.workspace / 'bar' / '.gitnested').exists()

    # Sequential pushes
    env.add_new_files('bar/FooBar3', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar', cwd=env.workspace / 'foo')
    result = cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."

    env.add_new_files('bar/FooBar4', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar3', cwd=env.workspace / 'foo')
    result = cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."

    # Make changes in nested
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')
    env.add_new_files('barBar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Make changes in foo repo
    env.add_new_files('bar/FooBar5', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar3', cwd=env.workspace / 'foo')

    # Try to push (should fail)
    result = cmd_git_nested('push bar --branch master', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == "git-nested: There are new changes upstream (master), you need to pull first."


def test_push_pull_multiple_nested(foo_bar_cloned_and_nested):
    """Test multiple repos pushing and pulling to same nested repository"""
    env = foo_bar_cloned_and_nested

    bar_dir = env.workspace / 'bar'
    foo1_dir = env.workspace / 'foo1'
    foo2_dir = env.workspace / 'foo2'

    env.clone_foo(foo1_dir)
    env.clone_foo(foo2_dir)

    # Add an empty 'readme' to the bar repo
    (bar_dir / '.gitattributes').write_text('* text eol=lf\n')
    (bar_dir / 'readme').touch()
    env.run(['git', 'add', 'readme', '.gitattributes'], cwd=bar_dir)
    env.run(['git', 'commit', '-m', 'Initial bar'], cwd=bar_dir)

    # To push into here later we must not have working copy on master branch
    env.run(['git', 'checkout', '-b', 'temp'], cwd=bar_dir)

    # Clone the bar repo into foo1
    cmd_git_nested(f'clone {bar_dir} bar -b {env.defaultbranch}', cwd=foo1_dir)

    # Clone the bar repo into foo2
    cmd_git_nested(f'clone {bar_dir} bar -b {env.defaultbranch}', cwd=foo2_dir)

    # Make a change to the foo1 nested repository and push it
    msg_foo1 = "foo1 initial add to nested"
    readme_path = foo1_dir / 'bar' / 'readme'
    with open(readme_path, 'a') as f:
        f.write(f"{msg_foo1}\n")
    env.run(['git', 'add', 'bar/readme'], cwd=foo1_dir)
    env.run(['git', 'commit', '-m', msg_foo1], cwd=foo1_dir)
    cmd_git_nested('push bar --branch=master', cwd=foo1_dir)

    # Check that the nested-push/bar branch was deleted after push
    result = env.run(['git', 'branch', '--list', 'nested-push/bar'], cwd=foo1_dir)
    assert result.stdout.strip() == ''
    assert result.stderr.strip() == ''

    # Pull in the nested changes from foo1 into foo2
    cmd_git_nested('pull bar', cwd=foo2_dir)

    # Make a local change to the foo2 nested and push it
    readme_path = foo2_dir / 'bar' / 'readme'
    msg_foo2 = "foo2 initial add to nested"
    with open(readme_path, 'a') as f:
        f.write(f"{msg_foo2}\n")
    env.run(['git', 'add', 'bar/readme'], cwd=foo2_dir)
    env.run(['git', 'commit', '-m', msg_foo2], cwd=foo2_dir)

    result = cmd_git_nested('push bar --branch=master', cwd=foo2_dir)
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{bar_dir}' (master)."
    assert result.stderr.strip() == ''

    # Go back into foo1 and pull the nested updates
    cmd_git_nested('pull bar', cwd=foo1_dir)

    # The readme file should have both changes
    readme_content = (foo1_dir / 'bar' / 'readme').read_text()
    assert readme_content.strip() == f"{msg_foo1}\n{msg_foo2}"


def test_push_pull_feature_branch(foo_bar_cloned_and_nested):
    """Push and pull with feature branch"""
    env = foo_bar_cloned_and_nested

    foo_dir = env.workspace / 'foo'
    bar_dir = env.workspace / 'bar'
    bar_upstream = env.upstream / 'bar'

    # Commit some changes to the foo repo
    (foo_dir / 'feature').touch()
    env.run(['git', 'add', 'feature'], cwd=foo_dir)
    env.run(['git', 'commit', '-m', 'feature added'], cwd=foo_dir)

    # Commit directly to bar
    with open(bar_dir / 'Bar', 'a') as f:
        f.write("direct change in bar\n")
    env.run(['git', 'commit', '-a', '-m', 'direct change in bar'], cwd=bar_dir)

    # Pull changes from nested bar repository
    cmd_git_nested('pull bar', cwd=foo_dir)

    # Commit directly to bar
    with open(bar_dir / 'Bar', 'a') as f:
        f.write("another direct change in bar\n")
    env.run(['git', 'commit', '-a', '-m', 'another direct change in bar'], cwd=bar_dir)
    env.run(['git', 'push'], cwd=bar_dir)

    # Checkout temp branch otherwise push to master will fail
    env.run(['git', 'checkout', '-b', 'temp'], cwd=bar_dir)

    # Commit to foo/bar
    (foo_dir / 'bar' / 'nested-bar').write_text("change from foo\n")
    env.run(['git', 'add', 'bar/nested-bar'], cwd=foo_dir)
    env.run(['git', 'commit', '-m', 'change from foo'], cwd=foo_dir)

    # Pull nested changes - expected: successful pull without conflicts
    result = cmd_git_nested('pull bar', cwd=foo_dir)
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{bar_upstream}' ({env.defaultbranch})."

    # Push nested changes - expected: successful push without conflicts
    result = cmd_git_nested(f'push bar -b {env.defaultbranch} -u', cwd=foo_dir)
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{bar_upstream}' ({env.defaultbranch})."


def test_push_after_init(env):
    """Test push after init"""
    # Create directory and init git locally
    # This will test some corner cases when you don't have any previous commits to rely on
    init_dir = env.workspace / 'init'

    env.clone_init()
    cmd_git_nested('init doc', cwd=init_dir)

    upstream_dir = env.workspace / 'upstream'
    upstream_dir.mkdir()
    env.run(['git', 'init', '--bare'], cwd=upstream_dir)

    # Push
    result = cmd_git_nested('push doc --remote=../upstream --commit', cwd=init_dir)
    assert result.stdout.strip() == "Nested repository 'doc' pushed to '../upstream' (init-master)."

    # Test init/doc/.gitnested file contents
    gitnested = init_dir / 'doc' / '.gitnested'
    assert_gitnested_field(gitnested, remote='../upstream', branch='master', commit=None, parent=None, method=None)

    # Clone upstream and verify
    up_dir = env.workspace / 'up'
    env.run(['git', 'clone', str(upstream_dir), str(up_dir)])
    assert (up_dir / '.git').exists()
    assert not (up_dir / '.gitnested').exists()


def test_push_after_push_no_changes(foo_bar_cloned_and_nested):
    """Test that push after an empty push works"""
    env = foo_bar_cloned_and_nested

    # Do an empty push
    cmd_git_nested('push bar', cwd=env.workspace / 'foo')

    # Add a file and push again
    env.add_new_files('bar/Bar1', cwd=env.workspace / 'foo')
    result = cmd_git_nested('push bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (foo-master)."


def test_push_force(foo_bar_cloned_and_nested):
    """Test nested push with --force flag"""
    env = foo_bar_cloned_and_nested

    # Add new file to bar and push
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Add file in foo and force push
    env.add_new_files('bar/Foo1', cwd=env.workspace / 'foo')
    cmd_git_nested('push bar --force --branch=master', cwd=env.workspace / 'foo')

    # Pull in foo and check that Foo1 exists but Bar2 doesn't (because we force pushed)
    cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'bar' / 'Foo1').exists()
    assert not (env.workspace / 'foo' / 'bar' / 'Bar2').exists()

    # Pull in bar (will actually merge the old master with the new one)
    env.run(['git', 'pull', '--rebase=false'], cwd=env.workspace / 'bar')

    # After merge, both files should exist
    assert (env.workspace / 'bar' / 'Bar2').exists()
    assert (env.workspace / 'bar' / 'Foo1').exists()

    # Test that a fresh repo is not contaminated
    new_bar_dir = env.workspace / 'newbar'
    env.run(['git', 'clone', str(env.upstream / 'bar'), str(new_bar_dir)])

    # Fresh clone should only have Foo1, not Bar2
    assert (new_bar_dir / 'Foo1').exists()
    assert not (new_bar_dir / 'Bar2').exists()


def test_push_new_branch(foo_bar_cloned_and_nested):
    """Test nested push to a new branch"""
    env = foo_bar_cloned_and_nested

    # Make a commit
    env.add_new_files('bar/FooBar', cwd=env.workspace / 'foo')

    # Do the nested push to another branch
    result = cmd_git_nested('push bar --branch newbar --commit', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (newbar)."

    # Do the nested push to another branch again
    result = cmd_git_nested('push bar --branch newbar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == "Nested repository 'bar' has no new commits to push."

    # Pull the changes from UPSTREAM/bar in OWNER/bar
    env.run(['git', 'fetch'], cwd=env.workspace / 'bar')
    env.run(['git', 'checkout', 'newbar'], cwd=env.workspace / 'bar')
    assert (env.workspace / 'bar' / 'FooBar').is_file()


def test_push_no_changes(foo_bar_cloned_and_nested):
    """Test that push requires changes to push"""
    env = foo_bar_cloned_and_nested

    # Try to push with no changes
    cp = env.run('git nested push bar --branch=master', check=False, cwd=env.workspace / 'foo')
    assert cp.stdout.strip() == "Nested repository 'bar' has no new commits to push."


def test_push_squash(foo_bar_cloned_and_nested):
    """Test nested push with --squash flag"""
    env = foo_bar_cloned_and_nested

    # Make a series of commits
    env.add_new_files('bar/FooBar1', cwd=env.workspace / 'foo')
    env.add_new_files('bar/FooBar2', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar1', cwd=env.workspace / 'foo')
    env.add_new_files('./FooBar', cwd=env.workspace / 'foo')
    env.modify_files('./FooBar', 'bar/FooBar2', cwd=env.workspace / 'foo')

    # Do the nested push with --squash
    result = cmd_git_nested('push bar --squash --branch master', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."

    # Pull in bar
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')

    # Check that all commits arrived in nested (squashed to 1 commit + initial 2)
    assert_commit_count(env.workspace / 'bar', 3)

    # Check files exist
    assert (env.workspace / 'bar' / 'Bar').exists()
    assert (env.workspace / 'bar' / 'FooBar1').exists()
    assert (env.workspace / 'bar' / 'FooBar2').exists()
    assert not (env.workspace / 'bar' / '.gitnested').exists()


def test_push_rebase(foo_bar_cloned_and_nested):
    """Test nested push with -M rebase method"""
    env = foo_bar_cloned_and_nested

    # Get the gitnested file
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'

    # Verify the default method is 'merge'
    assert_gitnested_field(gitnested, remote=None, branch=None, commit=None, parent=None, method='merge')

    # Make a commit
    env.add_new_files('bar/FooBar', cwd=env.workspace / 'foo')

    # Do the nested push with -M rebase to change the method
    result = cmd_git_nested('push -M rebase bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."

    # Verify the method was changed to rebase in the config
    assert_gitnested_field(gitnested, remote=None, branch=None, commit=None, parent=None, method='rebase')

    # Pull the changes from upstream in bar
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')

    # Verify the file was pushed
    assert (env.workspace / 'bar' / 'FooBar').is_file()

    # Check .gitnested file fields
    foo_push_commit = git_rev_parse(['HEAD^'], cwd=env.workspace / 'foo')
    bar_head_commit = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')

    assert_gitnested_field(
        gitnested,
        remote=str(env.upstream / 'bar'),
        branch='master',
        commit=bar_head_commit,
        parent=foo_push_commit,
        method='rebase',
    )

    # Make another commit and push again to verify method persists
    env.add_new_files('bar/FooBar2', cwd=env.workspace / 'foo')
    result = cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."

    # Verify method is still rebase after second push
    assert_gitnested_field(gitnested, remote=None, branch=None, commit=None, parent=None, method='rebase', version=None)

    # Pull and verify second file
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')
    assert (env.workspace / 'bar' / 'FooBar2').is_file()


def test_push_rebase_conflict(foo_bar_cloned_and_nested):
    """Test that nested push with conflicting upstream changes shows error"""
    env = foo_bar_cloned_and_nested

    # Get the gitnested file
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'

    # Make a commit and push with rebase method to set it up
    env.add_new_files('bar/FooBar', cwd=env.workspace / 'foo')
    result = cmd_git_nested('push -M rebase bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."

    # Verify method changed to rebase
    assert_gitnested_field(gitnested, remote=None, branch=None, commit=None, parent=None, method='rebase')

    # Pull the changes in bar
    env.run(['git', 'pull'], cwd=env.workspace / 'bar')

    # Modify FooBar in foo
    env.modify_files('bar/FooBar', text='change from foo', cwd=env.workspace / 'foo')

    # Modify FooBar in bar with conflicting content and push
    env.modify_files('FooBar', text='change from bar', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # Try to push from foo - will fail because there are upstream changes
    result = cmd_git_nested('push bar --branch=master', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == "git-nested: There are new changes upstream (master), you need to pull first."

    result = cmd_git_nested('push bar --branch=master --force', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (master)."
    assert result.stderr.strip() == ""
