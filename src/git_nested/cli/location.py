"""Running from anywhere in the repository, the way git does.

git-nested works from the top level of the repository: every path it
handles internally is relative to it. A command started further down moves
there for its duration, and the path arguments it was given are first
rewritten so that they still mean what they meant where it was started --
a <subdir> relative to the starting directory, like git's own pathspecs,
and any other path made absolute.
"""

from __future__ import annotations

import os
import posixpath
from contextlib import nullcontext
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .. import output
from .._compat import chdir
from ..constants import GITNESTED_FILENAME

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from ..git import GitRunner
    from ..models import CommandContext

# Commands whose missing <subdir> is not filled in from the current directory:
# status reports on all of them, clone guesses one from the upstream, and init
# is what makes a directory nested in the first place.
_NO_IMPLIED_SUBDIR = ('clone', 'completion', 'init', 'status', 'version')


def at_top_level(git: GitRunner, command: str, ctx: CommandContext) -> AbstractContextManager[object]:
    """A context that runs the command at the top level, `ctx` rewritten to match.

    Outside a working tree there is nowhere to move to; the repository
    checks that follow say so in their own words.
    """
    # The current directory relative to the top level; '' at the top or outside a working tree
    prefix = (
        '' if command in ('completion', 'version') else git.check_output(['rev-parse', '--show-prefix'], may_fail=True)
    )
    if not prefix:
        return nullcontext()
    toplevel = Path(git.check_output(['rev-parse', '--show-toplevel']))

    # Path options are made absolute, so moving to the top level does not change what they name.
    ctx.flags.dir = _absolute(ctx.flags.dir)
    ctx.flags.message_file = _absolute(ctx.flags.message_file)
    # Remotes given as relative paths are rebased onto the top level instead.
    # Relative rather than absolute: a remote ends up in .gitnested, and a
    # relative one keeps working in every clone of the parent repository.
    ctx.upstream = _remote_from(prefix, ctx.upstream)
    ctx.flags.remote = _remote_from(prefix, ctx.flags.remote)
    if ctx.config_key == 'remote':
        ctx.config_value = _remote_from(prefix, ctx.config_value)

    if ctx.subdir is not None:
        ctx.subdir = _joined(prefix, Path(ctx.subdir))
    elif command not in _NO_IMPLIED_SUBDIR and not ctx.flags.all:
        ctx.subdir = _enclosing_nested(toplevel, prefix)
    return chdir(toplevel)


def _absolute(path: str | None) -> str | None:
    """`path` made absolute against the current directory, '..' resolved; None stays None.

    Not Path.resolve(): that follows symlinks too, and the path would no
    longer be the one the user typed (on macOS /var turns into /private/var).
    """
    return os.path.abspath(path) if path else None  # noqa: PTH100


def _remote_from(prefix: str, remote: str | None) -> str | None:
    """`remote`, typed below the top level at `prefix`, as seen from the top level.

    Only a remote git reads as a path is touched, by git's own rule (see
    'GIT URLS' in git-fetch(1)): a URL has '://', and scp-like syntax
    ('host:path') has a colon before any slash.
    """
    if not remote or Path(remote).anchor or '://' in remote:
        return remote
    colon, slash = remote.find(':'), remote.find('/')
    if colon != -1 and not -1 < slash < colon:
        return remote
    joined = posixpath.normpath(PurePosixPath(prefix, Path(remote).as_posix()))
    # './' keeps a path that has lost its leading '..' from reading as a remote's name
    return joined if joined.startswith('.') else f'./{joined}'


def _joined(prefix: str, subdir: Path) -> str:
    """`subdir`, typed below the top level at `prefix`, as a path from the top level."""
    if subdir.anchor:
        return str(subdir)  # absolute: setup_command rejects it with the usual message
    joined = posixpath.normpath(PurePosixPath(prefix, subdir.as_posix()))
    if joined == '..' or joined.startswith('../'):
        output.usage_error(f"{subdir.as_posix()}: outside the repository")
    return joined


def _enclosing_nested(toplevel: Path, prefix: str) -> str | None:
    """The nearest directory at or above `prefix` that is a nested repository, if any."""
    for candidate in (PurePosixPath(prefix), *PurePosixPath(prefix).parents):
        if candidate != PurePosixPath('.') and (toplevel / candidate / GITNESTED_FILENAME).is_file():
            return candidate.as_posix()
    return None
