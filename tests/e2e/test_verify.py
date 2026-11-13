"""Tests for git nested verify command"""

import re

from conftest import clone_repo, cmd_git_nested, create_upstream_repo


def _patch_files(directory):
    return sorted(patch.name for patch in directory.glob('*.patch'))


def _commit_local_change(env, foo, text):
    env.modify_files('bar/Bar', text=text, cwd=foo)


def test_verify_without_local_changes(foo_bar_cloned_and_nested):
    """A freshly cloned nested repository is its upstream commit with no patches"""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('verify bar', cwd=env.workspace / 'foo')
    assert result.output.strip().startswith("bar: matches upstream ")
    assert result.output.strip().endswith(" with 0 patches")


def test_verify_without_patches_reports_the_difference(foo_bar_cloned_and_nested):
    """With nowhere to write the missing patch, only the difference is reported"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _commit_local_change(env, foo, 'local')

    result = cmd_git_nested('verify bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: differs from its upstream commit with 0 patches" in result.output
    assert " Bar | 1 +" in result.output
    assert "use --output to have the missing one written" in result.output
    assert not (foo / '.git' / 'tmp' / 'verify').exists()


def test_verify_writes_the_missing_patch_and_accepts_it(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    patches = foo / 'patches' / 'bar'
    _commit_local_change(env, foo, 'first')

    result = cmd_git_nested('verify -o patches/bar bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "wrote the missing patch patches/bar/0001-TODO-title.patch" in result.output
    assert _patch_files(patches) == ['0001-TODO-title.patch']
    patch = (patches / '0001-TODO-title.patch').read_text()
    assert "Subject: [PATCH] TODO: title" in patch
    assert "+first" in patch
    assert ".gitnested" not in patch

    result = cmd_git_nested(['verify', 'bar', '--patches', str(patches / '0001-TODO-title.patch')], cwd=foo)
    assert "applying patches/bar/0001-TODO-title.patch" in result.output
    assert result.output.strip().endswith(" with 1 patch")


def test_verify_writes_the_next_patch_next_to_the_last_one(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    patches = foo / 'patches'
    _commit_local_change(env, foo, 'first')
    cmd_git_nested('verify -o patches bar', cwd=foo, check=False)
    (patches / '0001-TODO-title.patch').rename(patches / '0001-first.patch')
    (patches / 'README').write_text("not a patch\n")
    _commit_local_change(env, foo, 'second')

    result = cmd_git_nested('verify bar --patches patches/0001-first.patch', cwd=foo, check=False)
    assert result.returncode == 1
    assert "differs from its upstream commit with 1 patch\n" in result.output
    assert _patch_files(patches) == ['0001-first.patch', '0002-TODO-title.patch']
    patch = (patches / '0002-TODO-title.patch').read_text()
    assert "+second" in patch
    assert "+first" not in patch

    cmd_git_nested('verify bar --patches patches/0001-first.patch patches/0002-TODO-title.patch', cwd=foo)


def test_verify_a_patch_that_does_not_apply(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    (foo / 'broken.patch').write_text(
        "From: x <x@x>\nSubject: [PATCH] broken\n\n---\n--- a/none\n+++ b/none\n@@ -1 +1 @@\n-a\n+b\n"
    )

    result = cmd_git_nested('verify bar --patches broken.patch', cwd=foo, check=False)
    assert result.returncode == 1
    assert "broken.patch: does not apply" in result.output
    assert not (foo / '.git' / 'tmp' / 'verify').exists()


def test_verify_a_diff_that_does_not_apply(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    (foo / 'broken.diff').write_text("--- a/none\n+++ b/none\n@@ -1 +1 @@\n-a\n+b\n")

    result = cmd_git_nested('verify bar --diffs broken.diff', cwd=foo, check=False)
    assert result.returncode == 1
    assert "broken.diff: does not apply\n" in result.output
    assert "none" in result.output


def test_verify_a_missing_patch_file(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('verify bar --patches no-such.patch', cwd=env.workspace / 'foo', check=False)
    assert result.returncode == 1
    assert "no-such.patch: no such file" in result.output


def test_verify_from_a_subdirectory(foo_bar_cloned_and_nested):
    """The subdir and the patches are relative to where the command is started"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _commit_local_change(env, foo, 'first')
    cmd_git_nested('verify -o patches bar', cwd=foo, check=False)

    result = cmd_git_nested('verify . --patches ../patches/0001-TODO-title.patch', cwd=foo / 'bar')
    assert result.output.strip().endswith(" with 1 patch")


def test_verify_keep_leaves_the_worktree(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    result = cmd_git_nested('verify --keep bar', cwd=foo)
    assert "kept the worktree at .git/tmp/verify/bar" in result.output
    assert (foo / '.git' / 'tmp' / 'verify' / 'bar' / 'Bar').is_file()

    # a second run replaces it
    cmd_git_nested('verify bar', cwd=foo)
    assert not (foo / '.git' / 'tmp' / 'verify').exists()


def test_verify_ignores_a_nested_branch(foo_bar_cloned_and_nested):
    """The patches go into a worktree of its own, so a branch in progress is no obstacle"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested('branch bar', cwd=foo)
    cmd_git_nested('verify bar', cwd=foo)
    assert (foo / '.git' / 'tmp' / 'nested' / 'bar').is_dir()


def test_verify_fetches_a_missing_upstream_commit(foo_bar_cloned_and_nested):
    """A fresh clone of the parent repository does not have the upstream commit yet"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    env.run(['git', 'push'], cwd=foo)
    clone_repo((env.upstream / 'foo').as_posix(), env.workspace / 'foo2')

    result = cmd_git_nested('verify bar', cwd=env.workspace / 'foo2')
    assert result.output.strip().endswith(" with 0 patches")


def test_verify_an_upstream_commit_that_is_gone(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    gitnested = foo / 'bar' / '.gitnested'
    gitnested.write_text(re.sub(r'(commit\W+)[0-9a-f]{40}', r'\g<1>' + 'deadbeef' * 5, gitnested.read_text()))
    env.run(['git', 'commit', '-qam', 'bad commit'], cwd=foo)

    result = cmd_git_nested('verify bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert f"bar: upstream commit {'deadbeef' * 5} is not on" in result.output


def test_verify_without_an_upstream_commit(env):
    env.clone_init()
    init = env.workspace / 'init'
    cmd_git_nested('init doc', cwd=init)

    result = cmd_git_nested('verify doc', cwd=init, check=False)
    assert result.returncode == 1
    assert "doc: no upstream commit recorded in .gitnested" in result.output


def test_verify_a_missing_commit_without_a_remote(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    env.run(['git', 'push'], cwd=env.workspace / 'foo')
    foo2 = env.workspace / 'foo2'
    clone_repo((env.upstream / 'foo').as_posix(), foo2)
    cmd_git_nested('config bar remote none', cwd=foo2)
    env.run(['git', 'commit', '-qam', 'no remote'], cwd=foo2)

    result = cmd_git_nested('verify bar', cwd=foo2, check=False)
    assert result.returncode == 1
    assert "is not here, and there is no remote" in result.output


def test_verify_with_a_path(foo_bar_cloned):
    """Only the nested directory of upstream is the base"""
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    env.add_new_files('sub/file', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')
    cmd_git_nested(['clone', '--path', 'sub', (env.upstream / 'bar').as_posix(), 'lib'], cwd=foo)
    cmd_git_nested('verify lib', cwd=foo)

    env.modify_files('lib/file', text='local', cwd=foo)
    result = cmd_git_nested('verify -o patches lib', cwd=foo, check=False)
    assert result.returncode == 1
    assert "diff --git a/file b/file" in (foo / 'patches' / '0001-TODO-title.patch').read_text()


def test_verify_with_a_filter(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    create_upstream_repo(env.upstream / 'leg')
    clone_repo((env.upstream / 'leg').as_posix(), env.workspace / 'leg')
    env.add_new_files('subdirA/file1', cwd=env.workspace / 'leg')
    env.add_new_files('subdirB/file1', cwd=env.workspace / 'leg')
    env.run(['git', 'push'], cwd=env.workspace / 'leg')
    cmd_git_nested(f'clone {env.upstream.as_posix()}/leg leg --filter=subdirA', cwd=foo)

    cmd_git_nested('verify leg', cwd=foo)


def test_verify_a_plain_diff(foo_bar_cloned_and_nested):
    """A diff made with diff(1), not git, applies as well"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    original = (foo / 'bar' / 'Bar').read_text()
    _commit_local_change(env, foo, 'local')
    (foo / 'orig').mkdir()
    (foo / 'orig' / 'Bar').write_text(original)
    plain = env.run(['diff', '-u', 'orig/Bar', 'bar/Bar'], cwd=foo, check=False).stdout
    (foo / 'orig').joinpath('Bar').unlink()
    (foo / 'orig').rmdir()
    (foo / 'bar.diff').write_text(plain)

    result = cmd_git_nested('verify bar --diffs bar.diff', cwd=foo)
    assert result.output.strip().endswith(" with 1 diff")


def test_verify_diff_writes_the_whole_diff(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _commit_local_change(env, foo, 'first')
    _commit_local_change(env, foo, 'second')

    result = cmd_git_nested('verify bar --diffs', cwd=foo, check=False)
    assert result.returncode == 1
    assert "differs from its upstream commit with 0 diffs" in result.output
    assert "use --output to have the whole diff written" in result.output

    result = cmd_git_nested('verify -o out/bar.diff bar --diffs', cwd=foo, check=False)
    assert result.returncode == 1
    assert "wrote the whole diff to out/bar.diff" in result.output
    diff = (foo / 'out' / 'bar.diff').read_text()
    assert "+first" in diff
    assert "+second" in diff
    assert ".gitnested" not in diff

    result = cmd_git_nested('verify bar --diffs out/bar.diff', cwd=foo)
    assert result.output.strip().endswith(" with 1 diff")
    _commit_local_change(env, foo, 'third')
    cmd_git_nested('verify -o out/bar.diff bar --diffs out/bar.diff', cwd=foo, check=False)
    assert "+third" in (foo / 'out' / 'bar.diff').read_text()
    cmd_git_nested('verify bar --diffs out/bar.diff', cwd=foo)


def test_verify_a_patch_outside_the_repository(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _commit_local_change(env, foo, 'first')
    outside = env.tmp / 'outside'

    cmd_git_nested(['verify', '-o', str(outside), 'bar'], cwd=foo, check=False)
    patch = outside / '0001-TODO-title.patch'
    result = cmd_git_nested(['verify', 'bar', '--patches', str(patch)], cwd=foo)
    assert f"applying {patch.as_posix()}" in result.output


def test_verify_patches_and_diffs_together(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('verify bar --patches a.patch --diffs b.diff', cwd=env.workspace / 'foo', check=False)
    assert result.returncode != 0
    assert "--patches and --diffs can't be used together" in result.output
