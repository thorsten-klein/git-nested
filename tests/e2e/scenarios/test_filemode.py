"""Tests that file permissions (executable bit) are preserved through pull/push"""

import stat
import subprocess
import sys

from conftest import assert_commit_count, clone_repo, cmd_git_nested, create_upstream_repo

# A Windows checkout has no executable bit on disk; git keeps it in the index
# only. So the mode git records is checked everywhere, the file on disk only
# where it can carry the bit.
WINDOWS = sys.platform == 'win32'


def _is_executable(path):
    staged = subprocess.run(
        ['git', 'ls-files', '--stage', '--', path.name], cwd=path.parent, capture_output=True, text=True, check=True
    ).stdout
    in_index = staged.startswith('100755')
    return in_index if WINDOWS else in_index and bool(path.stat().st_mode & stat.S_IXUSR)


def _make_executable(env, repo, *paths):
    """chmod +x the files and record that in the index -- which on Windows only the latter does."""
    for path in paths:
        (repo / path).chmod(0o755)
    env.run(['git', 'update-index', '--chmod=+x', *paths], cwd=repo)


def test_filemode_preserved_through_pull_and_push(foo_bar_cloned):
    """Executable bit on a file must round-trip through git nested clone/push/pull"""
    env = foo_bar_cloned

    create_upstream_repo(env.upstream / 'leg')
    clone_repo((env.upstream / 'leg').as_posix(), env.workspace / 'leg')

    # Create an executable script and a regular file in the upstream nested repo
    leg = env.workspace / 'leg'
    (leg / 'run.sh').write_text("#!/bin/sh\necho hi\n")
    (leg / 'data.txt').write_text("plain\n")
    (leg / 'data.txt').chmod(0o644)
    env.run(['git', 'add', 'run.sh', 'data.txt'], cwd=leg)
    _make_executable(env, leg, 'run.sh')
    env.run(['git', 'commit', '-m', 'add executable run.sh and data.txt'], cwd=leg)
    env.run(['git', 'push'], cwd=leg)

    assert_commit_count(leg, 1)

    # Clone the nested repo into foo
    cmd_git_nested(f'clone {env.upstream.as_posix()}/leg leg', cwd=env.workspace / 'foo')

    foo_leg = env.workspace / 'foo' / 'leg'
    assert _is_executable(foo_leg / 'run.sh'), "run.sh should be executable after clone"
    assert not _is_executable(foo_leg / 'data.txt'), "data.txt should not be executable after clone"

    # Add an executable file inside foo/leg and toggle data.txt to executable, then push
    (foo_leg / 'build.sh').write_text("#!/bin/sh\necho build\n")
    env.run(['git', 'add', 'leg/build.sh', 'leg/data.txt'], cwd=env.workspace / 'foo')
    _make_executable(env, env.workspace / 'foo', 'leg/build.sh', 'leg/data.txt')
    env.run(['git', 'commit', '-m', 'add executable build.sh and make data.txt executable'], cwd=env.workspace / 'foo')

    cmd_git_nested('push leg --branch master', cwd=env.workspace / 'foo')

    # Pull in the upstream working copy and verify modes survived the push
    env.run(['git', 'pull'], cwd=leg)
    assert _is_executable(leg / 'run.sh'), "run.sh should still be executable upstream after push"
    assert _is_executable(leg / 'build.sh'), "build.sh should be executable upstream after push"
    assert _is_executable(leg / 'data.txt'), "data.txt should now be executable upstream after push"

    # Make another upstream change (also executable) and pull back into foo
    (leg / 'deploy.sh').write_text("#!/bin/sh\necho deploy\n")
    env.run(['git', 'add', 'deploy.sh'], cwd=leg)
    _make_executable(env, leg, 'deploy.sh')
    env.run(['git', 'commit', '-m', 'add executable deploy.sh'], cwd=leg)
    env.run(['git', 'push'], cwd=leg)

    cmd_git_nested('pull leg', cwd=env.workspace / 'foo')

    assert _is_executable(foo_leg / 'run.sh'), "run.sh should still be executable after pull"
    assert _is_executable(foo_leg / 'build.sh'), "build.sh should still be executable after pull"
    assert _is_executable(foo_leg / 'data.txt'), "data.txt should still be executable after pull"
    assert _is_executable(foo_leg / 'deploy.sh'), "deploy.sh should be executable after pull"
