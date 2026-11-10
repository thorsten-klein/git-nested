"""Tests for the `patches` field: local changes kept as patch files"""

import pytest
from conftest import cmd_git_nested

FOLDER = '.gitnested.patches'


def _patch_names(foo):
    return sorted(patch.name for patch in (foo / 'bar' / FOLDER).glob('*.patch'))


def _commit(env, foo, message):
    env.run(['git', 'add', '-A'], cwd=foo)
    env.run(['git', 'commit', '-q', '-m', message], cwd=foo)


def _with_patches(env):
    """foo with bar nested, a local change to bar/Bar, and that change as a patch"""
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    (foo / 'bar' / 'Bar').write_text("local\n")
    _commit(env, foo, 'local change')
    result = cmd_git_nested('verify bar', cwd=foo, check=False)
    assert f"wrote the missing patch bar/{FOLDER}/0001-TODO-title.patch" in result.output
    _commit(env, foo, 'the patch')
    return foo


def _upstream_change(env, path, text):
    bar = env.workspace / 'bar'
    (bar / path).parent.mkdir(parents=True, exist_ok=True)
    (bar / path).write_text(text)
    env.run(['git', 'add', path], cwd=bar)
    env.run(['git', 'commit', '-q', '-m', f'upstream {path}'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)


def test_verify_uses_the_patches_folder(foo_bar_cloned_and_nested):
    foo = _with_patches(foo_bar_cloned_and_nested)
    result = cmd_git_nested('verify bar', cwd=foo)
    assert result.output.strip().endswith(" with 1 patch")


def test_pull_applies_the_patches_on_the_new_upstream(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    _upstream_change(env, 'New', "new\n")

    result = cmd_git_nested('pull bar', cwd=foo)
    assert "bar: pulled from" in result.output
    assert (foo / 'bar' / 'Bar').read_text() == "local\n"
    assert (foo / 'bar' / 'New').read_text() == "new\n"
    assert _patch_names(foo) == ['0001-TODO-title.patch']
    patch = (foo / 'bar' / FOLDER / '0001-TODO-title.patch').read_text()
    assert patch.startswith("From 0000000000000000000000000000000000000000 ")
    assert "+local" in patch
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''
    assert cmd_git_nested('verify bar', cwd=foo).output.strip().endswith(" with 1 patch")


def test_pull_refuses_local_changes_that_are_not_in_the_patches(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    (foo / 'bar' / 'Other').write_text("not in a patch\n")
    _commit(env, foo, 'more local work')

    result = cmd_git_nested('pull bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: has changes that are not in its patches; 'git nested verify bar' writes the missing one" in (
        result.output
    )


def test_pull_drops_a_patch_upstream_has(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    _upstream_change(env, 'Bar', "local\n")

    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'Bar').read_text() == "local\n"
    assert _patch_names(foo) == []
    assert not env.run(['git', 'ls-files', f'bar/{FOLDER}'], cwd=foo).stdout


def test_pull_stops_at_a_patch_that_does_not_apply(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    _upstream_change(env, 'Bar', "upstream\n")

    result = cmd_git_nested('pull bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: the pull is unfinished, the patch 0001-TODO-title.patch does not apply" in result.output
    assert "git am --continue" in result.output

    worktree = foo / '.git' / 'tmp' / 'nested' / 'bar'
    (worktree / 'Bar').write_text("upstream and local\n")
    env.run(['git', 'add', 'Bar'], cwd=worktree)
    env.run(['git', '-c', 'core.editor=true', 'am', '--continue'], cwd=worktree)
    cmd_git_nested('commit bar', cwd=foo)

    assert (foo / 'bar' / 'Bar').read_text() == "upstream and local\n"
    patch = (foo / 'bar' / FOLDER / '0001-TODO-title.patch').read_text()
    assert "+upstream and local" in patch
    assert cmd_git_nested('verify bar', cwd=foo).output.strip().endswith(" with 1 patch")


def test_push_leaves_the_patches_folder_out(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)

    cmd_git_nested('push -b master bar', cwd=foo)
    upstream = env.upstream / 'bar'
    pushed = env.run(['git', 'ls-tree', '-r', '--name-only', 'master'], cwd=upstream).stdout
    assert FOLDER not in pushed
    assert env.run(['git', 'show', 'master:Bar'], cwd=upstream).stdout == "local\n"


def test_reclone_puts_the_patches_back(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    _upstream_change(env, 'New', "new\n")

    cmd_git_nested('clone --force ../../upstream/bar bar', cwd=foo)
    assert (foo / 'bar' / 'Bar').read_text() == "local\n"
    assert (foo / 'bar' / 'New').read_text() == "new\n"
    assert _patch_names(foo) == ['0001-TODO-title.patch']


def test_pull_keeps_nested_repos_inside(foo_bar_cloned_and_nested):
    """A nested repo inside is not in the patches, and stays as it is"""
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    cmd_git_nested(['clone', (env.upstream / 'foo').as_posix(), 'bar/inner'], cwd=foo)
    cmd_git_nested(['config', 'bar/inner', 'patches', FOLDER], cwd=foo)
    (foo / 'bar' / 'inner' / 'Foo').write_text("inner local\n")
    _commit(env, foo, 'inner change')
    cmd_git_nested('verify bar/inner', cwd=foo, check=False)
    _commit(env, foo, 'inner patch')
    assert cmd_git_nested('verify bar', cwd=foo).output.strip().endswith(" with 1 patch")

    _upstream_change(env, 'New', "new\n")
    cmd_git_nested('pull bar', cwd=foo)

    assert (foo / 'bar' / 'New').read_text() == "new\n"
    assert (foo / 'bar' / 'inner' / 'Foo').read_text() == "inner local\n"
    assert (foo / 'bar' / 'inner' / '.gitnested').is_file()
    assert len(list((foo / 'bar' / 'inner' / FOLDER).glob('*.patch'))) == 1
    patch = (foo / 'bar' / FOLDER / '0001-TODO-title.patch').read_text()
    assert 'inner' not in patch
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''


def test_patches_refuse_a_filter(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    gitnested = foo / 'bar' / '.gitnested'
    gitnested.write_text(gitnested.read_text().replace('nested:\n', 'nested:\n  path: bard\n'))
    _commit(env, foo, 'path')

    result = cmd_git_nested('pull bar', cwd=foo, check=False)
    assert "bar: patches do not work with filter, exclude or path yet" in result.output


def test_push_commit_empties_the_patches(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)

    cmd_git_nested('push --commit -b master bar', cwd=foo)
    assert _patch_names(foo) == []
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''
    assert cmd_git_nested('verify bar', cwd=foo).output.strip().endswith(" with 0 patches")


def test_a_patches_folder_outside_the_subdir(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', '../patches/bar'], cwd=foo)
    (foo / 'bar' / 'Bar').write_text("local\n")
    _commit(env, foo, 'local change')
    cmd_git_nested('verify bar', cwd=foo, check=False)
    _commit(env, foo, 'the patch')
    _upstream_change(env, 'New', "new\n")

    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'Bar').read_text() == "local\n"
    assert [patch.name for patch in (foo / 'patches' / 'bar').glob('*.patch')] == ['0001-TODO-title.patch']
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''


@pytest.mark.parametrize(
    ('folder', 'message'),
    [
        ('/abs/patches', "bar: patches must be a path relative to the subdir"),
        ('.', "bar: patches can't be the subdir itself"),
    ],
)
def test_a_bad_patches_folder_is_refused(foo_bar_cloned_and_nested, folder, message):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', folder], cwd=foo)
    _commit(env, foo, 'patches')

    result = cmd_git_nested('pull bar', cwd=foo, check=False)
    assert message in result.output


@pytest.mark.parametrize(
    ('option', 'message'),
    [
        ('--ignore=bar/bard', "--ignore does not work with patches yet"),
        ('--no-squash', "bar: patches do not work with --no-squash yet"),
    ],
)
def test_pull_options_that_do_not_work_with_patches(foo_bar_cloned_and_nested, option, message):
    foo = _with_patches(foo_bar_cloned_and_nested)
    result = cmd_git_nested(['pull', option, 'bar'], cwd=foo, check=False)
    assert message in result.output


def test_reclone_stops_at_a_patch_that_does_not_apply(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    _upstream_change(env, 'Bar', "upstream\n")
    head = env.run(['git', 'rev-parse', 'HEAD'], cwd=foo).stdout

    result = cmd_git_nested('clone --force ../../upstream/bar bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: the patch 0001-TODO-title.patch does not apply on upstream " in result.output
    assert env.run(['git', 'rev-parse', 'HEAD'], cwd=foo).stdout == head


def test_commit_of_a_merge_writes_one_patch(foo_bar_cloned_and_nested):
    """A nested branch that is not a plain line becomes one patch"""
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    _upstream_change(env, 'Bar', "upstream\n")
    cmd_git_nested('pull bar', cwd=foo, check=False)

    worktree = foo / '.git' / 'tmp' / 'nested' / 'bar'
    env.run(['git', 'am', '--abort'], cwd=worktree)
    env.run(['git', 'checkout', '-q', '-b', 'side', 'HEAD~1'], cwd=worktree)
    (worktree / 'Side').write_text("side\n")
    env.run(['git', 'add', 'Side'], cwd=worktree)
    env.run(['git', 'commit', '-q', '-m', 'side'], cwd=worktree)
    env.run(['git', 'checkout', '-q', 'nested/bar'], cwd=worktree)
    env.run(['git', 'merge', '-q', '--no-ff', '-m', 'merge side', 'side'], cwd=worktree)
    cmd_git_nested('commit bar', cwd=foo)

    assert _patch_names(foo) == ['0001-Local-changes-to-bar.patch']
    assert "+side" in (foo / 'bar' / FOLDER / '0001-Local-changes-to-bar.patch').read_text()
    assert cmd_git_nested('verify bar', cwd=foo).output.strip().endswith(" with 1 patch")


def test_reclone_without_any_patches_yet(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    _commit(env, foo, 'patches')
    _upstream_change(env, 'New', "new\n")

    cmd_git_nested('clone --force ../../upstream/bar bar', cwd=foo)
    assert (foo / 'bar' / 'New').read_text() == "new\n"
    assert _patch_names(foo) == []
