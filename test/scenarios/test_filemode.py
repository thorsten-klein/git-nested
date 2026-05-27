"""Tests that file permissions (executable bit) are preserved through pull/push"""

import os
import stat

from conftest import assert_commit_count, clone_repo, cmd_git_nested, create_upstream_repo


def _is_executable(path):
    return bool(os.stat(path).st_mode & stat.S_IXUSR)


def test_filemode_preserved_through_pull_and_push(foo_bar_cloned):
    """Executable bit on a file must round-trip through git nested clone/push/pull"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo(str(env.upstream / 'leg'), env.workspace / 'leg')

    # Create an executable script and a regular file in the upstream nested repo
    leg = env.workspace / 'leg'
    (leg / 'run.sh').write_text("#!/bin/sh\necho hi\n")
    os.chmod(leg / 'run.sh', 0o755)
    (leg / 'data.txt').write_text("plain\n")
    os.chmod(leg / 'data.txt', 0o644)
    env.run(['git', 'add', 'run.sh', 'data.txt'], cwd=leg)
    env.run(['git', 'commit', '-m', 'add executable run.sh and data.txt'], cwd=leg)
    env.run(['git', 'push'], cwd=leg)

    assert_commit_count(leg, 1)

    # Clone the nested repo into foo
    cmd_git_nested(f'clone {env.upstream}/leg leg', cwd=env.workspace / 'foo')

    foo_leg = env.workspace / 'foo' / 'leg'
    assert _is_executable(foo_leg / 'run.sh'), "run.sh should be executable after clone"
    assert not _is_executable(foo_leg / 'data.txt'), "data.txt should not be executable after clone"

    # Add an executable file inside foo/leg and toggle data.txt to executable, then push
    (foo_leg / 'build.sh').write_text("#!/bin/sh\necho build\n")
    os.chmod(foo_leg / 'build.sh', 0o755)
    os.chmod(foo_leg / 'data.txt', 0o755)
    env.run(['git', 'add', 'leg/build.sh', 'leg/data.txt'], cwd=env.workspace / 'foo')
    env.run(['git', 'commit', '-m', 'add executable build.sh and make data.txt executable'], cwd=env.workspace / 'foo')

    cmd_git_nested('push leg --branch master', cwd=env.workspace / 'foo')

    # Pull in the upstream working copy and verify modes survived the push
    env.run(['git', 'pull'], cwd=leg)
    assert _is_executable(leg / 'run.sh'), "run.sh should still be executable upstream after push"
    assert _is_executable(leg / 'build.sh'), "build.sh should be executable upstream after push"
    assert _is_executable(leg / 'data.txt'), "data.txt should now be executable upstream after push"

    # Make another upstream change (also executable) and pull back into foo
    (leg / 'deploy.sh').write_text("#!/bin/sh\necho deploy\n")
    os.chmod(leg / 'deploy.sh', 0o755)
    env.run(['git', 'add', 'deploy.sh'], cwd=leg)
    env.run(['git', 'commit', '-m', 'add executable deploy.sh'], cwd=leg)
    env.run(['git', 'push'], cwd=leg)

    cmd_git_nested('pull leg', cwd=env.workspace / 'foo')

    assert _is_executable(foo_leg / 'run.sh'), "run.sh should still be executable after pull"
    assert _is_executable(foo_leg / 'build.sh'), "build.sh should still be executable after pull"
    assert _is_executable(foo_leg / 'data.txt'), "data.txt should still be executable after pull"
    assert _is_executable(foo_leg / 'deploy.sh'), "deploy.sh should be executable after pull"
