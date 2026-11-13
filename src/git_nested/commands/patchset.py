"""`git nested patches`: write the patches of a nested repository.

`create` brings the patches folder up to date: it writes the local
changes that are not in a patch yet as a new patch, and writes all patches
again in the one form git-nested uses.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .. import output, patchbuild, patches
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, NestedConfig
from . import verify


@dataclass
class _Rebuilt:
    """The patches written again from upstream, and what they miss."""

    files: list[Path]
    missing: str


@contextlib.contextmanager
def _rebuilt(
    git: GitRunner, config: NestedConfig, subdir: Path, subref: str, tmp: Path, add_missing: bool
) -> Iterator[_Rebuilt]:
    """The patches applied on upstream and written again, in a scratch folder.

    With `add_missing`, what HEAD has on top becomes one more patch.
    """
    local_tree = git.check_output(['rev-parse', f'HEAD:{subdir.as_posix()}'])
    base = verify.upstream_base(git, config, subref, subdir)
    pathspec = patches.pathspec(patches.local_paths(git, config, subdir))
    path = tmp / 'patches' / subref
    with tempfile.TemporaryDirectory() as scratch, patchbuild.worktree_at(git, path, base):
        patchbuild.apply(git, path, patches.files(config, subdir))
        missing = patchbuild.diff(git, path, 'HEAD', local_tree, pathspec, '--stat').rstrip()
        if missing and add_missing:
            patchbuild.commit_missing(git, path, local_tree, pathspec)
        yield _Rebuilt(patchbuild.write_all(git, path, base, Path(scratch)), missing)


def _changed(git: GitRunner, old: list[Path], new: list[Path]) -> list[str]:
    """The names of the patches that differ between `old` and `new`."""
    before = {file.name: patchbuild.stored(git, file) for file in old}
    after = {file.name: file.read_bytes() for file in new}
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


def _create(ctx: CommandContext, config: NestedConfig, subdir: Path, subref: str) -> None:
    """Write the missing patch, and all patches again."""
    git, name = ctx.git, subdir.as_posix()
    # _check_setup refused a setup with the patches off
    folder = subdir / config.patches
    old = patches.files(config, subdir)
    with _rebuilt(git, config, subdir, subref, ctx.tmp, add_missing=True) as rebuilt:
        changed = _changed(git, old, rebuilt.files)
        if changed:
            _replace(folder, old, rebuilt.files)
    if not changed:
        output.say(f"{name}: the patches are up to date")
    elif rebuilt.missing:
        output.say(
            f"{name}: wrote the missing patch {patchbuild.shown(folder / rebuilt.files[-1].name)}\n"
            f"replace '{patchbuild.TODO_TITLE}' and '{patchbuild.TODO_DESCRIPTION}' in it, "
            f"run 'git nested patches create {name}' again to name it, and commit the folder"
        )
    else:
        output.say(f"{name}: wrote the patches again: {', '.join(changed)}")


def _replace(folder: Path, old: list[Path], new: list[Path]) -> None:
    """Put the `new` patches into `folder`, in place of the `old` ones."""
    for file in old:
        file.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    for file in new:
        shutil.copyfile(file, folder / file.name)


def _check_setup(config: NestedConfig, subdir: Path) -> None:
    """Refuse a setup the patches are off for, or do not work with yet."""
    patches.check(config, subdir, patches.files(config, subdir))
    name = subdir.as_posix()
    if config.patches_folder(subdir) is None:
        raise GitNestedError(f"{name}: the patches are off; 'git nested config {name} patches <path>' turns them on")
    if not patches.supported(config):
        raise GitNestedError(f"{name}: patches do not work with filter, exclude, path or squash: false yet")


_ACTIONS = {'create': _create}


def cmd_patches(ctx: CommandContext) -> None:
    """Write the patches of a nested repository."""
    subdir, _, subref, config = setup.setup_command(ctx.git, 'patches', ctx.flags, ctx.subdir, ctx.upstream)
    _check_setup(config, subdir)
    _ACTIONS[ctx.patches_action or 'create'](ctx, config, subdir, subref)
