"""Tests for git nested init command"""

import textwrap

from conftest import VERSION, assert_gitnested_field, cmd_git_nested, git_rev_parse


def test_init_no_remote(env):
    """Test basic nested init functionality"""
    env.clone_init()

    gitnested = env.workspace / 'init' / 'doc' / '.gitnested'
    assert not gitnested.exists()

    # init the nested repository
    result = cmd_git_nested('init doc', cwd=env.workspace / 'init')

    # Test init/doc/.gitnested file contents
    assert result.output.strip() == "doc: initialised as a nested repository with no remote"
    assert_gitnested_field(gitnested, remote='none', branch='master', commit='', parent='', method='merge')


def test_init_with_remote(env):
    """Test basic nested init functionality"""
    env.clone_init()

    gitnested = env.workspace / 'init' / 'doc' / '.gitnested'
    assert not gitnested.exists()

    # Init with options
    result = cmd_git_nested('init doc -r git@github.com:user/repo -b foo -M rebase', cwd=env.workspace / 'init')

    # Test init/doc/.gitnested file contents
    assert result.output.strip() == "doc: initialised as a nested repository with git@github.com:user/repo (foo)"
    assert_gitnested_field(
        gitnested, remote='git@github.com:user/repo', branch='foo', commit='', parent='', method='rebase'
    )


def test_verbose(env):
    """Test that --verbose works"""
    env.clone_init()

    # Test verbose mode with init command
    cp = cmd_git_nested('--verbose init doc', cwd=env.workspace / 'init')
    assert cp.returncode == 0
    assert cp.output.strip() == textwrap.dedent("""\
        * checking for a worktree on nested/doc
        * writing doc/.gitnested
        * committing the .gitnested update
        doc: initialised as a nested repository with no remote""")


def test_init_nonexistent_subdir(env):
    """Test that init fails when the subdir doesn't exist"""
    env.clone_init()
    result = cmd_git_nested('init nonexistent', cwd=env.workspace / 'init', check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: nonexistent: does not exist"


def test_init_already_a_nested_repository(env):
    """Test that init fails when the subdir is already a nested repository"""
    env.clone_init()
    cmd_git_nested('init doc', cwd=env.workspace / 'init')
    result = cmd_git_nested('init doc', cwd=env.workspace / 'init', check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: doc: is already a nested repository"


def test_init_untracked_subdir(env):
    """Test that init fails when the subdir exists but nothing is tracked by git"""
    env.clone_init()
    untracked = env.workspace / 'init' / 'untracked'
    untracked.mkdir()
    (untracked / 'scratch.txt').write_text('not tracked\n')
    result = cmd_git_nested('init untracked', cwd=env.workspace / 'init', check=False)
    assert result.returncode == 1
    assert result.output.strip() == "git-nested: untracked: exists, but git tracks nothing in it"


def test_init_with_commit_records_sync_point_and_pull_uses_it(foo_bar_cloned):
    """An adopted directory can name its upstream commit explicitly."""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    vendored = foo / 'vendor' / 'bar'
    vendored.mkdir(parents=True)
    (vendored / 'Bar').touch()
    (vendored / 'Local').write_text('local only\n')
    env.run(['git', 'add', 'vendor/bar/Bar', 'vendor/bar/Local'], cwd=foo)
    env.run(['git', 'commit', '-m', 'vendor bar'], cwd=foo)

    vendor_commit = git_rev_parse(['HEAD'], cwd=foo)
    first_upstream = git_rev_parse(['A'], cwd=env.workspace / 'bar')
    latest_upstream = git_rev_parse(['HEAD'], cwd=env.workspace / 'bar')

    result = cmd_git_nested(
        ['init', 'vendor/bar', '-r', (env.upstream / 'bar').as_posix(), '--commit', first_upstream],
        cwd=foo,
    )

    assert result.output.strip() == (
        f"vendor/bar: initialised as a nested repository with {env.upstream.as_posix()}/bar (master) "
        f"at {first_upstream[:7]}"
    )
    assert_gitnested_field(
        vendored / '.gitnested',
        remote=(env.upstream / 'bar').as_posix(),
        branch='master',
        commit=first_upstream,
        parent=vendor_commit,
        method='merge',
        version=VERSION,
    )

    result = cmd_git_nested('pull vendor/bar', cwd=foo)

    assert result.output.strip() == f"vendor/bar: pulled from {env.upstream.as_posix()}/bar (master)"
    assert (vendored / 'Local').read_text() == 'local only\n'
    assert (vendored / 'bard' / 'Bard').is_file()
    assert_gitnested_field(
        vendored / '.gitnested',
        remote=(env.upstream / 'bar').as_posix(),
        branch='master',
        commit=latest_upstream,
        parent=vendor_commit,
        method='merge',
        version=VERSION,
    )
