"""Tests for contributing back from nested submodules (#184).

Upstream bar has the submodule mid. mid has the submodule inner.
`submodules init --recursive` nests both. A branch or push of one of them
must carry its own changes only: no files of the other nested repos, no
.gitnested files, and no changes of the parent.
"""

import pytest
from conftest import clone_repo, cmd_git_nested, git_rev_parse

ALLOW_FILE = ['-c', 'protocol.file.allow=always']


def _make_mid(env):
    """Make upstream mid with the submodule inner, which is upstream foo."""
    url = env.upstream / 'mid'
    env.run(['git', 'init', '-q', '--bare', url])
    mid = env.workspace / 'mid'
    env.run(['git', 'clone', '-q', url, mid])
    (mid / 'Mid').write_text("mid\n")
    env.run(['git', 'add', 'Mid'], cwd=mid)
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', (env.upstream / 'foo').as_posix(), 'inner'], cwd=mid)
    env.run(['git', 'commit', '-qm', 'mid with inner'], cwd=mid)
    env.run(['git', 'push', '-q', 'origin', 'master'], cwd=mid)
    return url


@pytest.fixture
def fork(foo_bar_cloned):
    """A fork of bar, with mid and mid/inner nested, and one commit that changes all three."""
    env = foo_bar_cloned
    mid_url = _make_mid(env)
    bar = env.workspace / 'bar'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', mid_url.as_posix(), 'mid'], cwd=bar)
    env.run(['git', 'commit', '-qm', 'add mid'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)
    env.mid_tip = git_rev_parse(['HEAD'], cwd=env.workspace / 'mid')
    env.inner_pin = git_rev_parse(['HEAD:inner'], cwd=env.workspace / 'mid')
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    cmd_git_nested('submodules init --recursive', cwd=env.fork)

    fork = env.fork
    (fork / 'Bar').write_text("changed in the parent\n")
    (fork / 'mid' / 'Mid').write_text("changed in mid\n")
    (fork / 'mid' / 'new-in-mid').write_text("new in mid\n")
    (fork / 'mid' / 'inner' / 'Foo').write_text("changed in inner\n")
    (fork / 'mid' / 'inner' / 'new-in-inner').write_text("new in inner\n")
    env.run(['git', 'add', '-A'], cwd=fork)
    env.run(['git', 'commit', '-qm', 'change the parent, mid and inner at once'], cwd=fork)
    return env


def _tree(env, repo, rev):
    """{path: (mode, object)} of `rev` in `repo`."""
    entries = env.run(['git', 'ls-tree', '-r', '-z', rev], cwd=repo).output.split('\0')
    return {path: tuple(meta.split()[::2]) for meta, _, path in (e.partition('\t') for e in entries if e)}


def _changed(env, repo, old, new):
    return sorted(env.run(['git', 'diff', '--name-only', old, new], cwd=repo).output.split())


def _branch_name(output):
    """The branch that `git nested branch` says it created."""
    return output.split('branch ', 1)[1].split(' created', 1)[0]


def _assert_only_own_content(tree):
    """No files of other nested repos, and no .gitnested files."""
    assert not [path for path in tree if path.startswith('inner/')]
    assert not [path for path in tree if path.rsplit('/', 1)[-1].startswith('.gitnested')]
    assert 'Bar' not in tree


# ============================================================================
# git nested branch
# ============================================================================


def test_branch_of_mid_has_mid_changes_only(fork):
    env = fork
    result = cmd_git_nested('branch mid', cwd=env.fork)
    branch = _branch_name(result.output)

    tree = _tree(env, env.fork, branch)
    assert tree['inner'] == ('160000', env.inner_pin)
    _assert_only_own_content(tree)
    assert _changed(env, env.fork, env.mid_tip, branch) == ['Mid', 'new-in-mid']
    assert env.run(['git', 'merge-base', '--is-ancestor', env.mid_tip, branch], cwd=env.fork).returncode == 0


def test_branch_of_inner_has_inner_changes_only(fork):
    env = fork
    result = cmd_git_nested('branch mid/inner', cwd=env.fork)
    branch = _branch_name(result.output)

    tree = _tree(env, env.fork, branch)
    assert not [path for path in tree if path.rsplit('/', 1)[-1].startswith('.gitnested')]
    assert 'Mid' not in tree
    assert 'Bar' not in tree
    assert _changed(env, env.fork, env.inner_pin, branch) == ['Foo', 'new-in-inner']


def test_each_commit_of_the_branch_stays_inside_mid(fork):
    """A commit of the parent that changes nothing in mid is not on the branch."""
    env = fork
    (env.fork / 'Bar').write_text("parent only\n")
    env.run(['git', 'commit', '-qam', 'parent only'], cwd=env.fork)
    (env.fork / 'mid' / 'inner' / 'Foo').write_text("inner only\n")
    env.run(['git', 'commit', '-qam', 'inner only'], cwd=env.fork)

    branch = _branch_name(cmd_git_nested('branch mid', cwd=env.fork).output)

    commits = env.run(['git', 'rev-list', f'{env.mid_tip}..{branch}'], cwd=env.fork).output.split()
    assert commits
    for commit in commits:
        changed = env.run(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', commit], cwd=env.fork).output
        assert set(changed.split()) <= {'Mid', 'new-in-mid'}


# ============================================================================
# git nested push
# ============================================================================


def test_push_of_mid_sends_mid_changes_only(fork):
    env = fork
    cmd_git_nested('push -b master mid', cwd=env.fork)

    upstream = env.upstream / 'mid'
    tree = _tree(env, upstream, 'master')
    assert tree['inner'] == ('160000', env.inner_pin)
    _assert_only_own_content(tree)
    assert _changed(env, upstream, env.mid_tip, 'master') == ['Mid', 'new-in-mid']


def test_push_of_inner_sends_inner_changes_only(fork):
    env = fork
    cmd_git_nested('push -b master mid/inner', cwd=env.fork)

    upstream = env.upstream / 'foo'
    tree = _tree(env, upstream, 'master')
    assert not [path for path in tree if path.rsplit('/', 1)[-1].startswith('.gitnested')]
    assert 'Mid' not in tree
    assert _changed(env, upstream, env.inner_pin, 'master') == ['Foo', 'new-in-inner']


def test_push_of_mid_keeps_the_pin_of_inner(fork):
    """Pushing inner does not bump mid's gitlink. Only a pull of inner moves what mid pins."""
    env = fork
    cmd_git_nested('push -b master mid/inner', cwd=env.fork)

    cmd_git_nested('push -b master mid', cwd=env.fork)

    assert _tree(env, env.upstream / 'mid', 'master')['inner'] == ('160000', env.inner_pin)


def test_push_of_mid_after_a_pull_of_inner_bumps_the_pin(fork):
    """Push inner, pull it, then push mid: mid's gitlink moves to what inner pushed."""
    env = fork
    cmd_git_nested('push -b master mid/inner', cwd=env.fork)
    pushed = git_rev_parse(['master'], cwd=env.upstream / 'foo')
    cmd_git_nested('pull -b master mid/inner', cwd=env.fork)

    cmd_git_nested('push -b master mid', cwd=env.fork)

    upstream = env.upstream / 'mid'
    assert _tree(env, upstream, 'master')['inner'] == ('160000', pushed)
    assert _changed(env, upstream, env.mid_tip, 'master') == ['Mid', 'inner', 'new-in-mid']


def test_push_of_mid_with_a_kept_inner(foo_bar_cloned):
    """Without --recursive inner stays a submodule. A push of mid keeps its gitlink as it is."""
    env = foo_bar_cloned
    mid_url = _make_mid(env)
    bar = env.workspace / 'bar'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', mid_url.as_posix(), 'mid'], cwd=bar)
    env.run(['git', 'commit', '-qm', 'add mid'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)
    mid_tip = git_rev_parse(['HEAD'], cwd=env.workspace / 'mid')
    inner_pin = git_rev_parse(['HEAD:inner'], cwd=env.workspace / 'mid')
    fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), fork)
    cmd_git_nested('submodules init', cwd=fork)
    (fork / 'mid' / 'Mid').write_text("changed in mid\n")
    env.run(['git', 'commit', '-qam', 'change mid'], cwd=fork)

    cmd_git_nested('push -b master mid', cwd=fork)

    upstream = env.upstream / 'mid'
    tree = _tree(env, upstream, 'master')
    assert tree['inner'] == ('160000', inner_pin)
    _assert_only_own_content(tree)
    assert _changed(env, upstream, mid_tip, 'master') == ['Mid']
