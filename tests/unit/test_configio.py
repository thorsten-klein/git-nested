"""Unit tests for reading and writing .gitnested as YAML or TOML"""

import sys

import pytest
from fakes import FakeGit

from git_nested import GitNestedError, configio, gitfile
from git_nested.messages import GITNESTED_HEADER

needs_tomllib = pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib needs Python 3.11")

DATA = {
    'nested': {
        'remote': 'https://example.com/lib "x"\\y',
        'branch': 'main',
        'squash': False,
        'filter': ['src', 'docs/.*\\.md'],
        'depth': 3,
        'pin': None,
        'note': 'ä\x7f',
    }
}


def test_toml_is_found_by_its_table():
    assert configio.is_toml_text('# comment\n[nested]\nremote = "x"\n')
    assert not configio.is_toml_text('nested:\n  remote: x\n')


def test_yaml_is_the_default(tmp_path):
    gitnested = tmp_path / '.gitnested'
    configio.write(gitnested, {'nested': {'remote': 'x'}})
    assert gitnested.read_text() == GITNESTED_HEADER + 'nested:\n  remote: x\n'
    assert not configio.is_toml(gitnested)


def test_toml_is_written(tmp_path):
    gitnested = tmp_path / '.gitnested'
    configio.write(gitnested, DATA, toml=True)
    assert gitnested.read_text(encoding='utf-8') == GITNESTED_HEADER + (
        '[nested]\n'
        'remote = "https://example.com/lib \\"x\\"\\\\y"\n'
        'branch = "main"\n'
        'squash = false\n'
        'filter = ["src", "docs/.*\\\\.md"]\n'
        'depth = 3\n'
        'note = "ä\\u007f"\n'
    )


@needs_tomllib
def test_toml_reads_back_what_was_written(tmp_path):
    gitnested = tmp_path / '.gitnested'
    configio.write(gitnested, DATA, toml=True)
    expected = {'nested': {k: v for k, v in DATA['nested'].items() if v is not None}}
    assert configio.read(gitnested) == expected


@needs_tomllib
def test_a_write_keeps_the_format(tmp_path):
    gitnested = tmp_path / '.gitnested'
    configio.write(gitnested, {'nested': {'remote': 'x'}}, toml=True)
    configio.write(gitnested, {'nested': {'remote': 'y'}})
    assert configio.is_toml(gitnested)
    assert configio.read(gitnested) == {'nested': {'remote': 'y'}}


@pytest.mark.parametrize('text', ['nested: [', '[nested]\nremote = '])
@needs_tomllib
def test_a_broken_file_is_an_error(tmp_path, text):
    gitnested = tmp_path / '.gitnested'
    gitnested.write_text(text)
    with pytest.raises(GitNestedError, match=r'cannot read .*\.gitnested'):
        configio.read(gitnested)


def test_toml_needs_python_3_11(monkeypatch):
    monkeypatch.setattr(configio, 'tomllib', None)
    with pytest.raises(GitNestedError, match=r"x/\.gitnested is TOML, which needs Python 3\.11 or newer"):
        configio.parse('[nested]\n', 'x/.gitnested')


def test_an_empty_file_is_empty():
    assert configio.parse('') == {}


def _format(value):
    return FakeGit().respond('config', '--get', 'nested.format', stdout=value, returncode=0 if value else 1)


@pytest.mark.parametrize(('value', 'toml'), [('', False), ('yaml', False), ('toml', True)])
@needs_tomllib
def test_nested_format_picks_the_format_of_a_new_file(value, toml):
    assert gitfile.new_file_is_toml(_format(value)) is toml


def test_nested_format_must_be_known():
    with pytest.raises(GitNestedError, match=r"nested\.format is json; use one of yaml, toml"):
        gitfile.new_file_is_toml(_format('json'))


def test_nested_format_toml_needs_python_3_11(monkeypatch):
    monkeypatch.setattr(configio, 'tomllib', None)
    with pytest.raises(GitNestedError, match=r"nested\.format is TOML, which needs Python 3\.11 or newer"):
        gitfile.new_file_is_toml(_format('toml'))
