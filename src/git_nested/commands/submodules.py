"""Turn all submodules into nested repos.

The root repo stays a normal clone of the upstream superproject. Its
submodules are nested repos.

- init: nest every submodule, or the ones named, one commit each.
"""

from __future__ import annotations

import posixpath
from dataclasses import replace
from pathlib import Path
from typing import cast

from .. import checks, output, submodules
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, Flags
from . import init

_GITMODULES = '.gitmodules'
# --only and --ignore, kept in .gitmodules
_ONLY, _IGNORE = 'nested.only', 'nested.ignore'


def cmd_submodules(ctx: CommandContext) -> None:
    """Run `submodules init`."""
    if ctx.flags.only and ctx.flags.ignore:
        output.usage_error("--only and --ignore can't be used together")
    checks.check_worktree_clean(ctx.git, 'init')
    _nest_all(ctx.git, ctx.flags)


# ============================================================================
# init
# ============================================================================


def _nest_all(git: GitRunner, flags: Flags) -> None:
    """Nest each submodule at the commit it pins. With --recursive, their submodules too.

    With --only, only the submodules at or below its paths. With --ignore,
    all others. The rest stay submodules. Relative submodule urls need
    --resolve-relative.
    """
    links = _selected(git, flags)
    if not links:
        output.say("no submodules to nest")
        return
    if not flags.resolve_relative:
        _refuse_relative_urls(git, links)
    _keep_selection(git, flags)
    # .gitnested keeps the choice
    choice = cast('Flags', replace(flags, submodules='nest' if flags.recursive else 'keep', hint='--recursive'))
    for path in links:
        init.init_from_submodule(git, choice, Path(path), flags.resolve_relative)


def _selected(git: GitRunner, flags: Flags) -> list[str]:
    """The submodules that --only and --ignore leave in."""
    links = [path for path, _ in submodules.gitlinks(git, Path())]
    if flags.only:
        return _below_any(links, flags.only)
    skipped = set(_below_any(links, flags.ignore)) if flags.ignore else set()
    return [link for link in links if link not in skipped]


def _keep_selection(git: GitRunner, flags: Flags) -> None:
    """Write --only and --ignore into .gitmodules. It is part of the first commit."""
    if not (flags.only or flags.ignore):
        return
    only = [posixpath.normpath(Path(path).as_posix()) for path in flags.only or []]
    ignore = [posixpath.normpath(Path(path).as_posix()) for path in flags.ignore or []]
    _add_selection(git, Path(_GITMODULES), (only, ignore))
    git.run(['add', '--', _GITMODULES])


def _add_selection(git: GitRunner, file: Path, selection: tuple[list[str], list[str]]) -> None:
    """Add the --only and --ignore paths of `selection` to `file`."""
    for key, paths in zip((_ONLY, _IGNORE), selection, strict=True):
        for path in filter(None, paths):
            git.run(['config', '-f', file, '--add', key, path])


def _refuse_relative_urls(git: GitRunner, links: list[str]) -> None:
    """Fail if a submodule in `links` has a relative url.

    It is relative to the superproject's url. In a fork that is not origin.
    So git-nested does not guess.
    """
    relative = [
        path
        for path in links
        if (found := submodules.entry(git, Path(_GITMODULES), path)) and submodules.is_relative(found[1])
    ]
    if relative:
        raise GitNestedError(
            f"these submodules have a relative url: {', '.join(relative)}\n"
            "Use --resolve-relative <url> to say what they are relative to. "
            "That is the url of the project they come from."
        )


def _below_any(links: list[str], paths: list[str]) -> list[str]:
    """The submodules in `links` at or below one of `paths`. Each path must hit one."""
    wanted = [posixpath.normpath(Path(path).as_posix()) for path in paths]
    for path, given in zip(wanted, paths, strict=True):
        if not any(_below(link, path) for link in links):
            raise GitNestedError(f"{given}: no submodule there")
    return [link for link in links if any(_below(link, path) for path in wanted)]


def _below(link: str, path: str) -> bool:
    """Whether `link` is `path` or below it."""
    return path in ('.', link) or link.startswith(f'{path}/')
