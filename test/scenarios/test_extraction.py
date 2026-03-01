"""Tests extraction of a nested repository"""

from conftest import (
    assert_commit,
    assert_commit_count,
    git_get_commit_msg,
    git_rev_parse,
    clone_repo,
    cmd_git_nested,
    create_upstream_repo,
)


def test_usual_contribution(foo_bar_cloned_and_nested):
    """Test basic nested push functionality"""
    env = foo_bar_cloned_and_nested

    # count commits
    assert_commit_count(env.workspace / 'foo', 2)
    assert_commit_count(env.workspace / 'bar', 2)

    # Make changes in the nested repository (inside foo)
    env.add_new_files('bar/FooBar', cwd=env.workspace / 'foo')
    env.modify_files('bar/Bar', text="make a change inside foo", cwd=env.workspace / 'foo')

    # Make changes in the nested repository directly (bar)
    env.add_new_files('FirstBar', cwd=env.workspace / 'bar')
    env.add_new_files('SecondBar', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')

    # count commits: 2 more in foo, 2 more in bar
    assert_commit_count(env.workspace / 'foo', 4)
    assert_commit_count(env.workspace / 'bar', 4)

    # Check that the files created in bar do not exist inside nested repository (foo/bar)
    assert not (env.workspace / 'foo' / 'bar' / 'FirstBar').exists()
    assert not (env.workspace / 'foo' / 'bar' / 'SecondBar').exists()

    # Do the nested pull
    result = cmd_git_nested('pull bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (master)."

    # Ensure that the changes from bar are correctly pulled
    assert (env.workspace / 'foo' / 'bar' / 'FirstBar').exists()
    assert (env.workspace / 'foo' / 'bar' / 'SecondBar').exists()
    assert_commit_count(env.workspace / 'foo', 5)  # 1 commit more
    assert_commit(
        env.workspace / 'foo',
        'HEAD',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        commit_title='git nested pull',
        changed_files=['bar/.gitnested', 'bar/FirstBar', 'bar/SecondBar'],
    )

    # Do the nested push
    result = cmd_git_nested('push bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (foo-master)."

    # The pushed branch should be available in a bar workspace now
    result = env.run(['git', 'fetch'], cwd=env.workspace / 'bar')
    assert result.stdout.strip() == ""
    result = env.run(['git', 'checkout', 'foo-master'], cwd=env.workspace / 'bar')
    assert result.stdout.strip() == "branch 'foo-master' set up to track 'origin/foo-master'."

    assert_commit_count(env.workspace / 'bar', 7)  # 1 commit more
    bar_commits = (
        git_get_commit_msg(env.workspace / 'bar', args=['--topo-order', '--pretty=format:%H']).strip().splitlines()
    )
    assert bar_commits == [
        git_rev_parse(['HEAD'], cwd=env.workspace / 'bar'),
        git_rev_parse(['HEAD^2'], cwd=env.workspace / 'bar'),
        git_rev_parse(['HEAD^2^'], cwd=env.workspace / 'bar'),
        git_rev_parse(['HEAD~1'], cwd=env.workspace / 'bar'),  # same as HEAD^1
        git_rev_parse(['HEAD~2'], cwd=env.workspace / 'bar'),
        git_rev_parse(['HEAD~3'], cwd=env.workspace / 'bar'),
        git_rev_parse(['HEAD~4'], cwd=env.workspace / 'bar'),
    ]
    assert_commit(
        env.workspace / 'bar',
        'HEAD',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        commit_title='git nested pull',
        changed_files=[],
    )
    assert_commit(
        env.workspace / 'bar',
        'HEAD~1',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        commit_title='modified file: bar/Bar',
        changed_files=['Bar'],
    )
    assert_commit(
        env.workspace / 'bar',
        'HEAD^2',
        author_name='BarUser',
        author_email='bar@bar',
        committer_name='BarUser',
        committer_email='bar@bar',
        commit_title='add new file: SecondBar',
        changed_files=['SecondBar'],
    )
    assert_commit(
        env.workspace / 'bar',
        'HEAD~2',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        commit_title='add new file: bar/FooBar',
        changed_files=['FooBar'],
    )
    assert_commit(
        env.workspace / 'bar',
        'HEAD^2^',
        author_name='BarUser',
        author_email='bar@bar',
        committer_name='BarUser',
        committer_email='bar@bar',
        commit_title='add new file: FirstBar',
        changed_files=['FirstBar'],
    )

    # Make more commits in foo repo
    env.add_new_files('bar/FooBar2', cwd=env.workspace / 'foo')
    env.modify_files('bar/FooBar', cwd=env.workspace / 'foo')
    assert_commit_count(env.workspace / 'foo', 7)  # 2 more commits

    # Make more commits in bar repo (on foo-master branch)
    env.add_new_files('ThirdBar', cwd=env.workspace / 'bar')
    env.modify_files('SecondBar', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')
    assert_commit_count(env.workspace / 'bar', 9)  # 2 more commits

    # push should warn that there are changes upstream
    result = cmd_git_nested('push bar', cwd=env.workspace / 'foo', check=False)
    assert result.stdout.strip() == ''
    assert result.stderr.strip() == "git-nested: There are new changes upstream (foo-master), you need to pull first."

    # Do the nested pull as suggested
    result = cmd_git_nested('pull bar --branch foo-master', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pulled from '{env.upstream}/bar' (foo-master)."

    # Ensure that the changes from bar are correctly pulled
    assert (env.workspace / 'foo' / 'bar' / 'ThirdBar').exists()
    assert_commit_count(env.workspace / 'foo', 8)  # 1 commits is added
    assert_commit(
        env.workspace / 'foo',
        'HEAD',
        author_name='FooUser',
        author_email='foo@foo',
        committer_name='FooUser',
        committer_email='foo@foo',
        commit_title='git nested pull',
        changed_files=['bar/.gitnested', 'bar/SecondBar', 'bar/ThirdBar'],
    )

    # Do the nested push (should work without --force as only new commits should be added)
    result = cmd_git_nested('push bar', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == f"Nested repository 'bar' pushed to '{env.upstream}/bar' (foo-master)."


def test_consumer_with_filter(foo_bar_cloned):
    """Test basic nested push functionality"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    env.add_new_files('subdirA/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirA/otherfile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/otherfile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/somefile', cwd=env.workspace / 'leg')
    env.add_new_files('subdirC/otherfile', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    # count commits
    assert_commit_count(env.workspace / 'foo', 1)
    assert_commit_count(env.workspace / 'leg', 6)

    # add nested repository leg
    cmd_git_nested(f'clone {env.upstream}/leg leg --filter=subdirA --filter=subdirC', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'leg' / 'subdirA').exists()
    assert not (env.workspace / 'foo' / 'leg' / 'subdirB').exists()
    assert (env.workspace / 'foo' / 'leg' / 'subdirC').exists()

    # add nested repository leg
    env.add_new_files('leg/subdirA/somefile', cwd=env.workspace / 'foo')
    cmd_git_nested('push leg --branch master', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'leg' / 'subdirA').exists()
    assert not (env.workspace / 'foo' / 'leg' / 'subdirB').exists()
    assert (env.workspace / 'foo' / 'leg' / 'subdirC').exists()

    # add nested repository leg
    env.run(['git', 'pull'], cwd=env.workspace / 'leg')
    env.add_new_files('subdirA/file3', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')

    cmd_git_nested('pull leg', cwd=env.workspace / 'foo')
    assert (env.workspace / 'foo' / 'leg' / 'subdirA').exists()
    assert not (env.workspace / 'foo' / 'leg' / 'subdirB').exists()
    assert (env.workspace / 'foo' / 'leg' / 'subdirC').exists()
