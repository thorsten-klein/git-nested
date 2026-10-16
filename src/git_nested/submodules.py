"""Submodules in the content of a nested repository."""

from __future__ import annotations

import posixpath
from pathlib import Path

from . import output
from .git import GitRunner


def gitlinks(git: GitRunner, subdir: Path) -> list[tuple[str, str]]:
    """The submodules under subdir in the index, as (path, pinned commit)."""
    links = []
    for entry in git.check_output(['ls-files', '-s', '-z', '--', subdir]).split('\0'):
        if entry.startswith('160000 '):
            meta, path = entry.split('\t', 1)
            links.append((path, meta.split()[1]))
    return links


def entry(git: GitRunner, gitmodules: Path, path: str) -> tuple[str, str] | None:
    """The name and url `gitmodules` gives for the submodule at `path`, if any."""
    if not gitmodules.is_file():
        return None
    lines = git.check_output(
        ['config', '-f', gitmodules, '--get-regexp', r'^submodule\..*\.(path|url)$'], may_fail=True
    ).splitlines()
    fields: dict[str, dict[str, str]] = {}
    for line in lines:
        key, _, value = line.partition(' ')
        name, _, field = key.removeprefix('submodule.').rpartition('.')
        fields.setdefault(name, {})[field] = value
    return next(((name, f['url']) for name, f in fields.items() if f.get('path') == path and 'url' in f), None)


def url_of(git: GitRunner, gitmodules: Path, path: str, base: str) -> str | None:
    """The url `gitmodules` gives for `path`; a relative one is resolved against `base`."""
    found = entry(git, gitmodules, path)
    return resolve(found[1], base) if found else None


def resolve(url: str, base: str) -> str:
    """`url`, when relative ('./x', '../x'), resolved against `base`, as git does it."""
    if not url.startswith(('./', '../')):
        return url
    scheme, sep, rest = base.rpartition('://')
    return f'{scheme}{sep}{posixpath.normpath(posixpath.join(rest, url))}'


def warn_if_any(git: GitRunner, subdir: Path) -> None:
    """Say which submodules under subdir stay empty."""
    paths = [path.removeprefix(f'{subdir.as_posix()}/') for path, _ in gitlinks(git, subdir)]
    if paths:
        output.warn(
            f"{subdir.as_posix()}: these submodules stay empty: {', '.join(paths)}; "
            "use --recurse-submodules to nest them"
        )
