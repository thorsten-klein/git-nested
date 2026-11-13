"""Patches taken from elsewhere: an upstream commit, or a patch file.

`git nested patches cherry-pick` adds them to the patches of a nested repo.
"""

from __future__ import annotations

from pathlib import Path

from . import configio, patches
from .git import GitRunner


def as_patches(git: GitRunner, remote: str, given: list[str], out: Path) -> list[Path]:
    """The patches to add, in order: a file is taken as it is, a commit is written as a patch into `out`."""
    return [_as_patch(git, remote, item, out, number) for number, item in enumerate(given, start=1)]


def _as_patch(git: GitRunner, remote: str, item: str, out: Path, number: int) -> Path:
    """`item` as a patch file."""
    if Path(item).is_file():
        return Path(item).resolve()
    commit = _commit(git, remote, item)
    return Path(
        git.check_output([*patches.FORMAT_PATCH, '-1', f'--start-number={number}', '-o', out.resolve(), commit])
    )


def _commit(git: GitRunner, remote: str, item: str) -> str:
    """The commit `item` names: here already, or fetched from `remote`."""
    found = git.run(['rev-parse', '--verify', '--quiet', f'{item}^{{commit}}'], may_fail=True)
    if found.returncode == 0:
        return found.stdout.strip()
    git.network(['fetch', '--no-tags', '--quiet', remote, item], f"fetching {item} from {remote}")
    return git.check_output(['rev-parse', 'FETCH_HEAD^{commit}'])


def names(git: GitRunner, tip: str, count: int) -> list[str]:
    """The patch names, without number, of the last `count` commits up to `tip`, oldest first.

    `%f` is the subject as `git format-patch` puts it into a file name.
    """
    return git.check_output(['log', '--reverse', '--format=%f', '-n', str(count), tip]).splitlines()


def add_local(git: GitRunner, gitnested: Path, new: list[str]) -> None:
    """Add `new` to `patches-local` in the .gitnested file, in the last commit."""
    data = configio.read(gitnested)
    nested = data.setdefault('nested', {})
    listed = nested.get('patches-local') or []
    listed = [listed] if isinstance(listed, str) else list(listed)
    nested['patches-local'] = [*listed, *(name for name in new if name not in listed)]
    configio.write(gitnested, data)
    git.run(['add', '-f', '--', gitnested])
    git.run(['commit', '--amend', '--no-edit', '--quiet', '--no-verify'])
