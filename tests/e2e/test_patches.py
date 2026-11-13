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


def test_push_leaves_the_patches_folder_out(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = _with_patches(env)

    cmd_git_nested('push -b master bar', cwd=foo)
    upstream = env.upstream / 'bar'
    pushed = env.run(['git', 'ls-tree', '-r', '--name-only', 'master'], cwd=upstream).stdout
    assert FOLDER not in pushed
    assert env.run(['git', 'show', 'master:Bar'], cwd=upstream).stdout == "local\n"


def test_patches_create_writes_to_a_folder_outside_the_subdir(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    cmd_git_nested(['config', 'bar', 'patches', '../patches/bar'], cwd=foo)
    (foo / 'bar' / 'Bar').write_text("local\n")
    _commit(env, foo, 'local change')

    cmd_git_nested('patches create bar', cwd=foo)
    assert [patch.name for patch in (foo / 'patches' / 'bar').glob('*.patch')] == ['0001-TODO-title.patch']


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


def _set(env, foo, line):
    """Add `line` to the nested section of bar/.gitnested, and commit"""
    gitnested = foo / 'bar' / '.gitnested'
    gitnested.write_text(gitnested.read_text().replace('nested:\n', f'nested:\n{line}'))
    _commit(env, foo, 'set up bar')


def test_verify_writes_no_patch_for_a_setup_the_patches_do_not_work_with(foo_bar_cloned_and_nested):
    env = foo_bar_cloned_and_nested
    foo = env.workspace / 'foo'
    _set(env, foo, '  squash: false\n')
    (foo / 'bar' / 'Bar').write_bytes(b"local\n")
    _commit(env, foo, 'local change')

    result = cmd_git_nested('verify bar', cwd=foo, check=False)
    assert "use --output to have the missing one written" in result.output
    assert not (foo / 'bar' / FOLDER).exists()


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
