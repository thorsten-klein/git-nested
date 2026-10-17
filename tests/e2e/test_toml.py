"""Tests for a .gitnested file written in TOML"""

import sys

import pytest
from conftest import cmd_git_nested

pytestmark = pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib needs Python 3.11")


@pytest.fixture
def toml_cloned(foo_bar_cloned):
    env = foo_bar_cloned
    env.run(['git', 'config', 'nested.format', 'toml'], cwd=env.workspace / 'foo')
    cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], env.workspace / 'foo')
    return env


def test_clone_writes_toml(toml_cloned):
    env = toml_cloned
    text = (env.workspace / 'foo' / 'bar' / '.gitnested').read_text()
    assert '[nested]\n' in text
    assert f'remote = "{(env.upstream / "bar").as_posix()}"\n' in text
    assert 'method = "merge"\n' in text


def test_pull_and_config_keep_toml(toml_cloned):
    env = toml_cloned
    foo = env.workspace / 'foo'
    env.add_new_files('Bar2', cwd=env.workspace / 'bar')
    env.run(['git', 'push'], cwd=env.workspace / 'bar')
    # Only new files take nested.format; this one stays TOML.
    env.run(['git', 'config', 'nested.format', 'yaml'], cwd=foo)

    cmd_git_nested('pull bar', cwd=foo)
    cmd_git_nested('config bar method rebase', cwd=foo)

    assert (foo / 'bar' / 'Bar2').is_file()
    text = (foo / 'bar' / '.gitnested').read_text()
    assert '[nested]\n' in text
    assert 'method = "rebase"\n' in text
    assert cmd_git_nested('config bar method', cwd=foo).stdout.strip() == 'rebase'
    assert 'Behind Upstream: 0' in cmd_git_nested('status', cwd=foo).stdout


def test_an_unknown_format_is_refused_before_the_clone(foo_bar_cloned):
    env = foo_bar_cloned
    foo = env.workspace / 'foo'
    env.run(['git', 'config', 'nested.format', 'json'], cwd=foo)

    result = cmd_git_nested(['clone', (env.upstream / 'bar').as_posix()], foo, check=False)

    assert result.returncode == 1
    assert "nested.format is json; use one of yaml, toml" in result.output
    assert not (foo / 'bar').exists()
