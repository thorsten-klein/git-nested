"""Everything git-nested says to the user.

The four functions here are the only places the package writes to a
stream; `Flags` decides whether a given message is emitted at all.
"""

from __future__ import annotations

import sys
from typing import NoReturn

from .errors import GitNestedError
from .models import Flags


def verbose(msg: str, flags: Flags):
    """Print verbose messages."""
    if flags.verbose:
        print(f"* {msg}")


def say(msg: str, flags: Flags):
    """Print message unless quiet."""
    if not flags.quiet:
        print(msg)


def error(msg: str) -> NoReturn:
    """Report a failure and abort the command.

    The message is written here rather than by GitNestedError so that a
    caller that wants to catch and recover does not get a stray line on
    stderr as a side effect of the exception existing.
    """
    print(f"git-nested: {msg}", file=sys.stderr)
    raise GitNestedError(msg, print_to_stderr=False)


def usage_error(msg: str) -> NoReturn:
    """Report a malformed command line and exit."""
    print(f"git-nested: {msg}", file=sys.stderr)
    sys.exit(1)
