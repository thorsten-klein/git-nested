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

    assert "git-nested: bar: these submodules stay empty: sub; use --recurse-submodules to nest them" in (result.output)


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


def test_clone_recurse_submodules_leaves_an_excluded_one_out(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    _bar_with_a_submodule(env)

    cmd_git_nested(['clone', '--recurse-submodules', '--exclude', 'sub', (env.upstream / 'bar').as_posix()], foo)

    assert not (foo / 'bar' / 'sub').exists()


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


def _bump_the_submodule(env):
    """Give upstream foo a new commit, and make upstream bar pin it. Return that commit."""
    other = env.workspace / 'foo-other'
    env.run(['git', 'clone', '-q', (env.upstream / 'foo').as_posix(), other.as_posix()])
    env.add_new_files('FooNew', cwd=other)
    env.run(['git', 'push', '-q'], cwd=other)
    bar = env.workspace / 'bar'
    env.run(['git', 'pull', '-q'], cwd=bar / 'sub')
    env.run(['git', 'commit', '-qam', 'bump sub'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)
    return git_rev_parse(['HEAD'], cwd=bar / 'sub')


def test_pull_follows_a_submodule_that_upstream_moved(foo_bar_cloned):
    """A nested submodule moves to the commit upstream pins now."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    _bar_with_a_submodule(env)
    cmd_git_nested(['clone', '--recurse-submodules', (env.upstream / 'bar').as_posix()], foo)
    pinned = _bump_the_submodule(env)

    cmd_git_nested('pull bar', cwd=foo)

    assert (foo / 'bar' / 'sub' / 'FooNew').is_file()
    assert_gitnested_field(foo / 'bar' / 'sub' / '.gitnested', commit=pinned)
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).output == ''


def test_push_keeps_the_submodule_of_upstream(foo_bar_cloned):
    """A push sends the submodule as the gitlink upstream had, not its files, and does not drop it."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    pinned = _bar_with_a_submodule(env)
    cmd_git_nested(['clone', '--recurse-submodules', (env.upstream / 'bar').as_posix()], foo)
    env.add_new_files('bar/from-foo', cwd=foo)

    cmd_git_nested('push -b master bar', cwd=foo)

    entry = env.run(['git', 'ls-tree', 'master', 'sub'], cwd=env.upstream / 'bar').output.split()
    assert entry[:3] == ['160000', 'commit', pinned]


# ============================================================================
# Inner nested repos keep their changes
# ============================================================================


def _nest_bar_with_sub(env):
    """Clone bar with its submodule 'sub' into foo, all nested. Return foo."""
    foo = env.workspace / 'foo'
    _bar_with_a_submodule(env)
    cmd_git_nested(['clone', '--recurse-submodules', (env.upstream / 'bar').as_posix()], foo)
    return foo


def _assert_no_gitlink(env, repo):
    modes = {line.split()[0] for line in env.run(['git', 'ls-files', '-s'], cwd=repo).output.splitlines()}
    assert '160000' not in modes


def _resolve_in_worktree(env, repo, output, file, text):
    """Fix a conflict where the help text says, and commit it there."""
    worktree = repo / next(line.split('cd ', 1)[1] for line in output.splitlines() if '1. cd ' in line)
    (worktree / file).write_text(text)
    env.run(['git', 'add', file], cwd=worktree)
    env.run(['git', 'commit', '-q', '--no-edit'], cwd=worktree)


def test_clone_recurse_submodules_commits_no_gitlink(foo_bar_cloned):
    env = foo_bar_cloned
    foo = _nest_bar_with_sub(env)

    for commit in env.run(['git', 'rev-list', 'HEAD'], cwd=foo).output.split():
        tree = env.run(['git', 'ls-tree', '-r', commit], cwd=foo).output
        assert '160000 commit' not in tree


def test_pull_keeps_changes_in_an_inner_nested_repo(foo_bar_cloned):
    env = foo_bar_cloned
    foo = _nest_bar_with_sub(env)
    env.modify_files('bar/sub/Foo', text='local', cwd=foo)
    pinned = _bump_the_submodule(env)

    cmd_git_nested('pull bar', cwd=foo)

    assert 'local' in (foo / 'bar' / 'sub' / 'Foo').read_text()
    assert (foo / 'bar' / 'sub' / 'FooNew').is_file()
    assert_gitnested_field(foo / 'bar' / 'sub' / '.gitnested', commit=pinned)
    _assert_no_gitlink(env, foo)


def test_pull_no_squash_keeps_changes_in_an_inner_nested_repo(foo_bar_cloned):
    env = foo_bar_cloned
    foo = _nest_bar_with_sub(env)
    env.modify_files('bar/sub/Foo', text='local', cwd=foo)
    _bump_the_submodule(env)

    cmd_git_nested('pull --no-squash bar', cwd=foo)

    assert 'local' in (foo / 'bar' / 'sub' / 'Foo').read_text()
    assert (foo / 'bar' / 'sub' / 'FooNew').is_file()
    _assert_no_gitlink(env, foo)


def test_pull_force_drops_changes_in_an_inner_nested_repo(foo_bar_cloned):
    """--force takes upstream as it is. --recurse-submodules nests sub again."""
    env = foo_bar_cloned
    foo = _nest_bar_with_sub(env)
    env.modify_files('bar/sub/Foo', text='local', cwd=foo)
    pinned = _bump_the_submodule(env)

    cmd_git_nested('pull --force --recurse-submodules bar', cwd=foo)

    assert 'local' not in (foo / 'bar' / 'sub' / 'Foo').read_text()
    assert_gitnested_field(foo / 'bar' / 'sub' / '.gitnested', commit=pinned)
    _assert_no_gitlink(env, foo)


def test_commit_after_a_conflict_keeps_inner_nested_repos(foo_bar_cloned):
    """You finish a pull by hand. sub stays nested. It moves to the new pin."""
    env = foo_bar_cloned
    foo = _nest_bar_with_sub(env)
    env.modify_files('bar/sub/Foo', text='local', cwd=foo)
    env.modify_files('bar/Bar', text='mine', cwd=foo)
    env.modify_files('Bar', text='theirs', cwd=env.workspace / 'bar')
    env.run(['git', 'push', '-q'], cwd=env.workspace / 'bar')
    pinned = _bump_the_submodule(env)

    result = cmd_git_nested('pull bar', cwd=foo, check=False)
    assert result.returncode == 1
    _resolve_in_worktree(env, foo, result.output, 'Bar', 'both\n')
    cmd_git_nested('commit bar', cwd=foo)

    assert (foo / 'bar' / 'Bar').read_text() == 'both\n'
    assert 'local' in (foo / 'bar' / 'sub' / 'Foo').read_text()
    assert_gitnested_field(foo / 'bar' / 'sub' / '.gitnested', commit=pinned)
    _assert_no_gitlink(env, foo)


def test_pull_again_after_a_conflict_in_an_inner_nested_repo(foo_bar_cloned):
    """The first inner repo stops on a conflict. A new pull updates the second one."""
    env = foo_bar_cloned
    bar = env.workspace / 'bar'
    _bar_with_a_submodule(env)
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', (env.upstream / 'foo').as_posix(), 'sub2'], cwd=bar)
    env.run(['git', 'commit', '-qm', 'add sub2'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)
    foo = env.workspace / 'foo'
    cmd_git_nested(['clone', '--recurse-submodules', (env.upstream / 'bar').as_posix()], foo)
    env.modify_files('bar/sub/Foo', text='local', cwd=foo)
    other = env.workspace / 'foo-other'
    env.run(['git', 'clone', '-q', (env.upstream / 'foo').as_posix(), other])
    env.modify_files('Foo', text='upstream', cwd=other)
    env.run(['git', 'push', '-q'], cwd=other)
    foo_upstream = git_rev_parse(['HEAD'], cwd=other)
    for path in ('sub', 'sub2'):
        env.run(['git', 'pull', '-q'], cwd=bar / path)
    env.run(['git', 'commit', '-qam', 'bump both'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)

    result = cmd_git_nested('pull bar', cwd=foo, check=False)

    assert result.returncode == 1
    assert "git nested pull bar" in result.output
    _resolve_in_worktree(env, foo, result.output, 'Foo', 'both\n')
    cmd_git_nested('commit bar/sub', cwd=foo)
    cmd_git_nested('pull bar', cwd=foo)

    assert_gitnested_field(foo / 'bar' / 'sub' / '.gitnested', commit=foo_upstream)
    assert_gitnested_field(foo / 'bar' / 'sub2' / '.gitnested', commit=foo_upstream)
    _assert_no_gitlink(env, foo)
