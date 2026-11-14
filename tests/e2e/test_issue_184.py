"""The scenario of issue #184.

Upstream has these repos:

- super: the superproject. Submodules: modules/core and tools.
- core: has the submodule third_party/lib.
- docs: has the submodule theme. Super adds it later.
- lib, tools, theme: plain repos.

The user wants the submodules as nested repos: no gitlink, no .gitmodules.
"""

import pytest
from conftest import cmd_git_nested

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


# ============================================================================
# Helpers: checks in the fork
# ============================================================================


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
