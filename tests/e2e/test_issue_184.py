"""The scenario of issue #184, from start to end.

Upstream has these repos:

- super: the superproject. Submodules: modules/core and tools.
- core: has the submodule third_party/lib.
- docs: has the submodule theme. Super adds it later.
- lib, tools, theme: plain repos.

The user forks super. The fork has no submodules, only nested repos. It
pulls from the remote 'upstream' and pushes to its own 'origin'.
"""

import pytest
from conftest import assert_gitnested_field, cmd_git_nested, git_rev_parse

ALLOW_FILE = ['-c', 'protocol.file.allow=always']


class Upstream:
    """The upstream repos, each with a work clone to make commits in."""

    def __init__(self, env):
        self.env = env
        self.work = env.workspace / 'upstream-work'

    def url(self, name):
        return (self.env.upstream / name).as_posix()

    def git(self, name, *args):
        return self.env.run(['git', *ALLOW_FILE, *args], cwd=self.work / name).output.strip()

    def create(self, name, **files):
        self.env.run(['git', 'init', '-q', '--bare', self.url(name)])
        self.env.run(['git', 'clone', '-q', self.url(name), self.work / name])
        self.write(name, **files)
        self.push(name, f'{name}: first commit')

    def write(self, name, **files):
        """Append a line to each file."""
        for file, text in files.items():
            path = self.work / name / file
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a') as f:
                f.write(f'{text}\n')

    def add_submodule(self, name, sub, path):
        self.git(name, 'submodule', 'add', '-q', self.url(sub), path)

    def follow(self, name, path):
        """Let the submodule at `path` pin the newest commit of its upstream."""
        self.git(name, '-C', path, 'fetch', '-q')
        self.git(name, '-C', path, 'checkout', '-q', 'origin/master')

    def push(self, name, message, author='Upstream Dev'):
        """Commit all changes as `author` and push. Return the commit."""
        self.git(name, 'add', '-A')
        self.git(name, '-c', f'user.name={author}', '-c', 'user.email=dev@upstream', 'commit', '-qm', message)
        self.git(name, 'push', '-q', 'origin', 'HEAD:master')
        return self.git(name, 'rev-parse', 'HEAD')

    def head(self, name):
        return self.git(name, 'rev-parse', 'HEAD')


@pytest.fixture
def upstream(env):
    up = Upstream(env)
    for name in ('lib', 'tools', 'theme'):
        up.create(name, **{name.capitalize(): name})
    up.create('core', Core='core')
    up.add_submodule('core', 'lib', 'third_party/lib')
    up.push('core', 'core: add lib')
    up.create('docs', Docs='docs')
    up.add_submodule('docs', 'theme', 'theme')
    up.push('docs', 'docs: add theme')
    up.create('super', README='super')
    up.add_submodule('super', 'core', 'modules/core')
    up.add_submodule('super', 'tools', 'tools')
    up.push('super', 'add core and tools')
    return up


@pytest.fixture
def mine(env, upstream):
    """The user's fork: flattened, with 'origin' as the fork and 'upstream' as super."""
    repo = env.workspace / 'mine'
    env.run(['git', 'clone', '-q', upstream.url('super'), repo])
    cmd_git_nested('submodules init --recursive', cwd=repo)
    fork = env.upstream / 'fork'
    env.run(['git', 'init', '-q', '--bare', fork])
    env.run(['git', 'remote', 'rename', 'origin', 'upstream'], cwd=repo)
    env.run(['git', 'remote', 'add', 'origin', fork], cwd=repo)
    env.run(['git', 'push', '-q', '-u', 'origin', 'master'], cwd=repo)
    return repo


# ============================================================================
# Helpers: checks in the fork
# ============================================================================


def _update_from_upstream(env, repo, check=True):
    """Fetch upstream, then `submodules update upstream/master`."""
    env.run(['git', 'fetch', '-q', 'upstream'], cwd=repo)
    return cmd_git_nested('submodules update upstream/master', cwd=repo, check=check)


def _git(env, repo, *args):
    return env.run(['git', *args], cwd=repo).output.strip()


def _assert_flat(env, repo):
    """No gitlink, no .gitmodules, nothing left over."""
    modes = {line.split()[0] for line in _git(env, repo, 'ls-files', '-s').splitlines()}
    assert '160000' not in modes
    assert not (repo / '.gitmodules').exists()
    assert _git(env, repo, 'status', '--porcelain') == ''


def _nested_repos(env, repo):
    """The paths of all nested repos in HEAD."""
    files = _git(env, repo, 'ls-tree', '-r', '--name-only', 'HEAD').splitlines()
    return sorted(path.removesuffix('/.gitnested') for path in files if path.endswith('/.gitnested'))


def _owner(path, roots):
    """The nested repo that `path` belongs to: the longest root that holds it."""
    owners = [root for root in roots if path == root or path.startswith(f'{root}/')]
    return max(owners, key=len) if owners else path


def _submodules_per_commit(env, repo, base, roots):
    """For each commit after base, the nested repos it changed."""
    result = []
    for commit in _git(env, repo, 'rev-list', '--reverse', f'{base}..HEAD').split():
        paths = _git(env, repo, 'diff', '--name-only', f'{commit}^', commit).split()
        result.append({_owner(path, roots) for path in paths if path != '.gitmodules'})
    return result


def _last_merge(env, repo):
    return _git(env, repo, 'rev-list', '--merges', '-1', 'HEAD')


def _is_ancestor(env, repo, commit):
    return env.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=repo, check=False).returncode == 0


def _edit(env, repo, path, text):
    with (repo / path).open('a') as f:
        f.write(f'{text}\n')
    env.run(['git', 'commit', '-qam', f'my change in {path}'], cwd=repo)


# ============================================================================
# The whole story
# ============================================================================


def test_the_fork_of_issue_184(env, upstream, mine):
    """Flatten the fork. Then follow upstream over two rounds of changes."""
    # --- The start: everything is flat, the history of super is there.
    assert _nested_repos(env, mine) == ['modules/core', 'modules/core/third_party/lib', 'tools']
    assert _is_ancestor(env, mine, upstream.head('super'))
    assert (mine / 'modules' / 'core' / 'third_party' / 'lib' / 'Lib').is_file()
    _assert_flat(env, mine)

    # --- Local changes in the flattened submodules, at every depth.
    _edit(env, mine, 'modules/core/Core', 'my core change')
    _edit(env, mine, 'modules/core/third_party/lib/Lib', 'my lib change')
    _edit(env, mine, 'tools/Tools', 'my tools change')
    env.add_new_files('FORK', cwd=mine)

    # --- Upstream round 1.
    upstream.write('lib', LibNew='lib 2')
    lib_pin = upstream.push('lib', 'lib: new file')
    upstream.follow('core', 'third_party/lib')
    upstream.write('core', CoreNew='core 2')
    core_pin = upstream.push('core', 'core: new file, bump lib')
    upstream.write('tools', ToolsNew='tools 2')
    upstream.push('tools', 'tools: new file')
    mirror = env.upstream / 'tools-mirror'
    env.run(['git', 'clone', '-q', '--bare', upstream.url('tools'), mirror])

    upstream.write('super', README='more text')
    upstream.follow('super', 'modules/core')
    alice = upstream.push('super', 'Update readme and core', author='Alice')
    upstream.add_submodule('super', 'docs', 'docs')
    bob = upstream.push('super', 'Add docs', author='Bob')
    upstream.git('super', 'submodule', 'set-url', 'tools', mirror.as_posix())
    upstream.follow('super', 'tools')
    tools_pin = upstream.git('super', '-C', 'tools', 'rev-parse', 'HEAD')
    alice_again = upstream.push('super', 'Move tools to a mirror and update it', author='Alice')

    _update_from_upstream(env, mine)

    # Each superproject commit is there, as upstream made it.
    for commit, author in ((alice, 'Alice'), (bob, 'Bob'), (alice_again, 'Alice')):
        assert _is_ancestor(env, mine, commit)
        assert _git(env, mine, 'log', '-1', '--format=%an', commit) == author
    merge = _last_merge(env, mine)
    assert git_rev_parse([f'{merge}^2'], cwd=mine) == alice_again

    # Each submodule moved, with the local changes kept.
    assert (mine / 'modules' / 'core' / 'CoreNew').is_file()
    assert 'my core change' in (mine / 'modules' / 'core' / 'Core').read_text()
    assert_gitnested_field(mine / 'modules' / 'core' / '.gitnested', commit=core_pin)
    lib = mine / 'modules' / 'core' / 'third_party' / 'lib'
    assert (lib / 'LibNew').is_file()
    assert 'my lib change' in (lib / 'Lib').read_text()
    assert_gitnested_field(lib / '.gitnested', commit=lib_pin)
    assert (mine / 'tools' / 'ToolsNew').is_file()
    assert 'my tools change' in (mine / 'tools' / 'Tools').read_text()
    assert_gitnested_field(mine / 'tools' / '.gitnested', remote=mirror.as_posix(), commit=tools_pin)

    # The new submodule is nested, its own submodule too.
    assert (mine / 'docs' / 'theme' / 'Theme').is_file()
    assert _nested_repos(env, mine) == [
        'docs',
        'docs/theme',
        'modules/core',
        'modules/core/third_party/lib',
        'tools',
    ]

    # Each changed submodule got its own commit. Nothing else is in them.
    changed = _submodules_per_commit(env, mine, merge, _nested_repos(env, mine))
    assert all(len(repos) == 1 for repos in changed), changed
    assert sorted(repo for repos in changed for repo in repos) == sorted([
        'docs',
        'docs/theme',
        'modules/core',
        'modules/core/third_party/lib',
        'tools',
    ])
    _assert_flat(env, mine)

    # --- The fork can push. A plain clone of it has all files.
    env.run(['git', 'push', '-q', 'origin', 'master'], cwd=mine)
    teammate = env.workspace / 'teammate'
    env.run(['git', 'clone', '-q', env.upstream / 'fork', teammate])
    assert (teammate / 'modules' / 'core' / 'third_party' / 'lib' / 'LibNew').is_file()
    assert (teammate / 'docs' / 'theme' / 'Theme').is_file()

    # --- Upstream round 2: drop tools, move docs.
    _edit(env, mine, 'docs/Docs', 'my docs change')
    upstream.git('super', 'rm', '-q', 'tools')
    dropped = upstream.push('super', 'Drop tools', author='Bob')
    (upstream.work / 'super' / 'documentation').mkdir()
    upstream.git('super', 'mv', 'docs', 'documentation/docs')
    moved = upstream.push('super', 'Move docs', author='Alice')

    _update_from_upstream(env, mine)

    assert _is_ancestor(env, mine, dropped)
    assert _is_ancestor(env, mine, moved)
    assert not (mine / 'tools').exists()
    assert not (mine / 'docs').exists()
    docs = mine / 'documentation' / 'docs'
    assert 'my docs change' in (docs / 'Docs').read_text()
    assert (docs / 'theme' / 'Theme').is_file()
    assert _nested_repos(env, mine) == [
        'documentation/docs',
        'documentation/docs/theme',
        'modules/core',
        'modules/core/third_party/lib',
    ]
    _assert_flat(env, mine)

    # --- Nothing new upstream.
    head = git_rev_parse(['HEAD'], cwd=mine)
    assert 'already up to date' in _update_from_upstream(env, mine).output
    assert git_rev_parse(['HEAD'], cwd=mine) == head


# ============================================================================
# Single cases of the story
# ============================================================================


def test_init_in_a_clone_the_user_already_has(env, upstream):
    """The user has a normal clone with submodules. init flattens it in place."""
    repo = env.workspace / 'clone'
    env.run(['git', *ALLOW_FILE, 'clone', '-q', '--recurse-submodules', upstream.url('super'), repo])

    cmd_git_nested('submodules init --recursive', cwd=repo)

    assert _nested_repos(env, repo) == ['modules/core', 'modules/core/third_party/lib', 'tools']
    assert (repo / 'modules' / 'core' / 'third_party' / 'lib' / 'Lib').is_file()
    assert not (repo / '.git' / 'modules' / 'modules' / 'core').exists()
    _assert_flat(env, repo)


def test_a_conflict_inside_a_submodule(env, upstream, mine):
    """The fork and upstream change the same lines. You fix it the git way. Then you continue."""
    _edit(env, mine, 'modules/core/Core', 'my core change')
    upstream.write('core', Core='upstream core change')
    core_pin = upstream.push('core', 'core: change Core')
    upstream.write('tools', ToolsNew='tools 2')
    tools_pin = upstream.push('tools', 'tools: new file')
    upstream.follow('super', 'modules/core')
    upstream.follow('super', 'tools')
    upstream.push('super', 'Bump core and tools')

    result = _update_from_upstream(env, mine, check=False)

    assert result.returncode == 1
    assert 'modules/core' in result.output
    assert 'submodules update --continue' in result.output
    worktree = next(line.split('cd ', 1)[1] for line in result.output.splitlines() if 'cd ' in line)

    worktree = mine / worktree
    (worktree / 'Core').write_text('core\nboth changes\n')
    env.run(['git', 'add', 'Core'], cwd=worktree)
    env.run(['git', 'commit', '-q', '--no-edit'], cwd=worktree)
    cmd_git_nested('commit modules/core', cwd=mine)
    cmd_git_nested('submodules update --continue', cwd=mine)

    assert (mine / 'modules' / 'core' / 'Core').read_text() == 'core\nboth changes\n'
    assert_gitnested_field(mine / 'modules' / 'core' / '.gitnested', commit=core_pin)
    assert_gitnested_field(mine / 'tools' / '.gitnested', commit=tools_pin)
    _assert_flat(env, mine)


def test_upstream_history_with_a_merge_commit(env, upstream, mine):
    """Upstream works on a branch and merges it. The fork keeps that history as it is."""
    upstream.git('super', 'checkout', '-q', '-b', 'feature')
    upstream.write('core', CoreNew='core 2')
    core_pin = upstream.push('core', 'core: new file')
    upstream.follow('super', 'modules/core')
    upstream.git('super', 'commit', '-qam', 'Bump core on a branch')
    feature = upstream.head('super')
    upstream.git('super', 'checkout', '-q', 'master')
    upstream.git('super', '-c', 'user.name=Alice', 'merge', '-q', '--no-ff', '-m', 'Merge feature', 'feature')
    upstream.git('super', 'submodule', 'update', '-q')
    upstream.git('super', 'push', '-q', 'origin', 'master')
    merged = upstream.head('super')

    _update_from_upstream(env, mine)

    assert _is_ancestor(env, mine, feature)
    assert _is_ancestor(env, mine, merged)
    assert_gitnested_field(mine / 'modules' / 'core' / '.gitnested', commit=core_pin)
    _assert_flat(env, mine)


def test_a_submodule_bump_inside_a_submodule(env, upstream, mine):
    """Only lib moves, deep inside core. core's commit pins it, super pins core."""
    _edit(env, mine, 'modules/core/third_party/lib/Lib', 'my lib change')
    upstream.write('lib', LibNew='lib 2')
    lib_pin = upstream.push('lib', 'lib: new file')
    upstream.follow('core', 'third_party/lib')
    upstream.push('core', 'core: bump lib')
    upstream.follow('super', 'modules/core')
    upstream.push('super', 'Bump core')

    _update_from_upstream(env, mine)

    lib = mine / 'modules' / 'core' / 'third_party' / 'lib'
    assert (lib / 'LibNew').is_file()
    assert 'my lib change' in (lib / 'Lib').read_text()
    assert_gitnested_field(lib / '.gitnested', commit=lib_pin)
    _assert_flat(env, mine)
