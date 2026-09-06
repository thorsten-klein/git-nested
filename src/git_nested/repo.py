"""The GitNestedRepo facade.

Every attribute that is not defined on the class resolves to the
module-level function of the same name in one of `_MODULES`. New code
imports those functions directly; this exists so that `GitNestedRepo()`
keeps working for anything that already depends on it.
"""

from __future__ import annotations

from collections.abc import Callable

from . import checks, content, discovery, filters, gitfile, history, output, refs, worktree, yamlio
from .commands import branch, clean, clone, commit, diff, fetch, init, pull, push, status, version

# Scanned in order by GitNestedRepo.__getattr__. A name defined by two of
# these modules would resolve to whichever comes first, so a unit test
# asserts the exported names are disjoint.
_MODULES = (
    checks,
    content,
    discovery,
    filters,
    gitfile,
    history,
    output,
    refs,
    worktree,
    yamlio,
    branch,
    clean,
    clone,
    commit,
    diff,
    fetch,
    init,
    pull,
    push,
    status,
    version,
)


class GitNestedRepo:
    """Handles repository operations and business logic."""

    def __init__(self) -> None:
        """No state to initialize; all methods operate on their arguments."""

    def __getattr__(self, name: str) -> Callable[..., object]:
        """Resolve `name` to the module-level function of the same name."""
        for module in _MODULES:
            func = getattr(module, name, None)
            if func is not None:
                return func
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")
