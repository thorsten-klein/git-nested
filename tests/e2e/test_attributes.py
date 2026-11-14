"""Tests for the parent's .gitattributes and the files of a nested repo"""

from conftest import cmd_git_nested


def _parent_wants_crlf(env):
    """foo says: .bat files have CRLF in the working tree and LF in git."""
    foo = env.workspace / 'foo'
    # No newline at the end: the new rules must still start on a line of their own
    (foo / ".gitattributes").write_text("*.bat text eol=crlf")
    env.run(['git', 'add', '.gitattributes'], cwd=foo)
    env.run(['git', 'commit', '-qm', 'bat files'], cwd=foo)
    return foo


def _upstream_bat(env, name, data):
    """Commit `data` as it is to upstream bar."""
    bar = env.workspace / 'bar'
    (bar / name).write_bytes(data)
    env.run(['git', '-c', 'core.autocrlf=false', 'add', name], cwd=bar)
    env.run(['git', 'commit', '-qm', name], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)


def test_clone_keeps_crlf_files_as_upstream_has_them(foo_bar_cloned):
    env = foo_bar_cloned
    foo = _parent_wants_crlf(env)
    _upstream_bat(env, 'make.bat', b"echo hi\r\n")
    _upstream_bat(env, 'plain.bat', b"echo plain\n")

    result = cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], foo)

    assert "bar: .gitattributes keeps 2 files as upstream has them" in result.output
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).output == ''
    assert "/bar/make.bat -text" in (foo / '.gitattributes').read_text()
    # git would check this one out with CRLF. A submodule keeps it LF.
    assert "/bar/plain.bat -text" in (foo / '.gitattributes').read_text()
    assert (foo / 'bar' / 'plain.bat').read_bytes() == b"echo plain\n"
    assert env.run(['git', 'show', 'HEAD:bar/make.bat'], cwd=foo, text=False).stdout == b"echo hi\r\n"
    assert cmd_git_nested('verify bar', cwd=foo).returncode == 0


def test_pull_adds_rules_only_for_new_files(foo_bar_cloned):
    env = foo_bar_cloned
    foo = _parent_wants_crlf(env)
    _upstream_bat(env, 'make.bat', b"echo hi\r\n")
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], foo)
    _upstream_bat(env, 'make.bat', b"echo changed\r\n")
    _upstream_bat(env, 'new.bat', b"echo new\r\n")

    cmd_git_nested('pull bar', cwd=foo)

    rules = (foo / '.gitattributes').read_text()
    assert rules.count("/bar/make.bat -text") == 1
    assert "/bar/new.bat -text" in rules
    assert rules.count("# git-nested") == 1
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).output == ''


def test_a_file_name_with_special_characters(foo_bar_cloned):
    env = foo_bar_cloned
    foo = _parent_wants_crlf(env)
    _upstream_bat(env, 'my [x] file.bat', b"echo hi\r\n")

    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], foo)

    assert '"/bar/my \\\\[x] file.bat" -text' in (foo / '.gitattributes').read_text()
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).output == ''
