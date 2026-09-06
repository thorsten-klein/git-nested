"""Fixtures for the tests that drive git-nested's internals directly.

The e2e tests go through `cmd_git_nested`, which runs a whole command and so
wires the output layer up on the way past. A unit test calling a single
function has to do that part itself -- hence `printing`.
"""

import pytest

from git_nested import output


@pytest.fixture
def printing():
    """Attach the stderr handler for the duration of one test.

    Everything git-nested says as a diagnostic goes through the logger, and
    the logger prints nothing until `configure` puts the handler on -- which
    is what `main` does per command.

    What lands on stderr is read back through capsys rather than through a
    redirect installed here: pytest resumes its own capturing at the start
    of the call phase, which would replace any sys.stderr a fixture had put
    in place during setup.
    """
    detach = output.configure()
    try:
        yield
    finally:
        detach()


@pytest.fixture
def no_colour(monkeypatch):
    """Force the uncoloured branch, whatever the environment says."""
    monkeypatch.delenv('FORCE_COLOR', raising=False)
    monkeypatch.setenv('NO_COLOR', '1')
