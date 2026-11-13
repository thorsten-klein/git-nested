"""Tests for the `patches` field: local changes kept as patch files"""

import re

import pytest
from conftest import cmd_git_nested

FOLDER = '.gitnested.patches'


def _patch_names(foo):
    return sorted(patch.name for patch in (foo / 'bar' / FOLDER).glob('*.patch'))


def _commit(env, foo, message):
    env.run(['git', 'add', '-A'], cwd=foo)
    env.run(['git', 'commit', '-q', '-m', message], cwd=foo)


def _with_patches(env):
    """foo with bar nested, the patches on, a local change to bar/Bar, and that change as a patch"""
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    # bytes: write_text would make it CRLF on Windows
    (foo / 'bar' / 'Bar').write_bytes(b"local\n")
    _commit(env, foo, 'local change')
    result = cmd_git_nested('patches create bar', cwd=foo)
    assert f"wrote the missing patch bar/{FOLDER}/0001-TODO-title.patch" in result.output
    _commit(env, foo, 'the patch')
    return foo


def _upstream_change(env, path, text):
    bar = env.workspace / 'bar'
    (bar / path).parent.mkdir(parents=True, exist_ok=True)
    (bar / path).write_bytes(text if isinstance(text, bytes) else text.encode())
    env.run(['git', 'add', path], cwd=bar)
    env.run(['git', 'commit', '-q', '-m', f'upstream {path}'], cwd=bar)
    env.run(['git', 'push', '-q'], cwd=bar)


def test_patches_verify_checks_the_folder(foo_bar_cloned_and_nested):
    foo = _with_patches(foo_bar_cloned_and_nested)
    result = cmd_git_nested('patches verify bar', cwd=foo)
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
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 1 patch")


def test_pull_refuses_local_changes_that_are_not_in_the_patches(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    (foo / 'bar' / 'Other').write_text("not in a patch\n")
    _commit(env, foo, 'more local work')

    result = cmd_git_nested('pull bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: has changes that are not in its patches\n" in result.output
    assert "'git nested patches create bar' writes the missing one" in result.output


def test_pull_drops_a_patch_upstream_has(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    _upstream_change(env, 'Bar', "local\n")

    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'Bar').read_text() == "local\n"
    assert _patch_names(foo) == []
    assert not env.run(['git', 'ls-files', f'bar/{FOLDER}'], cwd=foo).stdout


def test_pull_keeps_crlf_in_the_patches(foo_bar_cloned_and_nested):
    """A CR in a patch is content, also when upstream already has the change"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    for repo in (foo, env.workspace / 'bar'):
        env.run(['git', 'config', 'core.autocrlf', 'false'], cwd=repo)
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    (foo / 'bar' / 'Bar').write_bytes(b"local\r\n")
    _commit(env, foo, 'local change')
    cmd_git_nested('patches create bar', cwd=foo)
    _commit(env, foo, 'the patch')
    _upstream_change(env, 'Bar', b"local\r\n")

    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'Bar').read_bytes() == b"local\r\n"
    assert _patch_names(foo) == []


def test_pull_takes_a_patch_file_the_checkout_made_crlf(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    _upstream_change(env, 'New', "new\n")
    env.run(['git', 'config', 'core.autocrlf', 'true'], cwd=foo)
    patch = foo / 'bar' / FOLDER / '0001-TODO-title.patch'
    patch.unlink()
    env.run(['git', 'checkout', '--', patch.as_posix()], cwd=foo)
    assert patch.read_bytes().split(b'\n')[0].endswith(b'\r')

    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'Bar').read_text() == "local\n"
    assert (foo / 'bar' / 'New').read_text() == "new\n"


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
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 1 patch")


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
    cmd_git_nested('patches create bar/inner', cwd=foo)
    _commit(env, foo, 'inner patch')
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 1 patch")

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
    (foo / 'bar' / FOLDER).mkdir()
    (foo / 'bar' / FOLDER / '0001-x.patch').write_bytes(b"x\n")
    _commit(env, foo, 'path')

    result = cmd_git_nested('pull bar', cwd=foo, check=False)
    assert "bar: patches do not work with filter, exclude or path yet" in result.output


def test_push_commit_empties_the_patches(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)

    cmd_git_nested('push --commit -b master bar', cwd=foo)
    assert _patch_names(foo) == []
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 0 patches")

    env.run(['git', 'pull', '-q'], cwd=env.workspace / 'bar')
    _upstream_change(env, 'New', "new\n")
    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'New').read_bytes() == b"new\n"
    assert _patch_names(foo) == []


def test_patches_create_writes_to_a_folder_outside_the_subdir(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', '../patches/bar'], cwd=foo)
    (foo / 'bar' / 'Bar').write_text("local\n")
    _commit(env, foo, 'local change')

    cmd_git_nested('patches create bar', cwd=foo)
    assert [patch.name for patch in (foo / 'patches' / 'bar').glob('*.patch')] == ['0001-TODO-title.patch']


def test_pull_with_a_patches_folder_outside_the_subdir(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', '../patches/bar'], cwd=foo)
    (foo / 'bar' / 'Bar').write_text("local\n")
    _commit(env, foo, 'local change')
    cmd_git_nested('patches create bar', cwd=foo)
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

    result = cmd_git_nested('patches create bar', cwd=foo, check=False)
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
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 1 patch")


def test_reclone_without_any_patches_yet(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    _commit(env, foo, 'patches')
    _upstream_change(env, 'New', "new\n")

    cmd_git_nested('clone --force ../../upstream/bar bar', cwd=foo)
    assert (foo / 'bar' / 'New').read_text() == "new\n"
    assert _patch_names(foo) == []


def _split(patch, subjects):
    """Split `patch` into one patch per changed file, as a user would by hand.

    Each new patch gets the next subject and is named as format-patch
    names it. The single patch is removed.
    """
    text = patch.read_bytes().decode()
    header, *diffs = re.split(r'^(?=diff --git )', text, flags=re.MULTILINE)
    header = header[: header.index('\n---\n') + 1]
    names = []
    for number, (subject, diff) in enumerate(zip(subjects, diffs, strict=True), start=1):
        name = f"{number:04d}-{subject.replace(' ', '-')}.patch"
        own = header.replace("Subject: [PATCH] TODO: title", f"Subject: [PATCH] {subject}")
        own = own.replace("TODO: description", f"{subject}.")
        (patch.parent / name).write_bytes(f"{own}---\n{diff}".encode())
        names.append(name)
    patch.unlink()
    return names


def test_patches_split_by_hand_on_a_branch_survive_a_squash_merge_and_a_pull(foo_bar_cloned_and_nested):
    """The usual way to work: change bar on a branch, have verify write the patch,
    split it by hand, squash-merge the branch, and pull later on"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    _commit(env, foo, 'patches')

    env.run(['git', 'checkout', '-q', '-b', 'feature'], cwd=foo)
    (foo / 'bar' / 'Bar').write_bytes(b"local\n")
    _commit(env, foo, 'change Bar')
    (foo / 'bar' / 'Extra').write_bytes(b"extra\n")
    _commit(env, foo, 'add Extra')

    result = cmd_git_nested('patches create bar', cwd=foo)
    assert f"wrote the missing patch bar/{FOLDER}/0001-TODO-title.patch" in result.output
    names = _split(foo / 'bar' / FOLDER / '0001-TODO-title.patch', ["Change Bar", "Add Extra"])
    assert names == ['0001-Change-Bar.patch', '0002-Add-Extra.patch']
    result = cmd_git_nested('patches create bar', cwd=foo)
    assert f"bar: wrote the patches again: {', '.join(names)}" in result.output
    assert _patch_names(foo) == names
    _commit(env, foo, 'the patches')
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 2 patches")

    env.run(['git', 'checkout', '-q', 'master'], cwd=foo)
    env.run(['git', 'merge', '-q', '--squash', 'feature'], cwd=foo)
    env.run(['git', 'commit', '-q', '-m', 'feature, squashed'], cwd=foo)
    env.run(['git', 'branch', '-q', '-D', 'feature'], cwd=foo)
    assert _patch_names(foo) == names
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 2 patches")

    _upstream_change(env, 'New', "new\n")
    cmd_git_nested('pull bar', cwd=foo)

    assert (foo / 'bar' / 'New').read_bytes() == b"new\n"
    assert (foo / 'bar' / 'Bar').read_bytes() == b"local\n"
    assert (foo / 'bar' / 'Extra').read_bytes() == b"extra\n"
    assert _patch_names(foo) == names
    first, second = ((foo / 'bar' / FOLDER / name).read_text() for name in names)
    assert "Subject: [PATCH] Change Bar" in first
    assert "+local" in first
    assert "Extra" not in first
    assert "Subject: [PATCH] Add Extra" in second
    assert "+extra" in second
    assert "+local" not in second
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 2 patches")


def test_a_conflict_in_split_patches_is_resolved_patch_by_patch(foo_bar_cloned_and_nested):
    """Each patch that conflicts is resolved in turn; the commit writes them again, still split"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    (foo / 'bar' / 'Bar').write_bytes(b"local\n")
    (foo / 'bar' / 'Extra').write_bytes(b"extra\n")
    _commit(env, foo, 'local changes')
    cmd_git_nested('patches create bar', cwd=foo)
    names = _split(foo / 'bar' / FOLDER / '0001-TODO-title.patch', ["Change Bar", "Add Extra"])
    cmd_git_nested('patches create bar', cwd=foo)
    _commit(env, foo, 'the patches')
    _upstream_change(env, 'Bar', "upstream\n")
    _upstream_change(env, 'Extra', "upstream extra\n")

    result = cmd_git_nested('pull bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "the patch 0001-Change-Bar.patch does not apply" in result.output

    worktree = foo / '.git' / 'tmp' / 'nested' / 'bar'
    continue_am = ['git', '-c', 'core.editor=true', 'am', '--continue']
    (worktree / 'Bar').write_bytes(b"upstream and local\n")
    env.run(['git', 'add', 'Bar'], cwd=worktree)
    stopped = env.run(continue_am, cwd=worktree, check=False)
    assert stopped.returncode != 0
    assert "Add Extra" in stopped.stdout + stopped.stderr

    (worktree / 'Extra').write_bytes(b"upstream extra\nextra\n")
    env.run(['git', 'add', 'Extra'], cwd=worktree)
    env.run(continue_am, cwd=worktree)
    cmd_git_nested('commit bar', cwd=foo)

    assert (foo / 'bar' / 'Bar').read_bytes() == b"upstream and local\n"
    assert (foo / 'bar' / 'Extra').read_bytes() == b"upstream extra\nextra\n"
    assert _patch_names(foo) == names
    first, second = ((foo / 'bar' / FOLDER / name).read_text() for name in names)
    assert "+upstream and local" in first
    assert "Extra" not in first
    assert "+extra" in second
    assert "Bar" not in second
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 2 patches")


def test_reclone_names_a_first_patch_that_is_not_a_patch(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    (foo / 'bar' / FOLDER / '0000-garbage.patch').write_bytes(b"garbage\n")
    _commit(env, foo, 'garbage')

    result = cmd_git_nested('clone --force ../../upstream/bar bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: the patch 0000-garbage.patch does not apply on upstream " in result.output


def _set(env, foo, line):
    """Add `line` to the nested section of bar/.gitnested, and commit"""
    gitnested = foo / 'bar' / '.gitnested'
    gitnested.write_text(gitnested.read_text().replace('nested:\n', f'nested:\n{line}'))
    _commit(env, foo, 'set up bar')


def test_without_patches_yet_a_pull_merges_as_before(foo_bar_cloned_and_nested):
    """A nested repo from before the patches keeps working: no patch, no refusal"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    (foo / 'bar' / 'Bar').write_bytes(b"local\n")
    _commit(env, foo, 'local change')
    _upstream_change(env, 'New', "new\n")

    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'Bar').read_bytes() == b"local\n"
    assert (foo / 'bar' / 'New').read_bytes() == b"new\n"
    assert not (foo / 'bar' / FOLDER).exists()


def test_patches_false_turns_them_off(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    cmd_git_nested(['config', 'bar', 'patches', 'false'], cwd=foo)
    (foo / 'bar' / 'Other').write_bytes(b"not in a patch\n")
    _commit(env, foo, 'patches off, and more local work')
    _upstream_change(env, 'New', "new\n")

    cmd_git_nested('pull bar', cwd=foo)
    assert (foo / 'bar' / 'Other').read_bytes() == b"not in a patch\n"
    result = cmd_git_nested('verify bar', cwd=foo, check=False)
    assert "use --output to have the missing one written" in result.output

    cmd_git_nested('push --commit -b master bar', cwd=foo)
    assert _patch_names(foo) == ['0001-TODO-title.patch']


def test_verify_writes_no_patch_for_a_setup_the_patches_do_not_work_with(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _set(env, foo, '  squash: false\n')
    (foo / 'bar' / 'Bar').write_bytes(b"local\n")
    _commit(env, foo, 'local change')

    result = cmd_git_nested('verify bar', cwd=foo, check=False)
    assert "use --output to have the missing one written" in result.output
    assert not (foo / 'bar' / FOLDER).exists()


def test_patches_verify_refuses_a_plain_diff(foo_bar_cloned_and_nested):
    """A pull applies the patches with git am, so verify does too: a plain diff is not a patch"""
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    (foo / 'bar' / 'Bar').write_bytes(b"local\n")
    _commit(env, foo, 'local change')
    diff = env.run(['git', 'diff', 'HEAD~1', 'HEAD', '--relative=bar'], cwd=foo).stdout
    (foo / 'bar' / FOLDER).mkdir()
    (foo / 'bar' / FOLDER / '0001-plain.patch').write_text(diff)
    _commit(env, foo, 'a plain diff as patch')

    result = cmd_git_nested('patches verify bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert f"bar/{FOLDER}/0001-plain.patch: is not a patch" in result.output
    assert not (foo / '.git' / 'tmp' / 'patches').exists()


def test_a_pull_writes_the_patches_as_they_were(foo_bar_cloned_and_nested):
    """A patch that still fits comes back byte for byte: no commit id, no signature, no new name"""
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    folder = foo / 'bar' / FOLDER
    patch = folder / '0001-TODO-title.patch'
    patch.write_bytes(patch.read_bytes().replace(b'TODO: title', b'Change Bar'))
    patch.rename(folder / '0001-Change-Bar.patch')
    _commit(env, foo, 'the patch, named')
    before = (folder / '0001-Change-Bar.patch').read_bytes()

    _upstream_change(env, 'New', "new\n")
    cmd_git_nested('pull bar', cwd=foo)
    assert _patch_names(foo) == ['0001-Change-Bar.patch']
    assert (folder / '0001-Change-Bar.patch').read_bytes() == before


def test_patches_create_with_nothing_to_do(foo_bar_cloned_and_nested):
    foo = _with_patches(foo_bar_cloned_and_nested)
    result = cmd_git_nested('patches create bar', cwd=foo)
    assert result.output.strip() == "bar: the patches are up to date"


def test_patches_create_names_a_patch_after_its_title(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    patch = foo / 'bar' / FOLDER / '0001-TODO-title.patch'
    patch.write_bytes(patch.read_bytes().replace(b'TODO: title', b'Change Bar'))

    result = cmd_git_nested('patches create bar', cwd=foo)
    assert result.output.strip() == "bar: wrote the patches again: 0001-Change-Bar.patch, 0001-TODO-title.patch"
    assert _patch_names(foo) == ['0001-Change-Bar.patch']
    _commit(env, foo, 'the patch, named')
    assert cmd_git_nested('patches create bar', cwd=foo).output.strip() == "bar: the patches are up to date"


def test_patches_verify_finds_a_patch_create_would_change(foo_bar_cloned_and_nested):
    foo = _with_patches(foo_bar_cloned_and_nested)
    patch = foo / 'bar' / FOLDER / '0001-TODO-title.patch'
    patch.write_bytes(patch.read_bytes().replace(b'TODO: title', b'Change Bar'))

    result = cmd_git_nested('patches verify bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: the patches are not as git-nested writes them: 0001-Change-Bar.patch, 0001-TODO-title.patch" in (
        result.output
    )
    assert "'git nested patches create bar' writes them again" in result.output


def test_patches_create_adds_the_next_patch(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    (foo / 'bar' / 'Other').write_bytes(b"more\n")
    _commit(env, foo, 'more local work')

    result = cmd_git_nested('patches create bar', cwd=foo)
    assert f"wrote the missing patch bar/{FOLDER}/0002-TODO-title.patch" in result.output
    assert _patch_names(foo) == ['0001-TODO-title.patch', '0002-TODO-title.patch']
    second = (foo / 'bar' / FOLDER / '0002-TODO-title.patch').read_text()
    assert "+more" in second
    assert "+local" not in second


def test_patches_verify_all(foo_bar_cloned_and_nested):
    foo = _with_patches(foo_bar_cloned_and_nested)
    result = cmd_git_nested('patches verify --all', cwd=foo)
    assert result.output.strip().endswith(" with 1 patch")


@pytest.mark.parametrize(
    ('line', 'message'),
    [
        ('', "bar: the patches are off; 'git nested config bar patches <path>' turns them on"),
        ('  patches: false\n', "bar: the patches are off; 'git nested config bar patches <path>' turns them on"),
        (
            '  patches: .gitnested.patches\n  squash: false\n',
            "bar: patches do not work with filter, exclude, path or squash: false yet",
        ),
    ],
)
def test_patches_refuse_a_setup_without_them(foo_bar_cloned_and_nested, line, message):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    if line:
        _set(env, foo, line)
    result = cmd_git_nested('patches create bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert message in result.output


def test_patches_verify_finds_a_change_that_is_not_in_a_patch(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    (foo / 'bar' / 'Other').write_bytes(b"more\n")
    _commit(env, foo, 'more local work')

    result = cmd_git_nested('patches verify bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: has changes that are not in its patches\n" in result.output
    assert "Other" in result.output
    assert "'git nested patches create bar' writes the missing one" in result.output
    assert _patch_names(foo) == ['0001-TODO-title.patch']


def test_patches_verify_takes_a_patch_file_the_checkout_made_crlf(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    env.run(['git', 'config', 'core.autocrlf', 'true'], cwd=foo)
    patch = foo / 'bar' / FOLDER / '0001-TODO-title.patch'
    patch.unlink()
    env.run(['git', 'checkout', '--', patch.as_posix()], cwd=foo)
    assert patch.read_bytes().split(b'\n')[0].endswith(b'\r')

    assert cmd_git_nested('patches create bar', cwd=foo).output.strip() == "bar: the patches are up to date"


def test_patches_leave_a_nested_repo_inside_out(foo_bar_cloned_and_nested):
    """A nested repo inside is not in the outer patches. It has its own"""
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    cmd_git_nested(['clone', (env.upstream / 'foo').as_posix(), 'bar/inner'], cwd=foo)
    cmd_git_nested(['config', 'bar/inner', 'patches', FOLDER], cwd=foo)
    (foo / 'bar' / 'inner' / 'Foo').write_text("inner local\n")
    _commit(env, foo, 'inner change')

    assert cmd_git_nested('patches create bar', cwd=foo).output.strip() == "bar: the patches are up to date"
    cmd_git_nested('patches create bar/inner', cwd=foo)
    _commit(env, foo, 'inner patch')
    assert cmd_git_nested('patches create bar/inner', cwd=foo).output.strip() == "bar/inner: the patches are up to date"
    assert 'inner' not in (foo / 'bar' / FOLDER / '0001-TODO-title.patch').read_text()


def test_patches_refuse_a_path(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    gitnested = foo / 'bar' / '.gitnested'
    gitnested.write_text(
        gitnested.read_text().replace('nested:\n', 'nested:\n  patches: .gitnested.patches\n  path: bard\n')
    )
    (foo / 'bar' / FOLDER).mkdir()
    (foo / 'bar' / FOLDER / '0001-x.patch').write_bytes(b"x\n")
    _commit(env, foo, 'path')

    result = cmd_git_nested('patches create bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: patches do not work with filter, exclude or path yet" in result.output


def test_patches_create_refuses_a_plain_diff(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', FOLDER], cwd=foo)
    (foo / 'bar' / 'Bar').write_bytes(b"local\n")
    _commit(env, foo, 'local change')
    diff = env.run(['git', 'diff', 'HEAD~1', 'HEAD', '--relative=bar'], cwd=foo).stdout
    (foo / 'bar' / FOLDER).mkdir()
    (foo / 'bar' / FOLDER / '0001-plain.patch').write_text(diff)
    _commit(env, foo, 'a plain diff as patch')

    result = cmd_git_nested('patches create bar', cwd=foo, check=False)
    assert result.returncode == 1
    assert f"bar/{FOLDER}/0001-plain.patch: is not a patch" in result.output
    assert (foo / 'bar' / FOLDER / '0001-plain.patch').read_text() == diff


def _two_patches(env):
    """foo with bar nested and two patches: one changes Bar, one adds Other"""
    foo = _with_patches(env)
    (foo / 'bar' / 'Other').write_bytes(b"more\n")
    _commit(env, foo, 'more local work')
    cmd_git_nested('patches create bar', cwd=foo)
    _commit(env, foo, 'the second patch')
    return foo


def test_patches_drop_removes_a_patch_and_its_changes(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _two_patches(env)
    upstream_bar = env.run(['git', 'show', 'HEAD:Bar'], cwd=env.workspace / 'bar').stdout

    result = cmd_git_nested(['patches', 'drop', 'bar', f'bar/{FOLDER}/0001-TODO-title.patch'], cwd=foo)
    assert result.output.strip() == "bar: dropped 0001-TODO-title.patch"
    assert (foo / 'bar' / 'Bar').read_text() == upstream_bar
    assert (foo / 'bar' / 'Other').read_bytes() == b"more\n"
    assert _patch_names(foo) == ['0001-TODO-title.patch']
    assert "+more" in (foo / 'bar' / FOLDER / '0001-TODO-title.patch').read_text()
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''
    message = env.run(['git', 'log', '-1', '--format=%s'], cwd=foo).stdout.strip()
    assert message == "bar: drop the patch 0001-TODO-title.patch"
    assert cmd_git_nested('patches verify bar', cwd=foo).output.strip().endswith(" with 1 patch")


def test_patches_drop_the_last_patch_by_name(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    upstream_bar = env.run(['git', 'show', 'HEAD:Bar'], cwd=env.workspace / 'bar').stdout

    cmd_git_nested('patches drop bar 0001-TODO-title.patch', cwd=foo)
    assert (foo / 'bar' / 'Bar').read_text() == upstream_bar
    assert _patch_names(foo) == []
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''


def test_patches_drop_stops_if_a_later_patch_needs_it(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)
    (foo / 'bar' / 'Bar').write_bytes(b"local\nand more\n")
    _commit(env, foo, 'more on Bar')
    cmd_git_nested('patches create bar', cwd=foo)
    _commit(env, foo, 'the second patch')
    head = env.run(['git', 'rev-parse', 'HEAD'], cwd=foo).stdout

    result = cmd_git_nested('patches drop bar 0001-TODO-title.patch', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: the patch 0002-TODO-title.patch does not apply on upstream" in result.output
    assert env.run(['git', 'rev-parse', 'HEAD'], cwd=foo).stdout == head
    assert env.run(['git', 'status', '--porcelain'], cwd=foo).stdout == ''


@pytest.mark.parametrize(
    ('args', 'message'),
    [
        ('patches drop bar no-such.patch', "bar: no-such.patch is not one of its patches"),
        ('patches drop bar', "drop needs the patches to drop; create and verify take none"),
        ('patches create bar 0001-TODO-title.patch', "drop needs the patches to drop; create and verify take none"),
    ],
)
def test_patches_drop_refuses(foo_bar_cloned_and_nested, args, message):
    foo = _with_patches(foo_bar_cloned_and_nested)
    result = cmd_git_nested(args, cwd=foo, check=False)
    assert result.returncode != 0
    assert message in result.output


def test_patches_drop_refuses_changes_that_are_not_in_a_patch(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _two_patches(env)
    (foo / 'bar' / 'Third').write_bytes(b"not in a patch\n")
    _commit(env, foo, 'not in a patch')

    result = cmd_git_nested('patches drop bar 0002-TODO-title.patch', cwd=foo, check=False)
    assert result.returncode == 1
    assert "bar: has changes that are not in its patches" in result.output


def test_patches_drop_refuses_a_dirty_worktree(foo_bar_cloned_and_nested):
    foo = _with_patches(foo_bar_cloned_and_nested)
    (foo / 'bar' / 'Bar').write_bytes(b"not committed\n")
    result = cmd_git_nested('patches drop bar 0001-TODO-title.patch', cwd=foo, check=False)
    assert result.returncode == 1
    assert "can't drop a patch" in result.output
