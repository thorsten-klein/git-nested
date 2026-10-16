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
    prefix = '' if command in ('completion', 'version') else _prefix(git)
    if not prefix:
        return nullcontext()
    toplevel = Path(git.check_output(['rev-parse', '--show-toplevel']))
    _absolute_paths(ctx)
    _rebase_remotes(ctx, prefix)
    ctx.subdir = _subdir_from(toplevel, prefix, ctx.subdir, command, ctx.flags.all)
    return chdir(toplevel)


def _prefix(git: GitRunner) -> str:
    """The current directory relative to the top level, '' at the top or outside a working tree."""
    return git.check_output(['rev-parse', '--show-prefix'], may_fail=True)


def _absolute(path: str | None) -> str | None:
    """`path` made absolute against the current directory, '..' resolved; None stays None.

    Not Path.resolve(): that follows symlinks too, and the path would no
    longer be the one the user typed (on macOS /var turns into /private/var).
    """
    return os.path.abspath(path) if path else None  # noqa: PTH100


def _absolute_paths(ctx: CommandContext) -> None:
    """Make the path options absolute, so moving to the top level does not change what they name."""
    ctx.flags.dir = _absolute(ctx.flags.dir)
    ctx.flags.message_file = _absolute(ctx.flags.message_file)


def _rebase_remotes(ctx: CommandContext, prefix: str) -> None:
    """Rebase every remote given as a relative path onto the top level.

    Relative rather than absolute: a remote ends up in .gitnested, and a
    relative one keeps working in every clone of the parent repository.
    """
    ctx.upstream = _remote_from(prefix, ctx.upstream)
    ctx.flags.remote = _remote_from(prefix, ctx.flags.remote)
    if ctx.config_key == 'remote':
        ctx.config_value = _remote_from(prefix, ctx.config_value)


def _is_local_path(remote: str) -> bool:
    """Whether git reads `remote` as a path, by git's own rule (see 'GIT URLS' in git-fetch(1)).

    A URL has '://'; scp-like syntax ('host:path') has a colon before any slash.
    """
    colon, slash = remote.find(':'), remote.find('/')
    return '://' not in remote and (colon == -1 or -1 < slash < colon)


def _remote_from(prefix: str, remote: str | None) -> str | None:
    """`remote`, typed below the top level at `prefix`, as seen from the top level."""
    if not remote or Path(remote).anchor or not _is_local_path(remote):
        return remote
    joined = posixpath.normpath(PurePosixPath(prefix, Path(remote).as_posix()))
    # './' keeps a path that has lost its leading '..' from reading as a remote's name
    return joined if joined.startswith('.') else f'./{joined}'


def _subdir_from(toplevel: Path, prefix: str, subdir: str | Path | None, command: str, all_flag: bool) -> str | None:
    """`subdir` as seen from the top level; the enclosing nested repository when none was given."""
    if subdir is None:
        return None if command in _NO_IMPLIED_SUBDIR or all_flag else _enclosing_nested(toplevel, prefix)
    return _joined(prefix, Path(subdir))


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
