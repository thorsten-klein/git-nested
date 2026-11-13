"""`git nested patches`: write, check and drop the patches of a nested repository.

`create` brings the patches folder up to date: it writes the local
changes that are not in a patch yet as a new patch, and writes all patches
again in the one form git-nested uses. `verify` only checks that nothing
would change. `drop` removes patches, and their changes from the subdir.
`cherry-pick` adds an upstream commit or a patch file as a patch.
"""

from __future__ import annotations

import contextlib
import dataclasses
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .. import checks, content, output, patchbuild, patches, patchpick
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


def _count(files: list[Path]) -> str:
    """'1 patch', '2 patches'."""
    return f"{len(files)} patch{'' if len(files) == 1 else 'es'}"


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


def check_content(git: GitRunner, config: NestedConfig, subdir: Path, subref: str, tmp: Path) -> None:
    """Refuse if subdir has changes that are not in its patches."""
    with _rebuilt(git, config, subdir, subref, tmp, add_missing=False) as rebuilt:
        if rebuilt.missing:
            raise GitNestedError(_missing_message(subdir, rebuilt.missing))


def _missing_message(subdir: Path, missing: str) -> str:
    """The error for changes that are not in a patch."""
    name = subdir.as_posix()
    return (
        f"{name}: has changes that are not in its patches\n{missing}\n"
        f"'git nested patches create {name}' writes the missing one"
    )


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


def _verify(ctx: CommandContext, config: NestedConfig, subdir: Path, subref: str) -> None:
    """Check that `create` would change nothing."""
    git, name = ctx.git, subdir.as_posix()
    old = patches.files(config, subdir)
    with _rebuilt(git, config, subdir, subref, ctx.tmp, add_missing=False) as rebuilt:
        if rebuilt.missing:
            raise GitNestedError(_missing_message(subdir, rebuilt.missing))
        changed = _changed(git, old, rebuilt.files)
    if changed:
        raise GitNestedError(
            f"{name}: the patches are not as git-nested writes them: {', '.join(changed)}\n"
            f"'git nested patches create {name}' writes them again"
        )
    output.say(f"{name}: the patches are up to date: upstream {config.commit[:9]} with {_count(old)}")


def _check_setup(config: NestedConfig, subdir: Path) -> None:
    """Refuse a setup the patches are off for, or do not work with yet."""
    patches.check(config, subdir, patches.files(config, subdir))
    name = subdir.as_posix()
    if config.patches_folder(subdir) is None:
        raise GitNestedError(f"{name}: the patches are off; 'git nested config {name} patches <path>' turns them on")
    if not patches.supported(config):
        raise GitNestedError(f"{name}: patches do not work with filter, exclude, path or squash: false yet")


def _find(files: list[Path], given: str, subdir: Path) -> Path:
    """The patch in `files` that `given` names: by its path, or by its file name."""
    found = next((file for file in files if given == file.name or Path(given).resolve() == file.resolve()), None)
    if found is None:
        raise GitNestedError(f"{subdir.as_posix()}: {given} is not one of its patches")
    return found


def _drop(ctx: CommandContext, config: NestedConfig, subdir: Path, subref: str, gitnested: Path) -> None:
    """Remove the named patches, and their changes from subdir, in one commit."""
    git, name = ctx.git, subdir.as_posix()
    checks.check_worktree_clean(git, 'drop a patch')
    files = patches.files(config, subdir)
    dropped = [_find(files, given, subdir) for given in ctx.patch_names or []]
    check_content(git, config, subdir, subref, ctx.tmp)
    kept = [file for file in files if file not in dropped]
    result = patches.apply_on(git, config.commit, kept, ctx.tmp / 'patches' / subref, subdir) if kept else config.commit
    names = ', '.join(file.name for file in dropped)
    flags = dataclasses.replace(ctx.flags, message=f"{name}: drop the patch {names}")
    content.commit_nested_branch(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        nested_commit_ref=result,
        upstream_head_commit=config.commit,
        head_commit=ctx.head,
        subdir_worktree=None,
        command='patches',
    )
    output.say(f"{name}: dropped {names}")


def _cherry_pick(ctx: CommandContext, config: NestedConfig, subdir: Path, subref: str, gitnested: Path) -> None:
    """Add commits or patch files as patches, and their changes to subdir, in one commit."""
    git, name = ctx.git, subdir.as_posix()
    checks.check_worktree_clean(git, 'cherry-pick a patch')
    check_content(git, config, subdir, subref, ctx.tmp)
    with tempfile.TemporaryDirectory() as scratch:
        picked = patchpick.as_patches(git, ctx.flags.remote or config.remote, ctx.patch_names or [], Path(scratch))
        files = [*patches.files(config, subdir), *picked]
        result = patches.apply_on(git, config.commit, files, ctx.tmp / 'patches' / subref, subdir)
    added = patchpick.names(git, result, len(picked))
    flags = dataclasses.replace(ctx.flags, message=f"{name}: cherry-pick {', '.join(added)}")
    content.commit_nested_branch(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        nested_commit_ref=result,
        upstream_head_commit=config.commit,
        head_commit=ctx.head,
        subdir_worktree=None,
        command='patches',
    )
    if ctx.flags.local:
        # After the commit: replacing the subdir needs an unchanged .gitnested.
        # The new patches are the last ones, by file name.
        new = [file.name for file in patches.files(config, subdir)[-len(picked) :]]
        patchpick.add_local(git, gitnested, new)
    output.say(f"{name}: cherry-picked {', '.join(added)}")


_ACTIONS = {'create': _create, 'verify': _verify}
_CHANGING = {'drop': _drop, 'cherry-pick': _cherry_pick}


def cmd_patches(ctx: CommandContext) -> None:
    """Write, check, drop or cherry-pick the patches of a nested repository."""
    subdir, gitnested, subref, config = setup.setup_command(ctx.git, 'patches', ctx.flags, ctx.subdir, ctx.upstream)
    action = ctx.patches_action or 'verify'
    if (action in _CHANGING) != bool(ctx.patch_names):
        output.usage_error("drop and cherry-pick need what to drop or pick; create and verify take nothing")
    if ctx.flags.local and action != 'cherry-pick':
        output.usage_error("--local only works with cherry-pick")
    _check_setup(config, subdir)
    if action in _CHANGING:
        _CHANGING[action](ctx, config, subdir, subref, gitnested)
        return
    _ACTIONS[action](ctx, config, subdir, subref)
