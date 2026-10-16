"""Tests for git nested repair"""

from conftest import assert_gitnested_field, cmd_git_nested, git_get_commit_msg, git_rev_parse

_NO_SYNC_POINT = (
    "git-nested: {subdir}: no sync point in HEAD's history to repair to; "
    "no commit with a parent of its own ever brought it in step with upstream"
)


def _squash_merge(env, branch):
    """Squash-merge branch into master, with a master commit of its own in between so it is no fast-forward."""
    foo = env.workspace / 'foo'
    env.run(['git', 'switch', 'master'], cwd=foo)
    env.add_new_files('on-master', cwd=foo)
    env.run(['git', 'merge', '--squash', branch], cwd=foo)
    env.run(['git', 'commit', '-m', f'squashed {branch}'], cwd=foo)
    env.run(['git', 'branch', '-D', branch], cwd=foo)
    # The nested branch the pull left behind was built from the history that is gone.
    cmd_git_nested('clean --all', cwd=foo)


def _push_upstream_change(env, file):
    """Commit file to upstream bar."""
    env.add_new_files(file, cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')


def _pull_on_feature_branch(env):
    """Pull bar on a new branch 'feature', after a commit of its own -- which is what the pull records as parent."""
    foo = env.workspace / 'foo'
    env.run(['git', 'switch', '-c', 'feature'], cwd=foo)
    env.add_new_files('before-pull', cwd=foo)
    _push_upstream_change(env, 'bar-feature')
    cmd_git_nested('pull bar', cwd=foo)


def test_repair_after_squash_merged_pull(foo_bar_cloned_and_nested):
    """A pull on a branch that was squash-merged leaves a parent only that branch had; repair finds the new one."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'

    _pull_on_feature_branch(env)
    env.add_new_files('foo-feature', cwd=foo)
    _squash_merge(env, 'feature')

    # Without repair the sync point is found, with a note
    found = cmd_git_nested('branch bar', cwd=foo)
    assert "'git nested repair bar' records it" in found.output
    cmd_git_nested('clean bar', cwd=foo)

    squash = git_rev_parse(['HEAD'], cwd=foo)
    parent = git_rev_parse(['HEAD^'], cwd=foo)
    result = cmd_git_nested('repair bar', cwd=foo)

    assert result.output.strip() == f"bar: sync point repaired, parent is now {parent}"
    assert_gitnested_field(foo / 'bar' / '.gitnested', parent=parent)
    assert git_get_commit_msg(foo).startswith("git nested repair")
    assert git_rev_parse(['HEAD^'], cwd=foo) == squash

    # The nested history can be rebuilt again, and both directions work.
    cmd_git_nested('branch bar', cwd=foo)
    cmd_git_nested('clean bar', cwd=foo)
    env.add_new_files('bar/from-foo', cwd=foo)
    cmd_git_nested('push bar', cwd=foo)
    env.run(['git', 'cat-file', '-e', 'foo-master:from-foo'], cwd=env.upstream / 'bar')
    _push_upstream_change(env, 'bar-after-repair')
    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'bar-after-repair').is_file()


def test_repair_after_squash_merged_clone(foo_bar_cloned):
    """A clone squash-merged from a branch hangs off the commit the squash was made on."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'

    env.run(['git', 'switch', '-c', 'feature'], cwd=foo)
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], foo)
    _squash_merge(env, 'feature')

    cmd_git_nested('repair bar', cwd=foo)

    assert_gitnested_field(foo / 'bar' / '.gitnested', parent=git_rev_parse(['HEAD~2'], cwd=foo))
    cmd_git_nested('branch bar', cwd=foo)


def test_repair_after_rebase(foo_bar_cloned_and_nested):
    """A rebase rewrites the pull; repair hangs the sync point off the rewritten one."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'

    _pull_on_feature_branch(env)
    env.run(['git', 'switch', 'master'], cwd=foo)
    env.add_new_files('on-master', cwd=foo)
    env.run(['git', 'switch', 'feature'], cwd=foo)
    env.run(['git', 'rebase', 'master'], cwd=foo)
    cmd_git_nested('clean bar', cwd=foo)

    cmd_git_nested('repair bar', cwd=foo)

    assert_gitnested_field(foo / 'bar' / '.gitnested', parent=git_rev_parse(['HEAD~2'], cwd=foo))
    cmd_git_nested('branch bar', cwd=foo)


def test_repair_leaves_a_reachable_parent_alone(foo_bar_cloned_and_nested):
    """Nothing is written or committed when the sync point is still part of the history."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    head = git_rev_parse(['HEAD'], cwd=foo)

    result = cmd_git_nested('repair bar', cwd=foo)

    assert result.output.strip() == "bar: the sync point is part of HEAD's history, nothing to repair"
    assert git_rev_parse(['HEAD'], cwd=foo) == head


def test_repair_without_a_parent(foo_bar_cloned):
    """A subdir turned into a nested repository with init has no sync point to repair."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    env.add_new_files('doc/readme', cwd=foo)
    cmd_git_nested('init doc', cwd=foo)

    result = cmd_git_nested('repair doc', cwd=foo)

    assert result.output.strip() == "doc: no sync point recorded, nothing to repair"


def test_repair_all(foo_bar_cloned_and_nested):
    """--all repairs every nested repository that needs it."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'

    _pull_on_feature_branch(env)
    _squash_merge(env, 'feature')

    result = cmd_git_nested('repair --all', cwd=foo)

    assert "bar: sync point repaired" in result.output
    cmd_git_nested('branch bar', cwd=foo)


def test_repair_with_a_message(foo_bar_cloned_and_nested):
    """-m replaces the generated commit message."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'

    _pull_on_feature_branch(env)
    _squash_merge(env, 'feature')

    cmd_git_nested(['repair', '-m', 'fix the bar sync point', 'bar'], cwd=foo)

    assert git_get_commit_msg(foo).strip() == 'fix the bar sync point'


def test_repair_with_nothing_to_hang_off(foo_bar_cloned_and_nested):
    """When the commit that brought the subdir in step is the root, there is no sync point to repair to."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.run(['git', 'switch', '--orphan', 'solo'], cwd=foo)
    env.run(['git', 'checkout', 'master', '--', '.'], cwd=foo)
    env.run(['git', 'commit', '-m', 'everything at once'], cwd=foo)

    result = cmd_git_nested('repair bar', cwd=foo, check=False)

    assert result.returncode != 0
    assert result.output.strip() == _NO_SYNC_POINT.format(subdir='bar')


def test_repair_when_upstream_never_came_in(foo_bar_cloned):
    """A parent set by hand on a subdir no pull ever brought in step has nothing to repair to."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    env.add_new_files('doc/readme', cwd=foo)
    cmd_git_nested('init doc', cwd=foo)
    cmd_git_nested(['config', 'doc', 'parent', '0' * 40], cwd=foo)
    env.run(['git', 'commit', '-m', 'set a parent by hand'], cwd=foo)

    result = cmd_git_nested('repair doc', cwd=foo, check=False)

    assert result.returncode != 0
    assert result.output.strip() == _NO_SYNC_POINT.format(subdir='doc')


def test_branch_without_a_sync_point_says_how_to_recover(foo_bar_cloned_and_nested):
    """When this history has no sync point at all, the error stays."""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.run(['git', 'switch', '--orphan', 'solo'], cwd=foo)
    env.run(['git', 'checkout', 'master', '--', '.'], cwd=foo)
    env.run(['git', 'commit', '-m', 'everything at once'], cwd=foo)

    result = cmd_git_nested('branch bar', cwd=foo, check=False)

    assert result.returncode == 1
    assert "is no longer an ancestor of HEAD" in result.output
