"""Tests for `git nested submodules` (#184).

Upstream bar is the superproject. Its submodules become nested repos.
"""

import pytest
from conftest import assert_gitnested_field, clone_repo, cmd_git_nested, git_rev_parse

ALLOW_FILE = ['-c', 'protocol.file.allow=always']


@pytest.fixture
def fork(foo_bar_cloned):
    """Fork bar and nest its submodule 'sub'."""
    env = foo_bar_cloned
    _upstream_adds_submodule(env, env.upstream / 'foo', 'sub')
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    cmd_git_nested('init --from-submodule sub', cwd=env.fork)
    return env


# ============================================================================
# Helpers: changes in upstream
# ============================================================================


def _push_bar(env, message):
    bar = env.workspace / 'bar'
    env.run(['git', 'commit', '-qam', message], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)
    return git_rev_parse(['HEAD'], cwd=bar)


def _upstream_adds_submodule(env, url, path):
    """Add a submodule to upstream bar. Return its pin."""
    bar = env.workspace / 'bar'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', url.as_posix(), path], cwd=bar)
    _push_bar(env, f'add {path}')
    return git_rev_parse(['HEAD'], cwd=bar / path)


def _upstream_commit(env, name):
    """Commit a new file in upstream bar. Return the commit."""
    env.add_new_files(name, cwd=env.workspace / 'bar')
    env.run(['git', 'push', '-q'], cwd=env.workspace / 'bar')
    return git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')


def _upstream_bumps_sub(env):
    """Make upstream bar pin a new foo commit. Return it."""
    env.add_new_files('FooNew', cwd=env.workspace / 'foo')
    env.run(['git', 'push', '-q'], cwd=env.workspace / 'foo')
    env.run(['git', 'pull', '-q'], cwd=env.workspace / 'bar' / 'sub')
    _push_bar(env, 'bump sub')
    return git_rev_parse(['HEAD'], cwd=env.workspace / 'bar' / 'sub')


def _make_mid(env):
    """Make upstream mid. It has the submodule 'inner'. Return its url."""
    url = env.upstream / 'mid'
    env.run(['git', 'init', '-q', '--bare', url])
    mid = env.workspace / 'mid'
    env.run(['git', 'clone', '-q', url, mid])
    env.add_new_files('Mid', cwd=mid)
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', (env.upstream / 'foo').as_posix(), 'inner'], cwd=mid)
    env.run(['git', 'commit', '-qm', 'add inner'], cwd=mid)
    env.run(['git', 'push', '-q', 'origin', 'master'], cwd=mid)
    return url


def _update(env, *args, check=True):
    return cmd_git_nested(['submodules', 'update', *args], env.fork, check=check)


def _fetch_and_update(env, *args, remote='origin', check=True):
    """Fetch `remote`, then update to its master."""
    env.run(['git', 'fetch', '-q', remote], cwd=env.fork)
    return _update(env, f'{remote}/master', *args, check=check)


# ============================================================================
# Helpers: checks
# ============================================================================


def _assert_flat(env, repo):
    """No submodules and no leftovers."""
    modes = [line.split()[0] for line in env.run(['git', 'ls-files', '-s'], cwd=repo).output.splitlines()]
    assert '160000' not in modes
    assert not (repo / '.gitmodules').exists()
    assert not list(repo.glob('*~*'))
    assert env.run(['git', 'status', '--porcelain'], cwd=repo).output == ''


def _is_ancestor(env, repo, commit):
    return env.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=repo, check=False).returncode == 0


def _top_dirs_per_commit(env, repo, base):
    """The top dirs that each commit after base changed, sorted. .gitmodules does not count."""
    commits = env.run(['git', 'rev-list', f'{base}..HEAD'], cwd=repo).output.split()
    changed = [env.run(['git', 'diff', '--name-only', f'{c}^', c], cwd=repo).output.split() for c in commits]
    dirs = [{path.split('/')[0] for path in paths if path != '.gitmodules'} for paths in changed]
    return sorted(dirs, key=sorted)


def _last_update(env, repo):
    return env.run(['git', 'rev-list', '--merges', '-1', 'HEAD'], cwd=repo).output.strip()


# ============================================================================
# submodules init
# ============================================================================


def test_init_nests_all_submodules(foo_bar_cloned):
    env = foo_bar_cloned
    sub = _upstream_adds_submodule(env, env.upstream / 'foo', 'sub')
    lib = _upstream_adds_submodule(env, env.upstream / 'foo', 'ext/lib')
    tip = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')
    repo = env.workspace / 'repo'
    clone_repo((env.upstream / 'bar').as_posix(), repo)

    cmd_git_nested('submodules init', cwd=repo)

    assert_gitnested_field(repo / 'sub' / '.gitnested', commit=sub)
    assert_gitnested_field(repo / 'ext' / 'lib' / '.gitnested', commit=lib)
    assert _top_dirs_per_commit(env, repo, tip) == [{'ext'}, {'sub'}]
    _assert_flat(env, repo)


def test_init_nests_submodules_of_submodules(foo_bar_cloned):
    env = foo_bar_cloned
    _upstream_adds_submodule(env, _make_mid(env), 'mid')
    repo = env.workspace / 'repo'
    clone_repo((env.upstream / 'bar').as_posix(), repo)

    cmd_git_nested('submodules init --recursive', cwd=repo)

    assert (repo / 'mid' / 'inner' / 'Foo').is_file()
    assert (repo / 'mid' / 'inner' / '.gitnested').is_file()
    _assert_flat(env, repo)


def test_init_without_recursive_leaves_deeper_submodules(foo_bar_cloned):
    env = foo_bar_cloned
    _upstream_adds_submodule(env, _make_mid(env), 'mid')
    repo = env.workspace / 'repo'
    clone_repo((env.upstream / 'bar').as_posix(), repo)

    result = cmd_git_nested('submodules init', cwd=repo)

    assert_gitnested_field(repo / 'mid' / '.gitnested', submodules='keep')
    assert _gitlinks(env, repo) == ['mid/inner']
    assert 'mid: these submodules stay empty: inner; use --recursive to nest them' in result.output


def test_init_recursive_writes_nest(foo_bar_cloned):
    env = foo_bar_cloned
    _upstream_adds_submodule(env, _make_mid(env), 'mid')
    repo = env.workspace / 'repo'
    clone_repo((env.upstream / 'bar').as_posix(), repo)

    cmd_git_nested('submodules init --recursive', cwd=repo)

    assert_gitnested_field(repo / 'mid' / '.gitnested', submodules='nest')
    assert_gitnested_field(repo / 'mid' / 'inner' / '.gitnested', submodules='nest')
    assert 'mid: matches upstream' in cmd_git_nested('verify mid', cwd=repo).output


def _upstream_bumps_inner_of_mid(env):
    """Make upstream mid pin a new foo commit, and bar pin the new mid. Return the new inner pin."""
    env.add_new_files('FooNext', cwd=env.workspace / 'foo')
    env.run(['git', 'push', '-q'], cwd=env.workspace / 'foo')
    mid = env.workspace / 'mid'
    env.run(['git', *ALLOW_FILE, 'submodule', 'update', '-q', '--init', '--remote', 'inner'], cwd=mid)
    env.run(['git', 'commit', '-qam', 'bump inner'], cwd=mid)
    env.run(['git', 'push', '-q', 'origin', 'master'], cwd=mid)
    bar_mid = env.workspace / 'bar' / 'mid'
    env.run(['git', 'pull', '-q', 'origin', 'master'], cwd=bar_mid)
    _push_bar(env, 'bump mid')
    return git_rev_parse(['HEAD:inner'], cwd=mid)


def test_update_keeps_a_deeper_submodule_as_init_left_it(foo_bar_cloned):
    env = foo_bar_cloned
    _upstream_adds_submodule(env, _make_mid(env), 'mid')
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    cmd_git_nested('submodules init', cwd=env.fork)
    pinned = _upstream_bumps_inner_of_mid(env)
    env.run(['git', 'fetch', '-q'], cwd=env.fork)
    preview = _update(env, 'origin/master', '--dry-run').output
    assert 'mid: would pull to' in preview
    assert 'mid/inner' not in preview

    _fetch_and_update(env)

    entry = env.run(['git', 'ls-tree', 'HEAD', 'mid/inner'], cwd=env.fork).output.split()
    assert entry[:3] == ['160000', 'commit', pinned]
    assert not (env.fork / 'mid' / 'inner' / '.gitnested').exists()


def test_a_new_submodule_follows_the_choice_of_the_others(fork):
    env = fork
    cmd_git_nested(['config', 'sub', 'submodules', 'keep'], cwd=env.fork)
    env.run(['git', 'commit', '-qam', 'keep the submodules of sub'], cwd=env.fork)
    _upstream_adds_submodule(env, _make_mid(env), 'mid')

    result = _fetch_and_update(env)

    assert_gitnested_field(env.fork / 'mid' / '.gitnested', submodules='keep')
    assert _gitlinks(env, env.fork) == ['mid/inner']
    assert "mid: these submodules stay empty: inner; its .gitnested says 'submodules: keep'" in result.output


def test_init_recursive_resolves_deeper_relative_urls_against_their_parent(foo_bar_cloned):
    """--resolve-relative is for the first level. Deeper, the url of the parent submodule counts."""
    env = foo_bar_cloned
    mid = env.workspace / 'mid'
    _make_mid(env)
    env.run(['git', 'submodule', 'set-url', 'inner', '../foo'], cwd=mid)
    env.run(['git', 'commit', '-qam', 'inner is relative'], cwd=mid)
    env.run(['git', 'push', '-q', 'origin', 'master'], cwd=mid)
    bar = env.workspace / 'bar'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', '../mid', 'mid'], cwd=bar)
    _push_bar(env, 'add mid')
    repo = env.workspace / 'repo'
    clone_repo((env.upstream / 'bar').as_posix(), repo)

    base = (env.upstream / 'bar').as_posix()
    cmd_git_nested(['submodules', 'init', '--recursive', '--resolve-relative', base], cwd=repo)

    assert_gitnested_field(repo / 'mid' / '.gitnested', remote=(env.upstream / 'mid').as_posix())
    assert_gitnested_field(repo / 'mid' / 'inner' / '.gitnested', remote=(env.upstream / 'foo').as_posix())
    _assert_flat(env, repo)


def test_init_without_submodules_changes_nothing(foo_bar_cloned):
    env = foo_bar_cloned
    repo = env.workspace / 'bar'
    head = git_rev_parse(['HEAD'], cwd=repo)

    result = cmd_git_nested('submodules init', cwd=repo)

    assert 'no submodules' in result.output
    assert git_rev_parse(['HEAD'], cwd=repo) == head


def _repo_with_three_submodules(env):
    """A clone of bar with the submodules sub, ext/lib and ext/more."""
    for path in ('sub', 'ext/lib', 'ext/more'):
        _upstream_adds_submodule(env, env.upstream / 'foo', path)
    repo = env.workspace / 'repo'
    clone_repo((env.upstream / 'bar').as_posix(), repo)
    return repo


def _gitlinks(env, repo):
    entries = env.run(['git', 'ls-files', '-s'], cwd=repo).output.splitlines()
    return sorted(entry.split('\t')[1] for entry in entries if entry.startswith('160000 '))


def test_init_nests_only_the_named_submodules(foo_bar_cloned):
    env = foo_bar_cloned
    repo = _repo_with_three_submodules(env)

    cmd_git_nested('submodules init --only ext/lib/', cwd=repo)

    assert (repo / 'ext' / 'lib' / '.gitnested').is_file()
    assert _gitlinks(env, repo) == ['ext/more', 'sub']
    paths = env.run(['git', 'config', '-f', '.gitmodules', '--get-regexp', 'path$'], cwd=repo).output.split()
    assert 'ext/more' in paths
    assert 'ext/lib' not in paths
    only = env.run(['git', 'config', '-f', '.gitmodules', 'nested.only'], cwd=repo).output.strip()
    assert only == 'ext/lib'


def test_init_nests_the_submodules_below_a_path(foo_bar_cloned):
    env = foo_bar_cloned
    repo = _repo_with_three_submodules(env)

    cmd_git_nested('submodules init --only ext', cwd=repo)

    assert (repo / 'ext' / 'lib' / '.gitnested').is_file()
    assert (repo / 'ext' / 'more' / '.gitnested').is_file()
    assert _gitlinks(env, repo) == ['sub']


def test_init_ignore_skips_the_submodules_below_a_path(foo_bar_cloned):
    env = foo_bar_cloned
    repo = _repo_with_three_submodules(env)

    cmd_git_nested('submodules init --ignore ext', cwd=repo)

    assert (repo / 'sub' / '.gitnested').is_file()
    assert _gitlinks(env, repo) == ['ext/lib', 'ext/more']


def test_init_paths_are_relative_to_the_current_directory(foo_bar_cloned):
    env = foo_bar_cloned
    repo = _repo_with_three_submodules(env)

    cmd_git_nested('submodules init --only more --only ../sub', cwd=repo / 'ext')

    assert (repo / 'ext' / 'more' / '.gitnested').is_file()
    assert _gitlinks(env, repo) == ['ext/lib']


def _partial_fork(env, *options):
    """Fork bar with sub, ext/lib and ext/more. init with `options`."""
    for path in ('sub', 'ext/lib', 'ext/more'):
        _upstream_adds_submodule(env, env.upstream / 'foo', path)
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    cmd_git_nested(['submodules', 'init', *options], cwd=env.fork)


def _module(env, key):
    return env.run(['git', 'config', '-f', '.gitmodules', key], cwd=env.fork, check=False).output.strip()


def test_update_keeps_a_new_submodule_that_init_ignores(foo_bar_cloned):
    env = foo_bar_cloned
    _partial_fork(env, '--ignore', 'ext')
    pinned = _upstream_adds_submodule(env, env.upstream / 'foo', 'ext/new')

    assert 'ext/new' not in _fetch_and_update(env, '--dry-run').output
    _fetch_and_update(env)

    assert _gitlinks(env, env.fork) == ['ext/lib', 'ext/more', 'ext/new']
    assert env.run(['git', 'ls-tree', 'HEAD', 'ext/new'], cwd=env.fork).output.split()[2] == pinned
    assert _module(env, 'submodule.ext/new.path') == 'ext/new'
    assert _module(env, 'nested.ignore') == 'ext'


def test_update_keeps_a_new_submodule_outside_of_only(foo_bar_cloned):
    env = foo_bar_cloned
    _partial_fork(env, '--only', 'sub')
    _upstream_adds_submodule(env, env.upstream / 'foo', 'other')

    _fetch_and_update(env)

    assert _gitlinks(env, env.fork) == ['ext/lib', 'ext/more', 'other']


def test_update_nests_a_new_submodule_that_init_selects(foo_bar_cloned):
    env = foo_bar_cloned
    _partial_fork(env, '--only', 'ext')
    _upstream_adds_submodule(env, env.upstream / 'foo', 'ext/new')

    _fetch_and_update(env)

    assert (env.fork / 'ext' / 'new' / '.gitnested').is_file()
    assert _gitlinks(env, env.fork) == ['sub']


def _set_url(env, path, url):
    bar = env.workspace / 'bar'
    env.run(['git', 'config', '-f', '.gitmodules', f'submodule.{path}.url', url], cwd=bar)
    _push_bar(env, f'new url for {path}')


def test_update_takes_a_new_url_of_a_kept_submodule(foo_bar_cloned):
    env = foo_bar_cloned
    _partial_fork(env, '--ignore', 'ext')
    (env.fork / '.gitmodules').write_text("# mine\n" + (env.fork / '.gitmodules').read_text())
    env.run(['git', 'commit', '-qam', 'my note in .gitmodules'], cwd=env.fork)
    _set_url(env, 'ext/lib', 'https://example.com/lib.git')

    _fetch_and_update(env)

    assert _module(env, 'submodule.ext/lib.url') == 'https://example.com/lib.git'
    assert '# mine' in (env.fork / '.gitmodules').read_text()
    assert _module(env, 'submodule.sub.url') == ''


def test_a_conflict_in_gitmodules_stops_and_continues(foo_bar_cloned):
    env = foo_bar_cloned
    _partial_fork(env, '--ignore', 'ext')
    env.run(['git', 'config', '-f', '.gitmodules', 'submodule.ext/lib.url', 'https://mine/lib.git'], cwd=env.fork)
    env.run(['git', 'commit', '-qam', 'my url'], cwd=env.fork)
    _set_url(env, 'ext/lib', 'https://theirs/lib.git')

    result = _fetch_and_update(env, check=False)

    assert 'the merge has conflicts in: .gitmodules' in result.output
    assert '# <<<<<<< HEAD' in (env.fork / '.gitmodules').read_text()
    assert env.run(['git', 'config', '-f', '.gitmodules', '--list'], cwd=env.fork).returncode == 0
    env.run(['git', 'checkout', '--ours', '.gitmodules'], cwd=env.fork)
    env.run(['git', 'add', '.gitmodules'], cwd=env.fork)
    _update(env, '--continue')
    assert _module(env, 'submodule.ext/lib.url') == 'https://mine/lib.git'
    assert env.run(['git', 'status', '--porcelain'], cwd=env.fork).output == ''


def test_update_follows_a_kept_submodule_that_upstream_moved(foo_bar_cloned):
    env = foo_bar_cloned
    _partial_fork(env, '--ignore', 'ext')
    bar = env.workspace / 'bar'
    env.run(['git', 'mv', 'ext/lib', 'ext/moved'], cwd=bar)
    env.run(['git', 'commit', '-qm', 'move ext/lib'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)

    _fetch_and_update(env)

    assert _gitlinks(env, env.fork) == ['ext/more', 'ext/moved']
    assert _module(env, 'submodule.ext/lib.path') == 'ext/moved'


def test_init_refuses_a_path_without_a_submodule(foo_bar_cloned):
    env = foo_bar_cloned
    repo = _repo_with_three_submodules(env)
    head = git_rev_parse(['HEAD'], cwd=repo)

    result = cmd_git_nested('submodules init --only sub --only nope', cwd=repo, check=False)

    assert result.returncode == 1
    assert 'nope: no submodule there' in result.output
    assert git_rev_parse(['HEAD'], cwd=repo) == head


def test_update_after_a_partial_init(foo_bar_cloned):
    """The nested one follows upstream. The other stays a submodule."""
    env = foo_bar_cloned
    _upstream_adds_submodule(env, env.upstream / 'foo', 'other')
    _upstream_adds_submodule(env, env.upstream / 'foo', 'sub')
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    cmd_git_nested('submodules init --only sub', cwd=env.fork)
    pinned = _upstream_bumps_sub(env)

    _fetch_and_update(env)

    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    assert _gitlinks(env, env.fork) == ['other']


# ============================================================================
# submodules update
# ============================================================================


def test_update_keeps_each_upstream_commit(fork):
    """Upstream commits keep their SHAs."""
    env = fork
    first = _upstream_commit(env, 'one')
    second = _upstream_commit(env, 'two')
    env.add_new_files('local', cwd=env.fork)

    _fetch_and_update(env)

    assert _is_ancestor(env, env.fork, first)
    assert git_rev_parse(['HEAD^2'], cwd=env.fork) == second
    assert (env.fork / 'two').is_file()
    _assert_flat(env, env.fork)


def _git_merge(env):
    """A plain git merge of upstream. It stops on the submodule."""
    env.run(['git', 'fetch', '-q'], cwd=env.fork)
    return env.run(['git', 'merge', '--no-edit', 'origin/master'], cwd=env.fork, check=False)


def test_update_during_a_git_merge_says_what_to_do(fork):
    env = fork
    _upstream_bumps_sub(env)
    assert _git_merge(env).returncode != 0

    result = _update(env, check=False)

    assert result.returncode == 1
    assert "a git merge is in progress. Run 'git merge --abort'." in result.output
    assert "'git nested submodules update <commit>'" in result.output


def test_update_moves_a_submodule_that_upstream_bumped(fork):
    env = fork
    pinned = _upstream_bumps_sub(env)

    _fetch_and_update(env)

    assert (env.fork / 'sub' / 'FooNew').is_file()
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    _assert_flat(env, env.fork)


def test_update_keeps_local_changes_in_a_submodule(fork):
    env = fork
    env.modify_files('sub/Foo', text='local', cwd=env.fork)
    _upstream_bumps_sub(env)

    _fetch_and_update(env)

    assert 'local' in (env.fork / 'sub' / 'Foo').read_text()
    assert (env.fork / 'sub' / 'FooNew').is_file()
    _assert_flat(env, env.fork)


def test_update_makes_one_commit_per_submodule(fork):
    """One commit per changed submodule after the merge."""
    env = fork
    _upstream_bumps_sub(env)
    _upstream_adds_submodule(env, env.upstream / 'foo', 'lib')

    _fetch_and_update(env)

    assert _top_dirs_per_commit(env, env.fork, _last_update(env, env.fork)) == [{'lib'}, {'sub'}]
    _assert_flat(env, env.fork)


def test_update_nests_a_new_submodule(fork):
    env = fork
    pinned = _upstream_adds_submodule(env, env.upstream / 'foo', 'lib')

    _fetch_and_update(env)

    assert (env.fork / 'lib' / 'Foo').is_file()
    assert_gitnested_field(env.fork / 'lib' / '.gitnested', remote=(env.upstream / 'foo').as_posix(), commit=pinned)
    _assert_flat(env, env.fork)


def test_update_nests_submodules_of_a_new_submodule(fork):
    env = fork
    _upstream_adds_submodule(env, _make_mid(env), 'mid')

    _fetch_and_update(env)

    assert (env.fork / 'mid' / 'Mid').is_file()
    assert (env.fork / 'mid' / '.gitnested').is_file()
    assert (env.fork / 'mid' / 'inner' / 'Foo').is_file()
    assert (env.fork / 'mid' / 'inner' / '.gitnested').is_file()
    _assert_flat(env, env.fork)


def test_update_removes_a_submodule_that_upstream_dropped(fork):
    """The fork's own nested repos stay."""
    env = fork
    cmd_git_nested(['clone', (env.upstream / 'foo').as_posix(), 'own'], env.fork)
    env.run(['git', 'rm', '-q', 'sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'drop sub')

    _fetch_and_update(env)

    assert not (env.fork / 'sub').exists()
    assert (env.fork / 'own' / '.gitnested').is_file()
    _assert_flat(env, env.fork)


def test_update_follows_a_moved_submodule(fork):
    """Local changes move along."""
    env = fork
    env.modify_files('sub/Foo', text='local', cwd=env.fork)
    (env.workspace / 'bar' / 'ext').mkdir()
    env.run(['git', 'mv', 'sub', 'ext/sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'move sub')

    _fetch_and_update(env)

    assert not (env.fork / 'sub').exists()
    assert 'local' in (env.fork / 'ext' / 'sub' / 'Foo').read_text()
    assert (env.fork / 'ext' / 'sub' / '.gitnested').is_file()
    _assert_flat(env, env.fork)


def test_update_keeps_a_real_submodule(foo_bar_cloned):
    """A submodule that the fork did not nest stays a submodule."""
    env = foo_bar_cloned
    _upstream_adds_submodule(env, env.upstream / 'foo', 'sub')
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    env.add_new_files('local', cwd=env.fork)
    pinned = _upstream_bumps_sub(env)

    _fetch_and_update(env)

    entry = env.run(['git', 'ls-tree', 'HEAD', 'sub'], cwd=env.fork).output.split()
    assert entry[:3] == ['160000', 'commit', pinned]
    assert not (env.fork / 'sub' / '.gitnested').exists()


def test_update_follows_a_new_url(fork):
    env = fork
    mirror = env.upstream / 'foo-mirror'
    env.run(['git', 'clone', '-q', '--bare', env.upstream / 'foo', mirror])
    env.run(['git', 'submodule', 'set-url', 'sub', mirror.as_posix()], cwd=env.workspace / 'bar')
    _push_bar(env, 'move sub to a mirror')

    _fetch_and_update(env)

    assert_gitnested_field(env.fork / 'sub' / '.gitnested', remote=mirror.as_posix())
    _assert_flat(env, env.fork)


def test_update_stops_on_a_conflict_and_continues(fork):
    """You fix other conflicts. Then --continue finishes."""
    env = fork
    env.modify_files('Bar', text='fork', cwd=env.fork)
    env.modify_files('Bar', text='upstream', cwd=env.workspace / 'bar')
    env.run(['git', 'push', '-q'], cwd=env.workspace / 'bar')
    pinned = _upstream_bumps_sub(env)

    result = _fetch_and_update(env, check=False)

    assert result.returncode == 1
    assert 'Bar' in result.output
    assert 'submodules update --continue' in result.output

    (env.fork / 'Bar').write_text('both\n')
    env.run(['git', 'add', 'Bar'], cwd=env.fork)
    _update(env, '--continue')

    assert _is_ancestor(env, env.fork, git_rev_parse(['origin/master'], cwd=env.fork))
    assert (env.fork / 'Bar').read_text() == 'both\n'
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    _assert_flat(env, env.fork)


def test_update_twice_changes_nothing(fork):
    env = fork
    _upstream_bumps_sub(env)
    _fetch_and_update(env)
    head = git_rev_parse(['HEAD'], cwd=env.fork)

    result = _fetch_and_update(env)

    assert 'already up to date' in result.output
    assert git_rev_parse(['HEAD'], cwd=env.fork) == head


# ============================================================================
# submodules update: stopping, aborting, errors
# ============================================================================


def _conflict_in_bar(env):
    """The fork and upstream change Bar. Upstream also bumps sub. Return the new pin."""
    env.modify_files('Bar', text='fork', cwd=env.fork)
    env.modify_files('Bar', text='upstream', cwd=env.workspace / 'bar')
    env.run(['git', 'push', '-q'], cwd=env.workspace / 'bar')
    return _upstream_bumps_sub(env)


def test_update_abort(fork):
    env = fork
    _conflict_in_bar(env)
    head = git_rev_parse(['HEAD'], cwd=env.fork)
    assert _fetch_and_update(env, check=False).returncode == 1

    result = _update(env, '--abort')

    assert 'aborted' in result.output
    assert git_rev_parse(['HEAD'], cwd=env.fork) == head
    assert env.run(['git', 'status', '--porcelain'], cwd=env.fork).output == ''
    assert 'stopped before' not in _fetch_and_update(env, check=False).output


def test_update_continue_after_the_merge_was_aborted(fork):
    """--continue does not update submodules for a merge that is gone."""
    env = fork
    _conflict_in_bar(env)
    _fetch_and_update(env, check=False)
    env.run(['git', 'merge', '--abort'], cwd=env.fork)
    before = (env.fork / 'sub' / '.gitnested').read_text()

    result = _update(env, '--continue', check=False)

    assert result.returncode == 1
    assert 'submodules update --abort' in result.output
    assert (env.fork / 'sub' / '.gitnested').read_text() == before


def test_update_from_a_repo_without_common_history(fork):
    env = fork

    env.run(['git', 'fetch', '-q', env.upstream / 'foo', 'master'], cwd=env.fork)

    result = _update(env, 'FETCH_HEAD', check=False)

    assert result.returncode == 1
    assert 'has no history in common with this branch' in result.output


def test_a_failed_merge_leaves_nothing_to_continue(fork):
    """An untracked file is where upstream adds one. git does not merge."""
    env = fork
    _upstream_commit(env, 'one')
    (env.fork / 'one').write_text('mine\n')
    result = _fetch_and_update(env, check=False)
    assert result.returncode == 1
    assert 'the merge of origin/master failed' in result.output
    (env.fork / 'one').unlink()

    tip = _upstream_commit(env, 'two')
    _fetch_and_update(env)

    assert _is_ancestor(env, env.fork, tip)


def test_continue_or_abort_without_a_pull(fork):
    env = fork
    assert _update(env, '--continue', check=False).returncode == 1
    assert _update(env, '--abort', check=False).returncode == 1


def test_update_on_a_detached_head(fork):
    env = fork
    env.run(['git', 'checkout', '-q', '--detach'], cwd=env.fork)

    result = _fetch_and_update(env, check=False)

    assert result.returncode == 1
    assert 'detached' in result.output


def test_update_signoff(fork):
    env = fork
    _upstream_commit(env, 'one')

    _fetch_and_update(env, '--signoff')

    message = env.run(['git', 'log', '-1', '--format=%B', _last_update(env, env.fork)], cwd=env.fork).output
    assert 'Signed-off-by:' in message


def test_update_warns_about_changes_in_a_dropped_submodule(fork):
    env = fork
    env.modify_files('sub/Foo', text='local', cwd=env.fork)
    env.run(['git', 'rm', '-q', 'sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'drop sub')

    result = _fetch_and_update(env)

    assert 'sub: your changes in it go too' in result.output
    assert not (env.fork / 'sub').exists()


def test_update_keeps_a_moved_submodule_if_the_path_is_taken(fork):
    """The fork has its own ext/sub. sub stays where it is."""
    env = fork
    env.add_new_files('ext/sub/mine', cwd=env.fork)
    (env.workspace / 'bar' / 'ext').mkdir()
    env.run(['git', 'mv', 'sub', 'ext/sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'move sub')

    result = _fetch_and_update(env)

    assert 'that path is taken' in result.output
    assert 'ext/sub: the path is taken' in result.output
    assert (env.fork / 'sub' / '.gitnested').is_file()
    assert (env.fork / 'ext' / 'sub' / 'mine').is_file()


# ============================================================================
# submodules init: errors and relative urls
# ============================================================================


def test_init_needs_a_clean_tree(foo_bar_cloned):
    env = foo_bar_cloned
    _upstream_adds_submodule(env, env.upstream / 'foo', 'sub')
    repo = env.workspace / 'bar'
    (repo / 'Bar').write_text('changed\n')

    result = cmd_git_nested('submodules init', cwd=repo, check=False)

    assert result.returncode == 1
    assert 'changes' in result.output


def test_relative_urls_in_a_fork(foo_bar_cloned):
    """The fork lives somewhere else. Relative urls point to the project it forked."""
    env = foo_bar_cloned
    bar = env.workspace / 'bar'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', '../foo', 'sub'], cwd=bar)
    _push_bar(env, 'add sub')
    forks = env.tmp / 'forks'
    env.run(['git', 'clone', '-q', '--bare', env.upstream / 'bar', forks / 'bar'])
    env.fork = env.workspace / 'fork'
    clone_repo((forks / 'bar').as_posix(), env.fork)
    env.run(['git', 'remote', 'add', 'upstream', env.upstream / 'bar'], cwd=env.fork)
    cmd_git_nested(['submodules', 'init', '--resolve-relative', (env.upstream / 'bar').as_posix()], cwd=env.fork)
    pinned = _upstream_bumps_sub(env)
    _fetch_and_update(env, remote='upstream')

    remote = (env.upstream / 'foo').as_posix()
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', remote=remote, commit=pinned)
    _assert_flat(env, env.fork)


# ============================================================================
# submodules update <commit>
# ============================================================================


def test_update_a_fetched_branch(fork):
    env = fork
    pinned = _upstream_bumps_sub(env)
    tip = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')
    env.run(['git', 'fetch', '-q'], cwd=env.fork)

    _update(env, 'origin/master')

    assert _is_ancestor(env, env.fork, tip)
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    _assert_flat(env, env.fork)


def test_update_a_tag(fork):
    env = fork
    pinned = _upstream_bumps_sub(env)
    env.run(['git', 'tag', 'v2'], cwd=env.workspace / 'bar')
    env.run(['git', 'push', '-q', 'origin', 'v2'], cwd=env.workspace / 'bar')
    _upstream_commit(env, 'after-v2')
    env.run(['git', 'fetch', '-q', '--tags'], cwd=env.fork)

    _update(env, 'v2')

    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    assert not (env.fork / 'after-v2').exists()
    _assert_flat(env, env.fork)


def test_update_does_not_fetch(fork):
    env = fork
    _upstream_commit(env, 'one')

    result = _update(env, 'origin/master')

    assert 'already up to date' in result.output


def test_update_needs_a_known_commit(fork):
    env = fork

    result = _update(env, 'nope', check=False)

    assert result.returncode == 1
    assert 'nope: no such commit. Fetch it first.' in result.output


def test_update_resolves_relative_urls_against_the_remote_of_the_ref(foo_bar_cloned):
    env = foo_bar_cloned
    bar = env.workspace / 'bar'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', '../foo', 'sub'], cwd=bar)
    _push_bar(env, 'add sub')
    forks = env.tmp / 'forks'
    env.run(['git', 'clone', '-q', '--bare', env.upstream / 'bar', forks / 'bar'])
    env.fork = env.workspace / 'fork'
    clone_repo((forks / 'bar').as_posix(), env.fork)
    env.run(['git', 'remote', 'add', 'upstream', env.upstream / 'bar'], cwd=env.fork)
    cmd_git_nested(['submodules', 'init', '--resolve-relative', (env.upstream / 'bar').as_posix()], cwd=env.fork)
    _upstream_adds_submodule(env, env.upstream / 'foo', 'lib')
    env.run(['git', 'submodule', 'set-url', 'lib', '../foo'], cwd=bar)
    _push_bar(env, 'lib is relative')
    env.run(['git', 'fetch', '-q', 'upstream'], cwd=env.fork)

    _update(env, 'upstream/master')

    assert_gitnested_field(env.fork / 'lib' / '.gitnested', remote=(env.upstream / 'foo').as_posix())
    _assert_flat(env, env.fork)


# ============================================================================
# --dry-run and --single-commit
# ============================================================================


def test_update_dry_run_changes_nothing(fork):
    env = fork
    env.modify_files('sub/Foo', text='local', cwd=env.fork)
    _upstream_adds_submodule(env, env.upstream / 'foo', 'lib')
    env.run(['git', 'rm', '-q', 'sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'drop sub')
    head = git_rev_parse(['HEAD'], cwd=env.fork)

    result = _fetch_and_update(env, '--dry-run')

    assert 'would merge 2 commits of origin/master' in result.output
    assert 'lib: would nest at' in result.output
    assert 'sub: would remove (your changes in it go too' in result.output
    assert git_rev_parse(['HEAD'], cwd=env.fork) == head
    assert env.run(['git', 'status', '--porcelain'], cwd=env.fork).output == ''
    assert (env.fork / 'sub' / '.gitnested').is_file()
    assert _fetch_and_update(env).returncode == 0


def test_update_dry_run_shows_a_pull(fork):
    env = fork
    pinned = _upstream_bumps_sub(env)
    env.run(['git', 'fetch', '-q'], cwd=env.fork)

    result = _update(env, '--dry-run', 'origin/master')

    assert f'sub: would pull to {pinned[:12]}' in result.output


def test_single_commit(fork):
    """One merge commit holds the upstream commits and the submodule changes."""
    env = fork
    pinned = _upstream_bumps_sub(env)
    _upstream_adds_submodule(env, env.upstream / 'foo', 'lib')

    _fetch_and_update(env, '--single-commit')

    assert git_rev_parse(['HEAD'], cwd=env.fork) == _last_update(env, env.fork)
    message = env.run(['git', 'log', '-1', '--format=%B'], cwd=env.fork).output
    assert message.startswith('Merge')
    assert 'git nested' in message
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    assert (env.fork / 'lib' / '.gitnested').is_file()
    _assert_flat(env, env.fork)


def test_options_that_do_not_go_together(fork):
    env = fork
    for args in (['--continue', '--dry-run'], ['--abort', 'origin', 'master'], ['--continue', '--abort']):
        assert _fetch_and_update(env, *args, check=False).returncode == 1
    result = cmd_git_nested('submodules init --dry-run', cwd=env.fork, check=False)
    assert result.returncode == 1


# ============================================================================
# A shorter way through a conflict, and keeping a submodule back
# ============================================================================


def test_continue_finishes_a_conflict_inside_a_submodule(fork):
    """Fix the files where the message says, 'git add' them, then --continue. No 'git nested commit'."""
    env = fork
    env.modify_files('sub/Foo', text='local', cwd=env.fork)
    other = env.workspace / 'foo'
    env.modify_files('Foo', text='upstream', cwd=other)
    env.run(['git', 'push', '-q'], cwd=other)
    env.run(['git', 'pull', '-q'], cwd=env.workspace / 'bar' / 'sub')
    pinned = git_rev_parse(['HEAD'], cwd=other)
    _upstream_adds_submodule(env, env.upstream / 'foo', 'zlib')

    result = _fetch_and_update(env, check=False)

    assert result.returncode == 1
    assert 'submodules update --continue' in result.output
    worktree = env.fork / '.git' / 'tmp' / 'nested' / 'sub'
    (worktree / 'Foo').write_text('both\n')
    env.run(['git', 'add', 'Foo'], cwd=worktree)

    _update(env, '--continue')

    assert (env.fork / 'sub' / 'Foo').read_text() == 'both\n'
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    assert (env.fork / 'zlib' / '.gitnested').is_file()
    _assert_flat(env, env.fork)


def test_continue_says_which_conflicts_are_left(fork):
    env = fork
    env.modify_files('sub/Foo', text='local', cwd=env.fork)
    other = env.workspace / 'foo'
    env.modify_files('Foo', text='upstream', cwd=other)
    env.run(['git', 'push', '-q'], cwd=other)
    env.run(['git', 'pull', '-q'], cwd=env.workspace / 'bar' / 'sub')
    _push_bar(env, 'bump sub')
    _fetch_and_update(env, check=False)

    result = _update(env, '--continue', check=False)

    assert result.returncode == 1
    assert 'sub: fix the conflicts in' in result.output
    assert 'Foo' in result.output


def test_a_pinned_submodule_stays(fork):
    env = fork
    before = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar' / 'sub')
    cmd_git_nested(['config', 'sub', 'pin', before], env.fork)
    env.run(['git', 'commit', '-qm', 'keep sub'], cwd=env.fork)
    _upstream_bumps_sub(env)

    result = _fetch_and_update(env)

    assert f'sub: it has the pin {before}, so it stays' in result.output
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=before)
    assert not (env.fork / 'sub' / 'FooNew').exists()


# ============================================================================
# Less common paths
# ============================================================================


def test_wrong_arguments(fork):
    env = fork
    assert 'too many arguments' in cmd_git_nested('submodules init upstream', cwd=env.fork, check=False).output
    assert "--only only works with 'submodules init'" in _update(env, 'x', '--only', 'sub', check=False).output
    assert "--ignore only works with 'submodules init'" in _update(env, 'x', '--ignore', 'sub', check=False).output
    assert "--recursive only works with 'submodules init'" in _update(env, 'x', '--recursive', check=False).output
    result = _update(env, 'x', '--resolve-relative', 'y', check=False)
    assert "--resolve-relative only works with 'submodules init'" in result.output
    result = cmd_git_nested('submodules init --only sub --ignore sub', cwd=env.fork, check=False)
    assert "--only and --ignore can't be used together" in result.output
    assert "'submodules update' needs a commit" in _update(env, check=False).output
    assert 'too many arguments' in _update(env, 'a', 'b', check=False).output


def test_update_after_a_stop_needs_continue_or_abort(fork):
    env = fork
    _conflict_in_bar(env)
    _fetch_and_update(env, check=False)
    env.run(['git', 'merge', '--abort'], cwd=env.fork)

    result = _fetch_and_update(env, check=False)

    assert "A 'submodules update' stopped before." in result.output


def test_single_commit_without_submodule_changes(fork):
    env = fork
    _upstream_commit(env, 'one')

    _fetch_and_update(env, '--single-commit')

    assert git_rev_parse(['HEAD'], cwd=env.fork) == _last_update(env, env.fork)


def test_a_gitlink_without_url_stays_as_it_is(fork):
    env = fork
    bar = env.workspace / 'bar'
    commit = git_rev_parse(['HEAD'], cwd=bar)
    env.run(['git', 'update-index', '--add', '--cacheinfo', f'160000,{commit},nourl'], cwd=bar)
    env.run(['git', 'commit', '-qm', 'gitlink only'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)

    result = _fetch_and_update(env)

    assert 'nourl: .gitmodules has no url for it, so it stays as it is' in result.output
    _assert_flat(env, env.fork)


def test_a_teammates_clone_of_the_fork(fork):
    """A plain clone of the fork has no upstream objects of the nested repos. A pull works there too."""
    env = fork
    shared = env.tmp / 'shared-fork'
    # --no-local: copy only what a clone over the network gets
    env.run(['git', 'clone', '-q', '--bare', '--no-local', env.fork, shared])
    teammate = env.workspace / 'teammate'
    clone_repo(shared.as_posix(), teammate)
    env.run(['git', 'remote', 'add', 'upstream', env.upstream / 'bar'], cwd=teammate)
    env.modify_files('sub/Foo', text='mine', cwd=teammate)
    env.run(['git', 'rm', '-q', 'sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'drop sub')
    env.fork = teammate

    _fetch_and_update(env, remote='upstream')

    assert not (teammate / 'sub').exists()
    _assert_flat(env, teammate)


# ============================================================================
# The state file of a merge that stopped
# ============================================================================


def _state_file(env):
    return env.fork / '.git' / 'nested-submodules-update.json'


@pytest.mark.parametrize('text', ['not json', '{}', '{"base": "x", "target": "y", "url": ""}'])
def test_continue_with_a_broken_state_file(fork, text):
    env = fork
    _conflict_in_bar(env)
    _fetch_and_update(env, check=False)
    _state_file(env).write_text(text)

    result = _update(env, '--continue', check=False)

    assert result.returncode == 1
    assert 'is broken. Start over with --abort.' in result.output


def test_single_commit_after_a_conflict(fork):
    env = fork
    pinned = _conflict_in_bar(env)
    _fetch_and_update(env, '--single-commit', check=False)
    (env.fork / 'Bar').write_text('both\n')
    env.run(['git', 'add', 'Bar'], cwd=env.fork)

    _update(env, '--continue')

    assert git_rev_parse(['HEAD'], cwd=env.fork) == _last_update(env, env.fork)
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    _assert_flat(env, env.fork)


def test_single_commit_when_the_merge_commit_is_gone(fork):
    """You threw the merge away and moved to upstream itself. There is nothing to fold into."""
    env = fork
    _conflict_in_bar(env)
    _fetch_and_update(env, '--single-commit', check=False)
    env.run(['git', 'merge', '--abort'], cwd=env.fork)
    env.run(['git', 'reset', '-q', '--hard', 'origin/master'], cwd=env.fork)

    result = _update(env, '--continue', check=False)

    assert result.returncode == 1
    assert 'is gone' in result.output


def test_init_refuses_only_with_ignore(foo_bar_cloned):
    env = foo_bar_cloned
    repo = _repo_with_three_submodules(env)

    result = cmd_git_nested('submodules init --only sub --ignore ext', cwd=repo, check=False)

    assert result.returncode == 1
    assert "--only and --ignore can't be used together" in result.output


def test_init_resolves_relative_urls_only_when_asked(foo_bar_cloned):
    """A fork lives somewhere else. Its relative urls point to the project it forked."""
    env = foo_bar_cloned
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', '../foo', 'sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'add sub')
    forks = env.tmp / 'forks'
    env.run(['git', 'clone', '-q', '--bare', env.upstream / 'bar', forks / 'bar'])
    repo = env.workspace / 'fork'
    clone_repo((forks / 'bar').as_posix(), repo)

    result = cmd_git_nested('submodules init', cwd=repo, check=False)
    assert 'these submodules have a relative url: sub' in result.output
    assert 'Use --resolve-relative <url>' in result.output
    assert not (repo / 'sub' / '.gitnested').exists()

    cmd_git_nested(['submodules', 'init', '--resolve-relative', (env.upstream / 'bar').as_posix()], cwd=repo)
    assert_gitnested_field(repo / 'sub' / '.gitnested', remote=(env.upstream / 'foo').as_posix())


# ============================================================================
# Nested repos with patches
# ============================================================================

PATCHES = '.gitnested.patches'


def _commit(env, message):
    env.run(['git', 'add', '-A'], cwd=env.fork)
    env.run(['git', 'commit', '-q', '-m', message], cwd=env.fork)


def _with_patch(env, path='sub'):
    """Turn the patches on for `path`, change its Foo, and keep that change as a patch."""
    cmd_git_nested(['config', path, 'patches', PATCHES], cwd=env.fork)
    # bytes: write_text would make it CRLF on Windows
    (env.fork / path / 'Foo').write_bytes(b"local\n")
    _commit(env, 'local change')
    cmd_git_nested(['patches', 'create', path], cwd=env.fork)
    _commit(env, 'the patch')


def _verified(env, path='sub'):
    return cmd_git_nested(['patches', 'verify', path], cwd=env.fork).output.strip().endswith(" with 1 patch")


def _upstream_changes_foo(env, text):
    """Upstream foo changes Foo, and bar pins it. Return the pin."""
    foo = env.workspace / 'foo'
    (foo / 'Foo').write_bytes(text)
    env.run(['git', 'commit', '-qam', 'upstream Foo'], cwd=foo)
    env.run(['git', 'push', '-q'], cwd=foo)
    env.run(['git', 'pull', '-q'], cwd=env.workspace / 'bar' / 'sub')
    _push_bar(env, 'bump sub')
    return git_rev_parse(['HEAD'], cwd=foo)


def test_update_applies_the_patches_on_the_new_pin(fork):
    env = fork
    _with_patch(env)
    pinned = _upstream_bumps_sub(env)

    _fetch_and_update(env)

    assert (env.fork / 'sub' / 'Foo').read_text() == "local\n"
    assert (env.fork / 'sub' / 'FooNew').is_file()
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    assert _verified(env)
    _assert_flat(env, env.fork)


def test_update_drops_a_patch_upstream_has(fork):
    env = fork
    _with_patch(env)
    _upstream_changes_foo(env, b"local\n")

    _fetch_and_update(env)

    assert (env.fork / 'sub' / 'Foo').read_text() == "local\n"
    assert not list((env.fork / 'sub' / PATCHES).glob('*.patch'))
    _assert_flat(env, env.fork)


def test_continue_finishes_a_patch_that_does_not_apply(fork):
    env = fork
    _with_patch(env)
    pinned = _upstream_changes_foo(env, b"upstream\n")

    result = _fetch_and_update(env, check=False)

    assert result.returncode == 1
    assert "The patch 0001-TODO-title.patch does not apply." in result.output
    assert 'submodules update --continue' in result.output
    worktree = env.fork / '.git' / 'tmp' / 'nested' / 'sub'
    (worktree / 'Foo').write_bytes(b"upstream and local\n")
    env.run(['git', 'add', 'Foo'], cwd=worktree)

    _update(env, '--continue')

    assert (env.fork / 'sub' / 'Foo').read_text() == "upstream and local\n"
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    assert "+upstream and local" in (env.fork / 'sub' / PATCHES / '0001-TODO-title.patch').read_text()
    assert _verified(env)
    _assert_flat(env, env.fork)


def test_update_moves_the_patches_with_a_moved_submodule(fork):
    env = fork
    _with_patch(env)
    (env.workspace / 'bar' / 'ext').mkdir()
    env.run(['git', 'mv', 'sub', 'ext/sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'move sub')

    _fetch_and_update(env)

    assert (env.fork / 'ext' / 'sub' / 'Foo').read_text() == "local\n"
    assert _verified(env, 'ext/sub')
    _assert_flat(env, env.fork)


def test_update_warns_when_it_removes_a_submodule_with_patches(fork):
    env = fork
    _with_patch(env)
    env.run(['git', 'rm', '-q', 'sub'], cwd=env.workspace / 'bar')
    _push_bar(env, 'drop sub')

    result = _fetch_and_update(env)

    assert not (env.fork / 'sub').exists()
    assert 'sub' in result.output
    _assert_flat(env, env.fork)


def test_continue_finishes_a_rebase_that_stopped(fork):
    """Without patches, but with method rebase: the pull stops in a rebase."""
    env = fork
    cmd_git_nested(['config', 'sub', 'method', 'rebase'], cwd=env.fork)
    (env.fork / 'sub' / 'Foo').write_bytes(b"local\n")
    _commit(env, 'local change')
    pinned = _upstream_changes_foo(env, b"upstream\n")

    assert _fetch_and_update(env, check=False).returncode == 1
    worktree = env.fork / '.git' / 'tmp' / 'nested' / 'sub'
    (worktree / 'Foo').write_bytes(b"upstream and local\n")
    env.run(['git', 'add', 'Foo'], cwd=worktree)

    _update(env, '--continue')

    assert (env.fork / 'sub' / 'Foo').read_text() == "upstream and local\n"
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    _assert_flat(env, env.fork)


def test_continue_after_you_finished_the_patch_yourself(fork):
    env = fork
    _with_patch(env)
    _upstream_changes_foo(env, b"upstream\n")
    assert _fetch_and_update(env, check=False).returncode == 1
    worktree = env.fork / '.git' / 'tmp' / 'nested' / 'sub'
    (worktree / 'Foo').write_bytes(b"upstream and local\n")
    env.run(['git', 'add', 'Foo'], cwd=worktree)
    env.run(['git', '-c', 'core.editor=true', 'am', '--continue'], cwd=worktree)

    _update(env, '--continue')

    assert (env.fork / 'sub' / 'Foo').read_text() == "upstream and local\n"
    assert _verified(env)
    _assert_flat(env, env.fork)


def test_update_keeps_what_git_skips(fork):
    """git does not check out a submodule with `update = none`. update leaves it a submodule too."""
    env = fork
    _upstream_adds_submodule(env, env.upstream / 'foo', 'lib')
    _upstream_adds_submodule(env, env.upstream / 'foo', 'big')
    env.run(['git', 'config', '-f', '.gitmodules', 'submodule.big.update', 'none'], cwd=env.workspace / 'bar')
    _push_bar(env, 'skip big')

    preview = _fetch_and_update(env, '--dry-run').output
    _fetch_and_update(env)

    assert 'lib: would nest at' in preview
    assert 'big' not in preview
    assert (env.fork / 'lib' / '.gitnested').is_file()
    assert _gitlinks(env, env.fork) == ['big']
    assert _module(env, 'submodule.big.update') == 'none'


def test_init_keeps_what_git_skips(foo_bar_cloned):
    env = foo_bar_cloned
    _upstream_adds_submodule(env, _make_mid(env), 'mid')
    _upstream_adds_submodule(env, env.upstream / 'foo', 'big')
    env.run(['git', 'config', '-f', '.gitmodules', 'submodule.big.update', 'none'], cwd=env.workspace / 'bar')
    _push_bar(env, 'skip big')
    mid = env.workspace / 'mid'
    env.run(['git', 'config', '-f', '.gitmodules', 'submodule.inner.update', 'none'], cwd=mid)
    env.run(['git', 'commit', '-qam', 'skip inner'], cwd=mid)
    env.run(['git', 'push', '-q', 'origin', 'master'], cwd=mid)
    env.run(['git', 'pull', '-q', 'origin', 'master'], cwd=env.workspace / 'bar' / 'mid')
    _push_bar(env, 'bump mid')
    repo = env.workspace / 'repo'
    clone_repo((env.upstream / 'bar').as_posix(), repo)

    result = cmd_git_nested('submodules init --recursive', cwd=repo)

    assert "mid/inner: stays a submodule, .gitmodules says 'update = none'" in result.output
    assert _gitlinks(env, repo) == ['big', 'mid/inner']


def test_update_after_abort_updates_the_rest(fork):
    """You finished a nested repo by hand and threw the rest away. update <commit> does the rest."""
    env = fork
    env.modify_files('sub/Foo', text='local', cwd=env.fork)
    other = env.workspace / 'foo'
    env.modify_files('Foo', text='upstream', cwd=other)
    env.run(['git', 'push', '-q'], cwd=other)
    env.run(['git', 'pull', '-q'], cwd=env.workspace / 'bar' / 'sub')
    pinned = git_rev_parse(['HEAD'], cwd=other)
    _upstream_adds_submodule(env, env.upstream / 'foo', 'zlib')
    assert _fetch_and_update(env, check=False).returncode == 1
    worktree = env.fork / '.git' / 'tmp' / 'nested' / 'sub'
    (worktree / 'Foo').write_text('both\n')
    env.run(['git', 'add', 'Foo'], cwd=worktree)
    env.run(['git', 'commit', '-q', '--no-edit'], cwd=worktree)
    cmd_git_nested('commit sub', cwd=env.fork)
    assert 'aborted' in _update(env, '--abort').output
    assert not (env.fork / 'zlib').exists()

    assert 'zlib: would nest at' in _update(env, 'origin/master', '--dry-run').output
    _update(env, 'origin/master')

    assert (env.fork / 'zlib' / '.gitnested').is_file()
    assert_gitnested_field(env.fork / 'sub' / '.gitnested', commit=pinned)
    _assert_flat(env, env.fork)
    assert 'already up to date with origin/master' in _update(env, 'origin/master').output


def test_catching_up_has_no_single_commit(fork):
    """origin/master is merged already. There is no merge to fold the commits into."""
    result = _update(fork, 'origin/master', '--single-commit', check=False)

    assert result.returncode == 1
    assert "--single-commit only works when 'submodules update' merges" in result.output


# ============================================================================
# What a tester found on a big project (issue #184)
# ============================================================================


def _conflict_in_sub(env):
    """A local change in sub, and upstream changes the same line. Return the new pin."""
    env.modify_files('sub/Foo', text='local', cwd=env.fork)
    other = env.workspace / 'foo'
    env.modify_files('Foo', text='upstream', cwd=other)
    env.run(['git', 'push', '-q'], cwd=other)
    env.run(['git', 'pull', '-q'], cwd=env.workspace / 'bar' / 'sub')
    _push_bar(env, 'bump sub')
    return git_rev_parse(['HEAD'], cwd=other)


def test_abort_removes_the_worktree_of_a_stopped_nested_repo(fork):
    env = fork
    _conflict_in_sub(env)
    assert _fetch_and_update(env, check=False).returncode == 1
    worktree = env.fork / '.git' / 'tmp' / 'nested' / 'sub'
    assert worktree.is_dir()

    _update(env, '--abort')

    assert not worktree.exists()
    assert 'nested/sub' not in env.run(['git', 'worktree', 'list'], cwd=env.fork).output


def test_a_conflict_in_a_nested_repo_shows_the_submodules_way_only(fork):
    env = fork
    _conflict_in_sub(env)

    result = _fetch_and_update(env, check=False)

    assert result.returncode == 1
    assert 'git nested commit' not in result.output
    assert 'sub: the update stopped on conflicts in Foo' in result.output
    assert 'cd .git/tmp/nested/sub' in result.output
    assert "'git nested submodules update --continue'" in result.output
    assert "'git nested submodules update --abort'" in result.output


def test_dry_run_shows_the_deeper_submodules(foo_bar_cloned):
    env = foo_bar_cloned
    _upstream_adds_submodule(env, _make_mid(env), 'mid')
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    cmd_git_nested('submodules init --recursive', cwd=env.fork)
    pinned = _upstream_bumps_inner_of_mid(env)
    env.run(['git', 'fetch', '-q'], cwd=env.fork)

    result = _update(env, 'origin/master', '--dry-run')

    assert 'mid: would pull to' in result.output
    assert f'mid/inner: would pull to {pinned[:12]}' in result.output
    _update(env, 'origin/master')
    assert_gitnested_field(env.fork / 'mid' / 'inner' / '.gitnested', commit=pinned)


def test_the_gitattributes_block_does_not_conflict(foo_bar_cloned):
    """git-nested owns its block at the end of .gitattributes. Upstream's new rules come in above it."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    (foo / 'make.bat').write_bytes(b"echo hi\r\n")
    env.run(['git', '-c', 'core.autocrlf=false', 'add', 'make.bat'], cwd=foo)
    env.run(['git', 'commit', '-qm', 'make.bat'], cwd=foo)
    env.run(['git', 'push', '-q'], cwd=foo)
    bar = env.workspace / 'bar'
    (bar / '.gitattributes').write_text("*.bat text eol=crlf\n")
    env.run(['git', 'add', '.gitattributes'], cwd=bar)
    _upstream_adds_submodule(env, env.upstream / 'foo', 'sub')
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    cmd_git_nested('submodules init', cwd=env.fork)
    assert '/sub/make.bat -text' in (env.fork / '.gitattributes').read_text()
    with (bar / '.gitattributes').open('a') as f:
        f.write("*.bin binary\n")
    _push_bar(env, 'bin files')

    _fetch_and_update(env)

    rules = (env.fork / '.gitattributes').read_text()
    assert rules.index('*.bin binary') < rules.index('# git-nested')
    assert rules.rstrip().endswith('/sub/make.bat -text')
    assert env.run(['git', 'status', '--porcelain'], cwd=env.fork).output == ''


def test_dry_run_shows_a_new_deeper_submodule_and_skips_an_unchanged_one(foo_bar_cloned):
    env = foo_bar_cloned
    _upstream_adds_submodule(env, _make_mid(env), 'mid')
    env.fork = env.workspace / 'fork'
    clone_repo((env.upstream / 'bar').as_posix(), env.fork)
    cmd_git_nested('submodules init --recursive', cwd=env.fork)
    mid = env.workspace / 'mid'
    env.run(['git', *ALLOW_FILE, 'submodule', 'add', '-q', (env.upstream / 'foo').as_posix(), 'extra'], cwd=mid)
    env.run(['git', 'commit', '-qm', 'add extra'], cwd=mid)
    env.run(['git', 'push', '-q', 'origin', 'master'], cwd=mid)
    env.run(['git', 'pull', '-q', 'origin', 'master'], cwd=env.workspace / 'bar' / 'mid')
    _push_bar(env, 'bump mid')
    env.run(['git', 'fetch', '-q'], cwd=env.fork)

    preview = _update(env, 'origin/master', '--dry-run').output

    assert 'mid/extra: would nest at' in preview
    assert 'mid/inner' not in preview


def test_a_failed_pull_of_a_nested_repo_shows_its_own_error(fork):
    """No conflict, so there is no worktree to fix things in."""
    env = fork
    cmd_git_nested(['config', 'sub', 'remote', (env.tmp / 'gone').as_posix()], cwd=env.fork)
    env.run(['git', 'commit', '-qam', 'sub from somewhere else'], cwd=env.fork)
    _upstream_bumps_sub(env)

    result = _fetch_and_update(env, check=False)

    assert result.returncode == 1
    assert 'gone' in result.output
    assert 'the update stopped on conflicts' not in result.output
