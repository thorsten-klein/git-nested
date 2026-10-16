"""Tests for upstream repositories with submodules"""

from conftest import assert_gitnested_field, cmd_git_nested, git_rev_parse

ALLOW_FILE = ['-c', 'protocol.file.allow=always']


def _bar_with_a_submodule(env):
    """Give upstream bar a submodule 'sub', which is upstream foo. Return foo's commit."""
    bar = env.workspace / 'bar'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', (env.upstream / 'foo').as_posix(), 'sub'], cwd=bar)
    env.run(['git', 'commit', '-qm', 'add sub'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)
    return git_rev_parse(['HEAD'], cwd=bar / 'sub')


def test_clone_warns_about_submodules(foo_bar_cloned):
    """Without --recurse-submodules the submodules stay empty; say so."""
    env = foo_bar_cloned
    _bar_with_a_submodule(env)

    result = cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], env.workspace / 'foo')

    assert "git-nested: bar: these submodules stay empty: sub; clone with --recurse-submodules to nest them" in (
        result.output
    )


def test_clone_recurse_submodules_nests_them(foo_bar_cloned):
    """Each submodule becomes a nested repository, at the commit upstream pins."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    pinned = _bar_with_a_submodule(env)

    cmd_git_nested(['clone', '--recurse-submodules', (env.upstream / 'bar').as_posix()], foo)

    assert (foo / 'bar' / 'sub' / 'Foo').is_file()
    assert_gitnested_field(foo / 'bar' / 'sub' / '.gitnested', remote=(env.upstream / 'foo').as_posix(), commit=pinned)
    assert env.run(['git', 'ls-files', '-s', 'bar/sub'], cwd=foo).output.split()[0] != '160000'


def test_init_from_submodule(foo_bar_cloned):
    """A submodule of this repository becomes a nested repository, same commit and remote."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', (env.upstream / 'bar').as_posix(), 'lib'], cwd=foo)
    env.run(['git', 'commit', '-qm', 'add lib'], cwd=foo)
    pinned = git_rev_parse(['HEAD:lib'], cwd=foo)

    result = cmd_git_nested('init --from-submodule lib', cwd=foo)

    assert result.output.strip().endswith(f"lib: cloned from {(env.upstream / 'bar').as_posix()} ({pinned})")
    assert_gitnested_field(foo / 'lib' / '.gitnested', remote=(env.upstream / 'bar').as_posix(), commit=pinned)
    assert (foo / 'lib' / 'bard' / 'Bard').is_file()
    assert not (foo / '.gitmodules').exists() or 'lib' not in (foo / '.gitmodules').read_text()
    assert not (foo / '.git' / 'modules' / 'lib').exists()
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).output == ''


def test_a_submodule_without_url_stays_empty(foo_bar_cloned):
    """A gitlink that .gitmodules does not describe cannot be nested; say so."""
    env = foo_bar_cloned
    bar = env.workspace / 'bar'
    commit = git_rev_parse(['HEAD'], cwd=bar)
    env.run(['git', 'update-index', '--add', '--cacheinfo', f'160000,{commit},sub'], cwd=bar)
    env.run(['git', 'commit', '-qm', 'gitlink only'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)

    result = cmd_git_nested(['clone', '--recurse-submodules', (env.upstream / 'bar').as_posix()], env.workspace / 'foo')

    assert "git-nested: bar/sub: .gitmodules has no url for it, so it stays empty" in result.output


def test_init_from_submodule_refuses_a_directory(foo_bar_cloned):
    """Only a submodule can be turned into a nested repository this way."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    env.add_new_files('plain/file', cwd=foo)

    result = cmd_git_nested('init --from-submodule plain', cwd=foo, check=False)

    assert result.returncode == 1
    assert result.output.strip() == "git-nested: plain: is not a submodule"
