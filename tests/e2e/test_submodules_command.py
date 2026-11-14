"""Tests for `git nested submodules` (#184).

Upstream bar is the superproject. Its submodules become nested repos.
"""

from conftest import assert_gitnested_field, clone_repo, cmd_git_nested, git_rev_parse

ALLOW_FILE = ['-c', 'protocol.file.allow=always']


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


def _top_dirs_per_commit(env, repo, base):
    """The top dirs that each commit after base changed, sorted. .gitmodules does not count."""
    commits = env.run(['git', 'rev-list', f'{base}..HEAD'], cwd=repo).output.split()
    changed = [env.run(['git', 'diff', '--name-only', f'{c}^', c], cwd=repo).output.split() for c in commits]
    dirs = [{path.split('/')[0] for path in paths if path != '.gitmodules'} for paths in changed]
    return sorted(dirs, key=sorted)


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


def test_init_refuses_a_path_without_a_submodule(foo_bar_cloned):
    env = foo_bar_cloned
    repo = _repo_with_three_submodules(env)
    head = git_rev_parse(['HEAD'], cwd=repo)

    result = cmd_git_nested('submodules init --only sub --only nope', cwd=repo, check=False)

    assert result.returncode == 1
    assert 'nope: no submodule there' in result.output
    assert git_rev_parse(['HEAD'], cwd=repo) == head


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


# ============================================================================
# Nested repos with patches
# ============================================================================

PATCHES = '.gitnested.patches'


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
