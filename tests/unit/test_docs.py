"""The hand-written docs are the ones that can drift away from the parser."""

from pathlib import Path

import pytest

from git_nested.cli.spec import COMMAND_HELP, GLOBAL_ARG_SPECS, SUBPARSER_ARG_SPECS, VALID_COMMAND_OPTIONS
from git_nested.gitfile import CONFIG_FIELDS

_ROOT = Path(__file__).parent.parent.parent
_DOC = _ROOT / 'doc'
MANPAGE = (_ROOT / 'man' / 'man1' / 'git-nested.1').read_text()
DIAGRAMS = (_DOC / 'architecture' / 'diagrams.md').read_text(encoding='utf-8')
CLI_INDEX = (_DOC / 'cli' / 'index.md').read_text(encoding='utf-8')
SITE_INDEX = (_DOC / 'index.md').read_text(encoding='utf-8')
GITNESTED_FILE = (_DOC / 'configuration' / 'gitnested-file.md').read_text(encoding='utf-8')
CONFIG_PAGE = (_DOC / 'cli' / 'config.md').read_text(encoding='utf-8')

# `completion` prints a shell script and runs no git command, so there is
# nothing for a call diagram to show.
_UNDIAGRAMMED = {'completion'}

_FLAG_NAMES = {opt: names for opt, names, _ in SUBPARSER_ARG_SPECS}


def _command_page(command: str) -> str:
    return (_DOC / 'cli' / f'{command}.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('command', sorted(COMMAND_HELP))
def test_every_command_is_documented(command):
    """A new subcommand has to be added to the COMMANDS section too."""
    assert f".B {command}\n" in MANPAGE


@pytest.mark.parametrize('command', sorted(COMMAND_HELP))
def test_the_summary_matches_the_parser(command):
    """And with the same words --help uses, so the two cannot say different things."""
    assert COMMAND_HELP[command] in MANPAGE


@pytest.mark.parametrize('names', [names for names, _ in GLOBAL_ARG_SPECS])
def test_every_global_flag_is_documented(names):
    """The OPTIONS section covers the flags accepted before the command."""
    assert all(name.replace('-', '\\-') in MANPAGE for name in names)


@pytest.mark.parametrize('command', sorted(set(COMMAND_HELP) - _UNDIAGRAMMED))
def test_every_command_has_a_call_diagram(command):
    """doc/architecture/diagrams.md is how the git calls behind a command are explained."""
    assert f"\n## {command}\n" in DIAGRAMS


@pytest.mark.parametrize('command', sorted(COMMAND_HELP))
def test_every_command_has_a_page(command):
    """Each command has its own page, titled with its name."""
    assert _command_page(command).startswith(f"# `git nested {command}`\n")


@pytest.mark.parametrize('command', sorted(COMMAND_HELP))
def test_every_command_is_listed(command):
    """The command list and the site menu link the page."""
    assert f"]({command}.md)" in CLI_INDEX
    assert f"](cli/{command}.md)" in SITE_INDEX
    assert f"\ncli/{command}\n" in SITE_INDEX


@pytest.mark.parametrize('command', sorted(COMMAND_HELP))
def test_every_command_page_has_its_summary(command):
    """The command page opens with the words --help uses."""
    assert COMMAND_HELP[command].capitalize() in _command_page(command)


@pytest.mark.parametrize(
    ('command', 'flag'),
    [
        (command, flag)
        for command, options in sorted(VALID_COMMAND_OPTIONS.items())
        for opt in options
        for flag in _FLAG_NAMES[opt]
    ],
)
def test_every_option_is_documented(command, flag):
    """Each option a command takes is on that command's page."""
    assert f"`{flag}" in _command_page(command)


@pytest.mark.parametrize('names', [names for names, _ in GLOBAL_ARG_SPECS])
def test_every_global_flag_is_on_the_overview(names):
    """The flags every command takes are on the overview page."""
    assert all(f"`{name}`" in CLI_INDEX for name in names)


@pytest.mark.parametrize('field', sorted(CONFIG_FIELDS))
def test_every_gitnested_field_is_documented(field):
    """Each field of .gitnested has its own section and a row in the config table."""
    assert f"\n### `{field}`\n" in GITNESTED_FILE
    assert f"| `{field}` | {CONFIG_FIELDS[field].replace(chr(39), '`')} |" in CONFIG_PAGE
