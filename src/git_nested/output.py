"""Everything git-nested says to the user.

Diagnostics go to stderr through the `git_nested` logger; `payload` goes to
stdout and carries what a script would read -- the `status` report, the
`diff` body, a `config` value, a completion script. Nothing else in the
package writes to a stream.

The logger holds only a NullHandler at import, so importing git_nested as a
library says nothing at all. `configure` attaches the handler that prints
and hands back the callable that detaches it again; the CLI holds that in a
try/finally, because a long-lived process -- the test suite builds hundreds
of GitNestedCommands -- would otherwise stack a handler per command and
print every line that many times over.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, NoReturn

from .errors import GitNestedError

if TYPE_CHECKING:
    from collections.abc import Callable

    from .models import Flags

# Below DEBUG: every git command as GitRunner issues it. Its own level so
# that `-v` can narrate the steps git-nested is taking without also listing
# the dozens of plumbing calls each step makes -- `-vv` adds those.
TRACE = 5
logging.addLevelName(TRACE, 'TRACE')

LOGGER = logging.getLogger('git_nested')
LOGGER.addHandler(logging.NullHandler())
# Whatever the embedding application has configured on the root logger, it
# does not get to print git-nested's lines a second time.
LOGGER.propagate = False

# Per level: the marker written ahead of the message, and the SGR parameters
# to wrap the line in when the stream can take colour.
_STYLES: dict[int, tuple[str, str]] = {
    TRACE: ('$ ', '2'),
    logging.DEBUG: ('* ', '2'),
    logging.INFO: ('', ''),
    logging.WARNING: ('git-nested: ', '33'),
    logging.ERROR: ('git-nested: ', '31'),
}


def _use_colour(stream) -> bool:
    """Whether to colour output on `stream`, asked at the moment of writing.

    Late, because the stream is resolved late too. FORCE_COLOR is honoured
    alongside NO_COLOR so that the coloured branch is reachable where there
    is no tty -- under pytest, and in CI.
    """
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR'):
        return True
    return hasattr(stream, 'isatty') and stream.isatty()


def _render(record: logging.LogRecord, colour: bool) -> str:
    """One line of output: the level's marker, the message, a newline."""
    marker, sgr = _STYLES[record.levelno]
    text = f"{marker}{record.getMessage()}"
    if colour and sgr:
        text = f"\033[{sgr}m{text}\033[0m"
    return text + "\n"


class _StderrHandler(logging.Handler):
    """Writes to whatever `sys.stderr` is at the moment of the write.

    logging.StreamHandler binds the stream handed to its constructor, which
    is the wrong object under contextlib.redirect_stderr -- and that is how
    the test suite captures an in-process run.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Write one rendered record to the current sys.stderr."""
        stream = sys.stderr
        stream.write(_render(record, _use_colour(stream)))
        stream.flush()


_HANDLER = _StderrHandler()


def configure() -> Callable[[], None]:
    """Start printing what the logger is told, at the default level.

    Returns:
        The callable that stops it again. Logger.addHandler already ignores
        a handler it holds, so calling this twice attaches one handler; the
        returned callable is what keeps that true across commands.
    """
    LOGGER.setLevel(logging.INFO)
    LOGGER.addHandler(_HANDLER)
    return lambda: LOGGER.removeHandler(_HANDLER)


def _level(flags: Flags) -> int:
    """The level `flags` asks for: `-q` quieter, `-v`/`-vv`/`-d` louder.

    `-d` is the spelling for "show me the git commands" on its own, which is
    where `-vv` also ends up; it exists because that is the question people
    actually arrive with, and counting v's to reach it is a poor way to ask.
    """
    if flags.debug:
        return TRACE
    if flags.quiet:
        return logging.WARNING
    return {0: logging.INFO, 1: logging.DEBUG}.get(flags.verbose, TRACE)


def set_level(flags: Flags) -> None:
    """Raise or lower the level, once the command line has been parsed."""
    LOGGER.setLevel(_level(flags))


def payload(text: str) -> None:
    """Write a command's actual result to stdout, whatever the level.

    This is the half of the output a script consumes -- a status report, a
    diff, a config value, a completion script -- so it is neither marked
    nor gated. Everything else git-nested says is a diagnostic and goes
    through the logger onto stderr.
    """
    print(text)


def trace(msg: str) -> None:
    """Record one git invocation (`-vv`)."""
    LOGGER.log(TRACE, msg)


def verbose(msg: str) -> None:
    """Narrate a step git-nested is taking (`-v`)."""
    LOGGER.debug(msg)


def say(msg: str) -> None:
    """Report what a command did."""
    LOGGER.info(msg)


def warn(msg: str) -> None:
    """Report something worth knowing that did not stop the command."""
    LOGGER.warning(msg)


def error(msg: str) -> NoReturn:
    """Abort the command with `msg`.

    Nothing is written here. The message reaches the user from `report`,
    called by `cli.app` if the error is still unhandled by the time it
    leaves the command -- so a caller that catches this one and raises a
    clearer one in its place leaves no stray line behind.
    """
    raise GitNestedError(msg)


def usage_error(msg: str) -> NoReturn:
    """Abort the command because the command line was malformed.

    The same exit as `error`; a separate name because the two read
    differently at the call site and only one of them is the user's typo.
    """
    error(msg)


def report(exc: GitNestedError) -> None:
    """Print a failure. The one place a GitNestedError becomes visible."""
    LOGGER.error(exc.message)
