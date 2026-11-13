"""Check a nested repository against its upstream commit plus patches or diffs."""

from __future__ import annotations

from pathlib import Path

from .. import filters, output, patchbuild, patches
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, NestedConfig
from . import fetch


def _counted(count: int, mode: str | None) -> str:
    """'1 patch', '2 patches', '1 diff', '2 diffs'."""
    if mode == 'diff':
        return f"{count} diff{'' if count == 1 else 's'}"
    return f"{count} patch{'' if count == 1 else 'es'}"


def upstream_base(git: GitRunner, config: NestedConfig, subref: str, subdir: Path) -> str:
    """The upstream commit from .gitnested, fetched if missing.

    With `path`, `filter` or `exclude`, only the nested part is kept.
    """
    commit = config.commit
    if not commit:
        output.error(f"{subdir.as_posix()}: no upstream commit recorded in .gitnested")
    if not git.rev_exists(f'{commit}^{{commit}}'):
        _fetch_commit(git, config, subref, subdir)
    if config.path:
        tree = git.check_output(['rev-parse', f'{commit}:{config.path}'])
        return git.check_output(['commit-tree', '-p', commit, '-m', f'{config.path} of {commit}', tree])
    if config.filter or config.exclude:
        return filters.build_filtered_commit(git, Path.cwd(), config.filter or [], config.exclude or [], commit)
    return commit


def _fetch_commit(git: GitRunner, config: NestedConfig, subref: str, subdir: Path) -> None:
    """Fetch the upstream commit from .gitnested."""
    commit = config.commit
    if config.remote == 'none':
        output.error(f"{subdir.as_posix()}: upstream commit {commit} is not here, and there is no remote")
    fetch.do_fetch(git, config, subref)
    if not git.rev_exists(f'{commit}^{{commit}}'):
        output.error(f"{subdir.as_posix()}: upstream commit {commit} is not on {config.remote} ({config.branch})")


def _apply(git: GitRunner, path: Path, files: list[Path], as_patches: bool) -> None:
    """Apply `files` in order in the worktree at `path`, then commit.

    Patches go in with `git am`, so a plain diff is refused as a patch.
    Diffs go in with `git apply`.
    """
    for file in files:
        output.say(f"applying {patchbuild.shown(file)}")
    if as_patches:
        patchbuild.apply(git, path, files)
    else:
        for file in files:
            _git_apply(git, path, file)
    patchbuild.commit_in(git, path, "the upstream commit with the patches applied")


def _git_apply(git: GitRunner, path: Path, file: Path) -> None:
    """`git apply` the diff `file` in the worktree at `path`."""
    with patches.as_written(git, file) as diff:
        result = git.run(['apply', '--index', '--whitespace=nowarn', diff], may_fail=True, cwd=path)
    if result.returncode != 0:
        raise GitNestedError(f"{patchbuild.shown(file)}: does not apply\n{(result.stderr or '').strip()}")


def _write_diff(git: GitRunner, path: Path, base: str, local_tree: str, pathspec: list[str], file: Path) -> Path:
    """Write the whole diff from upstream to `file`."""
    file.parent.mkdir(parents=True, exist_ok=True)
    # git writes the file: text mode would drop or add CRs.
    patchbuild.diff(git, path, base, local_tree, pathspec, '--binary', f'--output={file.resolve()}')
    return file


def _report_difference(
    ctx: CommandContext, path: Path, base: str, local_tree: str, pathspec: list[str], subdir: Path
) -> str:
    """The error message when `subdir` differs; writes the missing file if it can."""
    git, files, out = ctx.git, [Path(file) for file in ctx.patches or []], ctx.flags.output_dir
    stat = patchbuild.diff(git, path, 'HEAD', local_tree, pathspec, '--stat').rstrip()
    message = (
        f"{subdir.as_posix()}: differs from its upstream commit with {_counted(len(files), ctx.verify_mode)}\n{stat}"
    )

    if ctx.verify_mode == 'diff':
        return _diff_hint(git, path, base, local_tree, pathspec, message, out)

    directory = _patch_directory(out, files)
    if directory is None:
        return f"{message}\nname the patches, or use --output to have the missing one written"
    patchbuild.commit_missing(git, path, local_tree, pathspec)
    patch = patchbuild.write_last(git, path, directory)
    return (
        f"{message}\nwrote the missing patch {patchbuild.shown(patch)}\n"
        f"replace '{patchbuild.TODO_TITLE}' and '{patchbuild.TODO_DESCRIPTION}' in it, rename it to match, "
        "and commit it"
    )


def _patch_directory(out: str | None, files: list[Path]) -> Path | None:
    """Where the missing patch goes: --output, else next to the last patch."""
    if out:
        return Path(out)
    return files[-1].parent if files else None


def _diff_hint(
    git: GitRunner, path: Path, base: str, local_tree: str, pathspec: list[str], message: str, out: str | None
) -> str:
    """`message` for 'diff' mode, after writing the whole diff to `out` if given."""
    if not out:
        return f"{message}\nuse --output to have the whole diff written"
    written = _write_diff(git, path, base, local_tree, pathspec, Path(out))
    return f"{message}\nwrote the whole diff to {patchbuild.shown(written)}"


def _files(ctx: CommandContext) -> list[Path]:
    """The files to apply, which must exist."""
    files = [Path(file) for file in ctx.patches or []]
    missing = next((file for file in files if not file.is_file()), None)
    if missing:
        output.usage_error(f"{missing.as_posix()}: no such file")
    return files


def cmd_verify(ctx: CommandContext) -> None:
    """Check that a nested repo is its upstream commit plus the given files."""
    git = ctx.git
    subdir, _, subref, config = setup.setup_command(git, 'verify', ctx.flags, ctx.subdir, ctx.upstream)
    files = _files(ctx)

    local_tree = git.check_output(['rev-parse', f'HEAD:{subdir.as_posix()}'])
    base = upstream_base(git, config, subref, subdir)
    pathspec = patches.pathspec(patches.local_paths(git, config, subdir), filters.ignored_paths(ctx.flags, subdir))

    path = ctx.tmp / 'verify' / subref
    with patchbuild.worktree_at(git, path, base, keep=ctx.flags.keep):
        _apply(git, path, files, as_patches=ctx.verify_mode != 'diff')
        if patchbuild.differs(git, path, local_tree, pathspec):
            raise GitNestedError(_report_difference(ctx, path, base, local_tree, pathspec, subdir))

    output.say(
        f"{subdir.as_posix()}: matches upstream {config.commit[:9]} with {_counted(len(files), ctx.verify_mode)}"
    )
