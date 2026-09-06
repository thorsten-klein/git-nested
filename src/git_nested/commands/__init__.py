"""One module per git-nested command.

Each module holds both halves of its command: the `do_*`/`get_*` mechanics
that talk to git, and the `cmd_*` handler that turns a CommandContext into
user-visible output. REGISTRY is what `cli.app` dispatches through, so a
new command is a new module plus one line here.

These modules may import the core modules and `cli.setup` (the shared
subdir-resolving preamble every handler needs, which imports nothing from
the CLI itself), but never `cli.app` -- that is what keeps the dependency
between the two packages one-way.
"""

from __future__ import annotations

from collections.abc import Callable

from ..models import CommandContext
from . import branch, clean, clone, commit, completion, diff, fetch, init, pull, push, status, version

REGISTRY: dict[str, Callable[[CommandContext], None]] = {
    'branch': branch.cmd_branch,
    'clean': clean.cmd_clean,
    'clone': clone.cmd_clone,
    'commit': commit.cmd_commit,
    'completion': completion.cmd_completion,
    'diff': diff.cmd_diff,
    'fetch': fetch.cmd_fetch,
    'init': init.cmd_init,
    'pull': pull.cmd_pull,
    'push': push.cmd_push,
    'status': status.cmd_status,
    'version': version.cmd_version,
}
