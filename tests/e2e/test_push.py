"""Tests for git nested push command"""

from conftest import (
    assert_commit,
    assert_commit_count,
    assert_gitnested_field,
    cmd_git_nested,
    git_get_commit_msg,
    git_rev_parse,
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
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

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
        remote=(env.upstream / 'bar').as_posix(),
        branch='master',
        commit=bar_head_commit,
        parent=foo_pull_commit,
        method=None,
    )

    # Make more commits in foo repo
    env.add_new_files('bar/FooBar2', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar', cwd=env.workspace / 'foo')

    result = cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

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
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

    env.add_new_files('bar/FooBar4', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar3', cwd=env.workspace / 'foo')
    result = cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

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
    assert result.output.strip() == "git-nested: upstream master has commits you do not have; pull first"


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
    with readme_path.open('a') as f:
        f.write(f"{msg_foo1}\n")
    env.run(['git', 'add', 'bar/readme'], cwd=foo1_dir)
    env.run(['git', 'commit', '-m', msg_foo1], cwd=foo1_dir)
    cmd_git_nested('push bar --branch=master', cwd=foo1_dir)

    # Check that the nested-push/bar branch was deleted after push
    result = env.run(['git', 'branch', '--list', 'nested-push/bar'], cwd=foo1_dir)
    assert result.stdout.strip() == ''

    # Pull in the nested changes from foo1 into foo2
    cmd_git_nested('pull bar', cwd=foo2_dir)

    # Make a local change to the foo2 nested and push it
    readme_path = foo2_dir / 'bar' / 'readme'
    msg_foo2 = "foo2 initial add to nested"
    with readme_path.open('a') as f:
        f.write(f"{msg_foo2}\n")
    env.run(['git', 'add', 'bar/readme'], cwd=foo2_dir)
    env.run(['git', 'commit', '-m', msg_foo2], cwd=foo2_dir)

    result = cmd_git_nested('push bar --branch=master', cwd=foo2_dir)
    assert result.output.strip() == f"bar: pushed to {bar_dir} (master)"

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
    with (bar_dir / 'Bar').open('a') as f:
        f.write("direct change in bar\n")
    env.run(['git', 'commit', '-a', '-m', 'direct change in bar'], cwd=bar_dir)

    # Pull changes from nested bar repository
    cmd_git_nested('pull bar', cwd=foo_dir)

    # Commit directly to bar
    with (bar_dir / 'Bar').open('a') as f:
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
    assert result.output.strip() == f"bar: pulled from {bar_upstream.as_posix()} ({env.defaultbranch})"

    # Push nested changes - expected: successful push without conflicts
    result = cmd_git_nested(f'push bar -b {env.defaultbranch} -u', cwd=foo_dir)
    assert result.output.strip() == f"bar: pushed to {bar_upstream.as_posix()} ({env.defaultbranch})"


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
    result = cmd_git_nested('push doc --remote=../upstream -b master --commit -u', cwd=init_dir)
    assert result.output.strip() == "doc: pushed to ../upstream (master)"

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
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (foo-master)"


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
    env.run(['git', 'clone', (env.upstream / 'bar').as_posix(), str(new_bar_dir)])

    # Fresh clone should only have Foo1, not Bar2
    assert (new_bar_dir / 'Foo1').exists()
    assert not (new_bar_dir / 'Bar2').exists()


def test_push_new_branch(foo_bar_cloned_and_nested):
    """Test nested push to a new branch"""
    env = foo_bar_cloned_and_nested

    # Make a commit
    env.add_new_files('bar/FooBar', cwd=env.workspace / 'foo')

    # Do the nested push to another branch
    result = cmd_git_nested('push bar --branch newbar --commit -u', cwd=env.workspace / 'foo')
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (newbar)"

    # Do the nested push to another branch again
    result = cmd_git_nested('push bar --branch newbar', cwd=env.workspace / 'foo')
    assert result.output.strip() == "bar: nothing to push"

    # Pull the changes from UPSTREAM/bar in OWNER/bar
    env.run(['git', 'fetch'], cwd=env.workspace / 'bar')
    env.run(['git', 'checkout', 'newbar'], cwd=env.workspace / 'bar')
    assert (env.workspace / 'bar' / 'FooBar').is_file()


def test_push_no_changes(foo_bar_cloned_and_nested):
    """Test that push requires changes to push"""
    env = foo_bar_cloned_and_nested

    # Try to push with no changes
    cp = env.run('git nested push bar --branch=master', check=False, cwd=env.workspace / 'foo')
    assert cp.output.strip() == "bar: nothing to push"


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
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

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
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

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
        remote=(env.upstream / 'bar').as_posix(),
        branch='master',
        commit=bar_head_commit,
        parent=foo_push_commit,
        method='rebase',
    )

    # Make another commit and push again to verify method persists
    env.add_new_files('bar/FooBar2', cwd=env.workspace / 'foo')
    result = cmd_git_nested('push bar --branch master --commit', cwd=env.workspace / 'foo')
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

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
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

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
    assert result.output.strip() == "git-nested: upstream master has commits you do not have; pull first"

    result = cmd_git_nested('push bar --branch=master --force', cwd=env.workspace / 'foo')
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"


def test_push_explicit_branch_does_not_exist(foo_bar_cloned_and_nested):
    """Test that pushing an explicit local branch that doesn't exist errors clearly"""
    env = foo_bar_cloned_and_nested

    result = cmd_git_nested('push bar nonexistent-branch --branch=master', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: no nested branch nonexistent-branch to push"


def test_push_squash_with_explicit_branch_errors(foo_bar_cloned_and_nested):
    """Test that --squash can't be combined with an explicit branch parameter"""
    env = foo_bar_cloned_and_nested

    result = cmd_git_nested('push bar somebranch --squash --branch=master', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: --squash can't be combined with an explicit branch"


def test_push_rebase_conflict_during_branch_creation(foo_bar_cloned_and_nested):
    """Test that a push (method=rebase) whose internal branch-creation rebase conflicts
    against an already-fetched upstream reports the rebase failure, not a generic error"""
    env = foo_bar_cloned_and_nested

    # Someone else pushes a conflicting change upstream, and we fetch it -- this is what
    # populates refs/nested/bar/fetch, the ref the internal rebase step replays onto.
    env.modify_files('Bar', text='change from bar upstream', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')
    cmd_git_nested('fetch bar', cwd=env.workspace / 'foo')

    # We make a conflicting local edit to the same file.
    env.modify_files('bar/Bar', text='change from foo', cwd=env.workspace / 'foo')

    # --force skips the "pull first" ancestry check; the internal rebase against the
    # already-fetched upstream then conflicts while (re)building the nested branch.
    result = cmd_git_nested('push -M rebase --force bar --branch=master', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    # git's own rebase output is interleaved and names a commit sha. The
    # failure of the internal rebase is caught and re-reported, so the one
    # line git-nested contributes is the whole of what it says.
    assert "git-nested: bar: git rebase failed, so nothing was pushed" in result.output


def test_push_commit_with_message_file(foo_bar_cloned_and_nested):
    """Test that `push --commit --file` uses the given commit message file"""
    env = foo_bar_cloned_and_nested

    env.add_new_files('bar/FooBar', cwd=env.workspace / 'foo')

    msg_file = env.workspace / 'foo' / 'commit_msg.txt'
    msg_file.write_text('Custom push commit message\n')

    result = cmd_git_nested(f'push bar --branch=master --commit --file={msg_file}', cwd=env.workspace / 'foo')
    assert result.output.strip() == f"bar: pushed to {env.upstream.as_posix()}/bar (master)"

    last_msg = env.run(['git', 'log', '-1', '--format=%B'], cwd=env.workspace / 'foo').stdout
    assert last_msg.strip() == 'Custom push commit message'


def test_push_commit_refuses_a_branch_it_does_not_track(foo_bar_cloned_and_nested):
    """--commit records the push; on another branch than the tracked one the next pull would break."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/from-foo', cwd=foo)

    result = cmd_git_nested('push --commit bar', cwd=foo, check=False)

    assert result.returncode == 1
    assert result.output.strip() == (
        "git-nested: bar: --commit records the push in .gitnested, but it goes to foo-master, "
        "not to the tracked branch master; push there with -b master"
    )
    assert env.run(['git', 'branch', '--list', 'foo-master'], cwd=env.upstream / 'bar').output == ''


def test_push_override_without_u_keeps_the_tracked_branch(foo_bar_cloned_and_nested):
    """-r/-b only change where this push goes; .gitnested keeps tracking what it did."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    fork = (env.upstream / 'fork').as_posix()
    env.run(['git', 'clone', '--quiet', '--bare', (env.upstream / 'bar').as_posix(), fork])
    env.add_new_files('bar/from-foo', cwd=foo)

    cmd_git_nested(['push', '-r', fork, '-b', 'topic', 'bar'], foo)

    assert_gitnested_field(foo / 'bar' / '.gitnested', remote=(env.upstream / 'bar').as_posix(), branch='master')


def test_push_commit_with_an_override_needs_u(foo_bar_cloned_and_nested):
    """--commit would record a commit of a branch .gitnested does not track."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/from-foo', cwd=foo)

    result = cmd_git_nested('push -b topic --commit bar', cwd=foo, check=False)

    assert result.returncode == 1
    assert result.output.strip() == (
        "git-nested: bar: --commit records the push in .gitnested, but -r and -b only change this push; "
        "add -u to track them"
    )


def test_a_failed_push_leaves_no_branch_behind(foo_bar_cloned_and_nested):
    """The branch built for the push goes, even when upstream rejects it, so the next pull works."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    hook = env.upstream / 'bar' / 'hooks' / 'pre-receive'
    hook.write_text('#!/bin/sh\nexit 1\n')
    hook.chmod(0o755)
    env.add_new_files('bar/from-foo', cwd=foo)

    result = cmd_git_nested('push -b master bar', cwd=foo, check=False)

    assert result.returncode == 1
    assert env.run(['git', 'branch', '--list', 'nested/*'], cwd=foo).output == ''
    cmd_git_nested('pull bar', cwd=foo)


def test_push_keeps_the_message_of_a_merged_commit(foo_bar_cloned_and_nested):
    """A change that came in through a merge reaches upstream under its own message."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.run(['git', 'switch', '-q', '-c', 'feat'], cwd=foo)
    env.modify_files('bar/Bar', cwd=foo)  # 'modified file: bar/Bar'
    env.add_new_files('feat-other', cwd=foo)
    env.run(['git', 'switch', '-q', 'master'], cwd=foo)
    env.add_new_files('main-other', cwd=foo)
    env.run(['git', 'merge', '-q', '--no-ff', 'feat', '-m', 'Merge unrelated PR'], cwd=foo)

    cmd_git_nested('push -b master bar', cwd=foo)

    log = env.run(['git', 'log', '--format=%s', 'master'], cwd=env.upstream / 'bar').output.splitlines()
    assert log == ['modified file: bar/Bar', 'bard/Bard', 'Bar']


def _three_bar_commits_then_another(env):
    foo = env.workspace / 'foo'
    for name in ('s1', 's2', 's3'):
        env.add_new_files(f'bar/{name}', cwd=foo)
    env.add_new_files('other', cwd=foo)
    return foo


def _upstream_message(env):
    return env.run(['git', 'log', '-1', '--format=%B', 'master'], cwd=env.upstream / 'bar').output.strip()


def test_push_squash_takes_the_message(foo_bar_cloned_and_nested):
    """-m is the message of the one commit upstream gets."""
    env = foo_bar_cloned_and_nested
    foo = _three_bar_commits_then_another(env)

    cmd_git_nested(['push', '--squash', '-m', 'one commit upstream', '-b', 'master', 'bar'], foo)

    assert _upstream_message(env) == 'one commit upstream'


def test_push_squash_lists_the_squashed_commits(foo_bar_cloned_and_nested):
    """Without -m the message lists the squashed commits, not a commit that did not touch the subdir."""
    env = foo_bar_cloned_and_nested
    foo = _three_bar_commits_then_another(env)

    cmd_git_nested('push --squash -b master bar', cwd=foo)

    assert _upstream_message(env) == (
        "Squash 3 commits\n\n- add new file: bar/s1\n- add new file: bar/s2\n- add new file: bar/s3"
    )
    assert env.run(['git', 'rev-list', '--count', 'master'], cwd=env.upstream / 'bar').output.strip() == '3'


def test_push_squash_takes_the_message_file(foo_bar_cloned_and_nested, tmp_path):
    """--file is the message of the one commit upstream gets."""
    env = foo_bar_cloned_and_nested
    foo = _three_bar_commits_then_another(env)
    message = tmp_path / 'msg.txt'
    message.write_text('from a file\n')

    cmd_git_nested(['push', '--squash', '--file', message.as_posix(), '-b', 'master', 'bar'], foo)

    assert _upstream_message(env) == 'from a file'


def test_push_squash_of_one_commit_keeps_its_message(foo_bar_cloned_and_nested):
    """One squashed commit needs no list."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/s1', cwd=foo)
    env.add_new_files('other', cwd=foo)

    cmd_git_nested('push --squash -b master bar', cwd=foo)

    assert _upstream_message(env) == 'add new file: bar/s1'


def test_push_refuses_a_read_only_repository(foo_bar_cloned_and_nested):
    """readonly: true in .gitnested keeps push from writing to someone else's repository."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested('config bar readonly true', cwd=foo)
    env.run(['git', 'commit', '-qm', 'bar is read-only'], cwd=foo)
    env.add_new_files('bar/from-foo', cwd=foo)

    result = cmd_git_nested('push -b master bar', cwd=foo, check=False)

    assert result.returncode == 1
    assert result.output.strip() == (
        "git-nested: bar: is read-only, so push refuses; 'git nested config bar readonly false' allows it"
    )


def test_push_all_skips_a_read_only_repository(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested('config bar readonly true', cwd=foo)
    env.run(['git', 'commit', '-qm', 'bar is read-only'], cwd=foo)

    result = cmd_git_nested('push --all', cwd=foo)

    assert result.output.strip() == "bar: skipped, it is read-only"


def _init_with_an_empty_upstream(env):
    """A directory 'mine' in foo, nested with an empty upstream that tracks master."""
    foo = env.workspace / 'foo'
    empty = env.upstream / 'new'
    env.run(['git', 'init', '-q', '--bare', empty.as_posix()])
    env.add_new_files('mine/file', cwd=foo)
    cmd_git_nested(['init', '-r', empty.as_posix(), '-b', 'master', 'mine'], foo)
    return foo, empty


def test_push_creates_the_tracked_branch_in_an_empty_upstream(foo_bar_cloned):
    """Without the tracked branch upstream, push makes it, so pull works afterwards."""
    env = foo_bar_cloned
    foo, empty = _init_with_an_empty_upstream(env)

    result = cmd_git_nested('push mine', cwd=foo)

    assert result.output.strip() == f"mine: pushed to {empty.as_posix()} (master)"
    cmd_git_nested('pull mine', cwd=foo)


def test_fetch_explains_a_missing_tracked_branch(foo_bar_cloned):
    """Not git's raw error, but what is missing and how to make it."""
    env = foo_bar_cloned
    foo, empty = _init_with_an_empty_upstream(env)

    result = cmd_git_nested('fetch mine', cwd=foo, check=False)

    assert result.returncode == 1
    assert (
        result.output.strip() == f"git-nested: {empty.as_posix()} has no branch master yet; 'git nested push' makes it"
    )
