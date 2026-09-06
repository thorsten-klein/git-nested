"""The hand-written docs are the ones that can drift away from the parser."""

from pathlib import Path

import pytest

from git_nested.cli.spec import COMMAND_HELP, GLOBAL_ARG_SPECS

_ROOT = Path(__file__).parent.parent.parent
MANPAGE = (_ROOT / 'man' / 'man1' / 'git-nested.1').read_text()
DIAGRAMS = (_ROOT / 'docs' / 'diagrams.md').read_text()

# `completion` prints a shell script and runs no git command, so there is
# nothing for a call diagram to show.
_UNDIAGRAMMED = {'completion'}


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
    """docs/diagrams.md is how the git calls behind a command are explained."""
    assert f"\n## {command}\n" in DIAGRAMS
