"""Local changes of a nested repo, kept as patch files.

The `patches` field of .gitnested names the folder, relative to the subdir.
The patches are the local changes on top of the upstream commit.
Nested repos inside the subdir are not part of them. They can have their
own patches.
"""

from __future__ import annotations

import contextlib
import posixpath
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from . import history, output, worktree
from .errors import GitNestedError
from .git import GitRunner
from .models import NestedConfig

# `git commit` and `git am` need an identity; CI often has none.
_FALLBACK_IDENTITY = ['-c', 'user.name=git-nested', '-c', 'user.email=git-nested@localhost']

# A patch with a subject that starts with this stays local: a push leaves it out.
LOCAL_PREFIX = 'git-nested local:'

_SUBJECT = re.compile(r'^Subject:\s*(?:\[[^]]*\]\s*)*(.*)$', re.MULTILINE)

# The patch files in the patches folder.
PATCH_GLOB = '*.patch'

# How every patch is written, so that a patch written again is the same.
FORMAT_PATCH = ['format-patch', '--zero-commit', '--no-signature', '--no-numbered', '--no-cover-letter']

# .gitnested files are not part of the upstream content.
GITNESTED_EXCLUDE = ':(exclude,glob)**/.gitnested*'


def identity(git: GitRunner) -> list[str]:
    """A stand-in identity if git has none."""
    return [] if git.check_output(['config', 'user.email'], may_fail=True) else _FALLBACK_IDENTITY


def files(config: NestedConfig, subdir: Path) -> list[Path]:
    """The patch files, in order."""
    folder = config.patches_folder(subdir)
    return sorted(folder.glob(PATCH_GLOB)) if folder and folder.is_dir() else []


def local_paths(git: GitRunner, config: NestedConfig, subdir: Path) -> list[str]:
    """The paths in subdir the patches leave out.

    The patches folder, the inner nested repos and the `patches-ignore` paths.
    """
    inside = config.patches_inside(subdir)
    return [*([inside] if inside else []), *history.inner_repos(git, config, subdir), *ignored(config)]


def ignored(config: NestedConfig) -> list[str]:
    """The `patches-ignore` paths, if the patches are on."""
    return list(config.patches_ignore) if config.patches else []


def pathspec(local: list[str], ignored: list[str] | None = None) -> list[str]:
    """All paths but .gitnested files, the `local` and the `ignored` ones."""
    return ['.', GITNESTED_EXCLUDE, *(f':(exclude,literal){path}' for path in [*local, *(ignored or [])])]


def in_use(git: GitRunner, config: NestedConfig, subdir: Path) -> bool:
    """Whether the patches take over: they are on, and HEAD has at least one.

    Without any, the commands work as without patches. So a nested repo
    from before the patches keeps working.

    From HEAD: a reclone has removed the folder already.
    """
    folder = config.patches_folder(subdir)
    if folder is None:
        return False
    listed = git.check_output(['ls-tree', '-r', '--name-only', 'HEAD', '--', f'{folder.as_posix()}/'], may_fail=True)
    return any(path.endswith(PATCH_GLOB[1:]) for path in listed.splitlines())


def supported(config: NestedConfig) -> bool:
    """Whether the patches work with this setup yet."""
    return config.squash and not (config.path or config.filter or config.exclude)


def check(config: NestedConfig, subdir: Path, patches: list[Path]) -> None:
    """Refuse a patches setup that can't be, and `patches` with a setup they do not work with yet."""
    if not config.patches:
        return
    problem = _folder_problem(config, subdir) or _ignore_problem(config) or _local_problem(config, patches)
    if not problem and patches and (config.path or config.filter or config.exclude):
        problem = "patches do not work with filter, exclude or path yet"
    if problem:
        raise GitNestedError(f"{subdir.as_posix()}: {problem}")


def _folder_problem(config: NestedConfig, subdir: Path) -> str | None:
    """What is wrong with the patches folder, if anything."""
    if PurePosixPath(config.patches).is_absolute() or Path(config.patches).is_absolute():
        return "patches must be a path relative to the subdir"
    if config.patches_inside(subdir) == '.':
        return "patches can't be the subdir itself"
    return None


def _ignore_problem(config: NestedConfig) -> str | None:
    """What is wrong with the patches-ignore paths, if anything."""
    outside = next((path for path in config.patches_ignore if not _inside(path)), None)
    return None if outside is None else f"patches-ignore {outside}: not a path inside the subdir"


def _local_problem(config: NestedConfig, patches: list[Path]) -> str | None:
    """What is wrong with the patches-local file names, if anything: a name with no patch."""
    names = {patch.name for patch in patches}
    missing = next((name for name in config.patches_local if name not in names), None)
    return None if missing is None else f"patches-local {missing}: no such patch"


def _subject(git: GitRunner, patch: Path) -> str:
    """The title of `patch`, without `[PATCH]`."""
    with as_written(git, patch) as plain:
        found = _SUBJECT.search(plain.read_text(encoding='utf-8', errors='replace'))
    return found.group(1) if found else ''


def local(git: GitRunner, config: NestedConfig, patches: list[Path]) -> list[Path]:
    """The patches that stay local: listed in patches-local, or with a title that starts with LOCAL_PREFIX."""
    listed = set(config.patches_local)
    return [patch for patch in patches if patch.name in listed or _subject(git, patch).startswith(LOCAL_PREFIX)]


def _inside(path: str) -> bool:
    """Whether `path`, relative to the subdir, is inside it."""
    normal = posixpath.normpath(PurePosixPath(path).as_posix())
    return not (posixpath.isabs(normal) or Path(path).is_absolute() or normal == '.' or normal.startswith('..'))


@contextlib.contextmanager
def as_written(git: GitRunner, patch: Path) -> Iterator[Path]:
    """`patch` with the bytes git stores for it, as an absolute path.

    A checkout with core.autocrlf or an eol attribute turns the LF line
    ends of a patch file into CRLF. git's clean filter undoes that; then
    this is a temporary copy with LF again. Else the file is taken as it
    is, and a CR in it is content.
    """
    patch = patch.resolve()
    raw = git.check_output(['hash-object', '--no-filters', patch])
    if git.check_output(['hash-object', patch]) == raw:
        yield patch
        return
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / patch.name
        copy.write_bytes(patch.read_bytes().replace(b'\r\n', b'\n'))
        yield copy


def _am(git: GitRunner, path: Path, patches: list[Path], no_hooks: Path) -> str | None:
    """`git am -3` the patches in the worktree at `path`, without hooks or signing.

    One `git am` for all patches: after a conflict, `git am --continue`
    goes on with the rest.

    --keep-cr: a CR in a patch is content.

    A patch that upstream already has is dropped.

    Returns:
        None, or the name of the patch that does not apply.
    """
    no_hooks.mkdir(parents=True, exist_ok=True)
    output.verbose(f"applying {', '.join(patch.as_posix() for patch in patches)}")
    hooks = ['-c', f'core.hooksPath={no_hooks.as_posix()}']
    am = ['am', '-3', '--quiet', '--no-gpg-sign', '--keep-cr']
    with contextlib.ExitStack() as stack:
        # git am copies the patches before it starts, so the copies can go after it.
        written = [stack.enter_context(as_written(git, patch)) for patch in patches]
        if git.run([*identity(git), *hooks, *am, *written], cwd=path, may_fail=True).returncode == 0:
            return None
    return patches[_stopped_at(git, path) - 1].name


def _stopped_at(git: GitRunner, path: Path) -> int:
    """The number of the patch the open `git am` in `path` stopped at, from 1.

    No open `git am`: the first patch failed the format detection.
    """
    state = _am_next(git, path)
    return int(state.read_text()) if state.is_file() else 1


def am_open(git: GitRunner, path: Path) -> bool:
    """Whether a `git am` is open in the worktree at `path`.

    After a failed `git am`: if not, the patch is not a patch at all.
    """
    return _am_next(git, path).is_file()


def _am_next(git: GitRunner, path: Path) -> Path:
    """The file where an open `git am` in `path` keeps the number of its next patch."""
    return path / git.check_output(['rev-parse', '--git-path', 'rebase-apply/next'], cwd=path)


def apply_in_worktree(git: GitRunner, path: Path, patches: list[Path], git_tmp: Path) -> str | None:
    """Apply the patches in the worktree at `path`, one commit each.

    On a conflict the `git am` stays open in the worktree.

    Returns:
        None, or the name of the patch that does not apply.
    """
    return _am(git, path, patches, git_tmp / 'no-hooks')


def apply_on(git: GitRunner, base: str, patches: list[Path], path: Path, subdir: Path) -> str:
    """The commit of `base` with the patches applied.

    It is built in a temporary worktree at `path`. Nothing is left behind,
    also when a patch does not apply.
    """
    worktree.remove_worktree(git, path)
    git.run(['worktree', 'add', '--quiet', '--detach', '--no-checkout', path, base])
    try:
        git.run(['reset', '-q', '--hard'], cwd=path)
        failed = _am(git, path, patches, path.parent / 'no-hooks')
        if failed:
            raise GitNestedError(
                f"{subdir.as_posix()}: the patch {failed} does not apply on upstream {base[:9]}; nothing was changed"
            )
        return git.check_output(['rev-parse', 'HEAD'], cwd=path)
    finally:
        worktree.remove_worktree(git, path)


def restore_inner_repos(git: GitRunner, subdir: Path, inner: list[str]) -> None:
    """Put the `inner` nested repos back, as HEAD has them."""
    for path in inner:
        git.run(['checkout', 'HEAD', '--', f'{subdir.as_posix()}/{path}'])


def restore_ignored(git: GitRunner, config: NestedConfig, subdir: Path) -> None:
    """Put the `patches-ignore` paths back as HEAD has them: upstream's changes there do not come in."""
    for path in ignored(config):
        full = f'{subdir.as_posix()}/{path}'
        git.run(['rm', '-r', '-q', '-f', '--ignore-unmatch', '--', full])
        if git.check_output(['ls-tree', '--name-only', 'HEAD', '--', full]):
            git.run(['checkout', 'HEAD', '--', full])


def write(git: GitRunner, config: NestedConfig, subdir: Path, base: str, tip: str, local: list[str]) -> None:
    """Write the changes from `base` to `tip` as the patches, and stage them.

    One patch per commit. If the commits are not a plain line on top of
    `base`, it writes one patch with all changes instead. The `local` paths
    are left out.
    """
    folder = config.patches_folder(subdir)
    if folder is None:
        return
    for old in folder.glob(PATCH_GLOB):
        old.unlink()

    tip = _linear(git, base, tip, subdir)
    limit = pathspec(local)
    if git.check_output(['diff', '--name-only', base, tip, '--', *limit]):
        output.verbose(f"writing the patches to {folder.as_posix()}")
        folder.mkdir(parents=True, exist_ok=True)
        git.run([
            *FORMAT_PATCH,
            '--quiet',
            '-o',
            folder.resolve(),
            f'{base}..{tip}',
            '--',
            *limit,
        ])
    if folder.exists():
        git.run(['add', '-A', '-f', '--', folder])


def _linear(git: GitRunner, base: str, tip: str, subdir: Path) -> str:
    """`tip`, or one commit on `base` with its tree if the history between is not a line."""
    on_base = git.run(['merge-base', '--is-ancestor', base, tip], may_fail=True).returncode == 0
    if on_base and not git.check_output(['rev-list', '--merges', f'{base}..{tip}']):
        return tip
    tree = git.check_output(['rev-parse', f'{tip}^{{tree}}'])
    message = f"Local changes to {subdir.as_posix()}"
    return git.check_output([*identity(git), 'commit-tree', '-p', base, '-m', message, tree])
