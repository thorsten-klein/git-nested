"""Running git-nested from below the top level of the repository"""

import os
import subprocess
from pathlib import Path

from conftest import cmd_git_nested

import git_nested


def _subject(cwd, rev='HEAD'):
    return subprocess.run(
        ['git', 'log', '-1', '--format=%s', rev], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_status_from_a_subdirectory(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    (env.workspace / 'foo' / 'deeper').mkdir()
    result = cmd_git_nested('status', cwd=env.workspace / 'foo' / 'deeper')
    assert "Git nested repository 'bar'" in result.output


def test_subdir_is_relative_to_the_current_directory(foo_bar_cloned):
    """Like a git pathspec: from ext/, 'lib' is ext/lib"""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    (foo / 'ext').mkdir()
    result = cmd_git_nested(['clone', (env.upstream / 'bar').as_posix(), 'lib'], cwd=foo / 'ext')
    assert result.output.startswith("ext/lib: cloned from")
    assert (foo / 'ext' / 'lib' / '.gitnested').is_file()

    # and a clone's guessed subdir lands in the current directory too
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], cwd=foo / 'ext')
    assert (foo / 'ext' / 'bar' / '.gitnested').is_file()

    result = cmd_git_nested('branch ../ext/lib', cwd=foo / 'ext')
    assert result.output.strip() == "ext/lib: branch nested/ext%2Flib created, worktree at .git/tmp/nested/ext%2Flib"


def test_the_enclosing_nested_repository_is_the_default_subdir(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.add_new_files('bar/inner/file', cwd=foo)

    result = cmd_git_nested('branch', cwd=foo / 'bar' / 'inner')
    assert result.output.strip() == "bar: branch nested/bar created, worktree at .git/tmp/nested/bar"

    cmd_git_nested(['run', '.', 'commit', '--allow-empty', '-m', 'from inside'], cwd=foo / 'bar')
    assert _subject(foo, 'nested/bar') == 'from inside'


def test_no_enclosing_nested_repository_still_asks_for_a_subdir(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    (env.workspace / 'foo' / 'plain').mkdir()
    (env.workspace / 'foo' / 'plain' / 'f').write_text('x')
    result = cmd_git_nested('branch', cwd=env.workspace / 'foo' / 'plain', check=False)
    assert result.returncode == 1
    assert "no subdir given, and none could be guessed" in result.output


def test_path_options_are_relative_to_the_current_directory(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    (foo / 'deeper').mkdir()
    (foo / 'deeper' / 'keep').write_text('x')

    result = cmd_git_nested(['branch', '-d', '../../wt', '../bar'], cwd=foo / 'deeper')
    assert result.output.strip().endswith(f"worktree at {(env.workspace / 'wt').as_posix()}")


def test_a_subdir_outside_the_repository_is_refused(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    (env.workspace / 'foo' / 'deeper').mkdir()
    (env.workspace / 'foo' / 'deeper' / 'keep').write_text('x')
    result = cmd_git_nested('branch ../../bar', cwd=env.workspace / 'foo' / 'deeper', check=False)
    assert result.returncode == 1
    assert "../../bar: outside the repository" in result.output


def test_the_previous_directory_is_restored(foo_bar_cloned_and_nested):
    """In-process callers keep their working directory"""
    env = foo_bar_cloned_and_nested
    deeper = env.workspace / 'foo' / 'deeper'
    deeper.mkdir()
    (deeper / 'keep').write_text('x')

    with git_nested.chdir(deeper):
        git_nested.GitNestedCommand().main(['-q', 'status'])
        assert Path.cwd() == deeper


def test_a_local_remote_is_relative_to_the_current_directory(foo_bar_cloned):
    """-r names the same repository from below the top level, and is stored relative to the top"""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    env.add_new_files('ext/lib/file', cwd=foo)
    remote = Path(os.path.relpath(env.upstream / 'bar', foo / 'ext')).as_posix()

    cmd_git_nested(['init', '-r', remote, '-b', 'master', 'lib'], cwd=foo / 'ext')

    expected = Path(os.path.relpath(env.upstream / 'bar', foo)).as_posix()
    assert cmd_git_nested(['config', 'ext/lib', 'remote'], cwd=foo).stdout.strip() == expected
    cmd_git_nested('fetch ext/lib', cwd=foo)


def test_a_remote_set_with_config_is_relative_to_the_current_directory(foo_bar_cloned_and_nested):
    """Also when the path does not exist yet; a URL is left alone"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    deeper = foo / 'deeper'
    deeper.mkdir()
    (deeper / 'keep').write_text('x')

    for typed, stored in [
        ('../not-yet', './not-yet'),
        ('../../elsewhere', '../elsewhere'),
        ('https://example.com/x.git', 'https://example.com/x.git'),
        ('git@example.com:x.git', 'git@example.com:x.git'),
    ]:
        cmd_git_nested(['config', '../bar', 'remote', typed], cwd=deeper)
        assert cmd_git_nested(['config', 'bar', 'remote'], cwd=foo).stdout.strip() == stored
        env.run(['git', 'checkout', '--', 'bar/.gitnested'], cwd=foo)


def test_an_absolute_subdir_is_still_refused(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    deeper = env.workspace / 'foo' / 'deeper'
    deeper.mkdir()
    (deeper / 'keep').write_text('x')
    result = cmd_git_nested(['branch', (env.workspace / 'foo' / 'bar').as_posix()], cwd=deeper, check=False)
    assert result.returncode == 1
    assert "subdir must be a relative path" in result.output


def test_a_message_file_is_relative_to_the_current_directory(env):
    """--file from inside the nested repository, whose subdir is implied"""
    env.clone_init()
    init_dir = env.workspace / 'init'
    cmd_git_nested(f'init doc -r {env.upstream.as_posix()}/bar -b master', cwd=init_dir)
    cmd_git_nested('branch doc', cwd=init_dir)
    (init_dir / 'msg.txt').write_text('message from a file one level up\n')

    cmd_git_nested('commit --fetch --force --file=../msg.txt', cwd=init_dir / 'doc')

    assert _subject(init_dir) == 'message from a file one level up'


def test_a_relative_upstream_is_relative_to_the_current_directory(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    (foo / 'ext').mkdir()
    upstream = Path(os.path.relpath(env.upstream / 'bar', foo / 'ext')).as_posix()

    result = cmd_git_nested(['clone', upstream, 'lib'], cwd=foo / 'ext')

    assert result.output.startswith("ext/lib: cloned from")
    expected = Path(os.path.relpath(env.upstream / 'bar', foo)).as_posix()
    assert cmd_git_nested(['config', 'ext/lib', 'remote'], cwd=foo).stdout.strip() == expected
