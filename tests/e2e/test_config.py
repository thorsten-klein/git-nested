"""Tests for git nested config command"""

import subprocess

from conftest import assert_gitnested_field, cmd_git_nested


def test_config_prints_every_field(foo_bar_cloned_and_nested):
    """With no key, every field the file sets is printed as 'key value'."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config bar', cwd=env.workspace / 'foo')

    fields = dict(line.split(' ', 1) for line in result.stdout.splitlines())
    assert list(fields) == ['remote', 'branch', 'method', 'commit', 'parent', 'cmdver']
    assert fields['remote'] == str(env.upstream / 'bar')
    assert fields['method'] == 'merge'


def test_config_prints_one_field(foo_bar_cloned_and_nested):
    """With a key and no value, only that field's value is printed."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config bar method', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == 'merge'


def test_config_prints_a_filter_as_one_line(foo_bar_cloned):
    """A filter is a YAML list; it prints as one space-separated line."""
    env = foo_bar_cloned
    cmd_git_nested(['clone', str(env.upstream / 'bar'), '--filter', 'doc', '--filter', 'src'], env.workspace / 'foo')

    result = cmd_git_nested('config bar filter', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == 'doc src'


def test_config_prints_nothing_for_an_unset_field(foo_bar_cloned_and_nested):
    """A field the file does not set is not an error, it is simply empty."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config bar filter', cwd=env.workspace / 'foo')
    assert result.stdout.strip() == ''


def test_config_writes_a_field(foo_bar_cloned_and_nested):
    """With a value, the field is written and the change is staged."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config bar method rebase', cwd=env.workspace / 'foo')

    assert result.stdout.strip() == "Set 'method' of 'bar' to 'rebase'."
    assert_gitnested_field(env.workspace / 'foo' / 'bar' / '.gitnested', method='rebase')

    staged = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        cwd=env.workspace / 'foo',
        capture_output=True,
        text=True,
        check=True,
    )
    assert 'bar/.gitnested' in staged.stdout


def test_config_leaves_the_other_fields_alone(foo_bar_cloned_and_nested):
    """Writing one field must not rewrite commit/parent/cmdver as a side effect."""
    env = foo_bar_cloned_and_nested
    gitnested = env.workspace / 'foo' / 'bar' / '.gitnested'
    before = cmd_git_nested('config bar', cwd=env.workspace / 'foo').stdout

    cmd_git_nested('config bar branch other', cwd=env.workspace / 'foo')

    after = cmd_git_nested('config bar', cwd=env.workspace / 'foo').stdout
    assert after == before.replace('branch master', 'branch other')
    assert gitnested.read_text().startswith('#')


def test_config_rejects_a_read_only_field(foo_bar_cloned_and_nested):
    """The fields the nested operations own cannot be set by hand."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config bar commit deadbeef', cwd=env.workspace / 'foo', check=False)

    assert result.returncode != 0
    assert "'commit' is written by git-nested itself" in result.stderr
    assert "Settable fields: remote, branch, method, parent." in result.stderr


def test_config_rejects_an_unknown_field(foo_bar_cloned_and_nested):
    """A key that is not part of a .gitnested file at all is a usage error."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config bar bogus', cwd=env.workspace / 'foo', check=False)

    assert result.returncode != 0
    assert "Unknown config key 'bogus'." in result.stderr


def test_config_rejects_an_invalid_method(foo_bar_cloned_and_nested):
    """'method' only takes the two values the nested operations understand."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config bar method squash', cwd=env.workspace / 'foo', check=False)

    assert result.returncode != 0
    assert "'squash' is not a valid 'method'. Use one of: merge, rebase." in result.stderr


def test_config_without_a_subdir_fails(foo_bar_cloned_and_nested):
    """There is nothing to read without knowing which nested repository."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config', cwd=env.workspace / 'foo', check=False)

    assert result.returncode != 0
    assert "subdir not set" in result.stderr


def test_config_with_an_absolute_subdir_fails(foo_bar_cloned_and_nested):
    """A subdir is always relative to the repository root."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested(f'config {env.workspace / "foo" / "bar"}', cwd=env.workspace / 'foo', check=False)

    assert result.returncode != 0
    assert "should not be absolute path" in result.stderr


def test_config_on_a_subdir_that_is_not_nested_fails(foo_bar_cloned_and_nested):
    """A directory with no .gitnested file has no configuration to print."""
    env = foo_bar_cloned_and_nested
    result = cmd_git_nested('config doc', cwd=env.workspace / 'foo', check=False)

    assert result.returncode != 0
    assert "No 'doc/.gitnested' file." in result.stderr
