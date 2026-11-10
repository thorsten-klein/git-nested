"""Check a nested repository against its upstream commit plus patches or diffs."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterator
from pathlib import Path

from .. import filters, output, patches, worktree
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, NestedConfig
from . import fetch

# Placeholders in a written patch, for the user to fill in.
TODO_TITLE = "TODO: title"
TODO_DESCRIPTION = "TODO: description"

_LEADING_NUMBER = re.compile(r'^(\d+)-')


def _commit(git: GitRunner, path: Path, *message: str) -> None:
    """Commit in the worktree at `path`, without hooks or signing."""
    paragraphs = [arg for paragraph in message for arg in ('-m', paragraph)]
    git.run(
        [*patches.identity(git), 'commit', '--quiet', '--allow-empty', '--no-verify', '--no-gpg-sign', *paragraphs],
        cwd=path,
    )


def _counted(count: int, mode: str | None) -> str:
    """'1 patch', '2 patches', '1 diff', '2 diffs'."""
    if mode == 'diff':
        return f"{count} diff{'' if count == 1 else 's'}"
    return f"{count} patch{'' if count == 1 else 'es'}"


def _upstream_base(git: GitRunner, config: NestedConfig, subref: str, subdir: Path) -> str:
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


def _apply(git: GitRunner, path: Path, files: list[Path], quiet: bool = False) -> None:
    """Apply `files` in order in the worktree at `path`, then commit.

    `git apply`, not `git am`: it takes plain diffs too.
    """
    for file in files:
        (output.verbose if quiet else output.say)(f"applying {_shown(file)}")
        result = git.run(['apply', '--index', '--whitespace=nowarn', file.resolve()], may_fail=True, cwd=path)
        if result.returncode != 0:
            raise GitNestedError(f"{_shown(file)}: does not apply\n{(result.stderr or '').strip()}")
    _commit(git, path, "the upstream commit with the patches applied")


def _next_number(directory: Path) -> int:
    """The next free patch number in `directory`."""
    numbers = [
        int(match.group(1)) for patch in directory.glob('*.patch') if (match := _LEADING_NUMBER.match(patch.name))
    ]
    return max(numbers, default=0) + 1


def _diff(git: GitRunner, path: Path, base: str, local_tree: str, pathspec: list[str], *options: str) -> str:
    """The diff from `base` to `local_tree`, for `pathspec`."""
    return git.run(['diff', *options, base, local_tree, '--', *pathspec], cwd=path).stdout


def _write_missing_patch(git: GitRunner, path: Path, local_tree: str, pathspec: list[str], directory: Path) -> Path:
    """Write the missing patch into `directory`."""
    missing = _diff(git, path, 'HEAD', local_tree, pathspec, '--binary', '--full-index')
    git.run(['apply', '--index'], cwd=path, input=missing)
    _commit(git, path, TODO_TITLE, TODO_DESCRIPTION)
    directory.mkdir(parents=True, exist_ok=True)
    number = _next_number(directory)
    return Path(
        git.check_output(
            ['format-patch', '-1', f'--start-number={number}', '-o', directory.resolve(), 'HEAD'], cwd=path
        )
    )


def _write_diff(git: GitRunner, path: Path, base: str, local_tree: str, pathspec: list[str], file: Path) -> Path:
    """Write the whole diff from upstream to `file`."""
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        _diff(git, path, base, local_tree, pathspec, '--binary'), encoding='utf-8', errors='surrogateescape'
    )
    return file


def _report_difference(
    ctx: CommandContext, path: Path, base: str, local_tree: str, pathspec: list[str], subdir: Path
) -> str:
    """The error message when `subdir` differs; writes the missing file if it can."""
    git, files, out = ctx.git, [Path(file) for file in ctx.patches or []], ctx.flags.output_dir
    stat = _diff(git, path, 'HEAD', local_tree, pathspec, '--stat').rstrip()
    message = (
        f"{subdir.as_posix()}: differs from its upstream commit with {_counted(len(files), ctx.verify_mode)}\n{stat}"
    )

    if ctx.verify_mode == 'diff':
        return _diff_hint(git, path, base, local_tree, pathspec, message, out)

    directory = _patch_directory(out, files)
    if directory is None:
        return f"{message}\nname the patches, or use --output to have the missing one written"
    patch = _write_missing_patch(git, path, local_tree, pathspec, directory)
    return (
        f"{message}\nwrote the missing patch {_shown(patch)}\n"
        f"replace '{TODO_TITLE}' and '{TODO_DESCRIPTION}' in it, rename it to match, and commit it"
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
    return f"{message}\nwrote the whole diff to {_shown(written)}"


def _shown(path: Path) -> str:
    """`path`, relative to the current directory if inside it."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


@contextlib.contextmanager
def _worktree_at(git: GitRunner, path: Path, base: str, keep: bool = False) -> Iterator[None]:
    """A temporary worktree at `base`, removed afterwards unless `keep`."""
    worktree.remove_worktree(git, path)
    # --no-checkout and reset: skip the parent's post-checkout hook
    git.run(['worktree', 'add', '--quiet', '--detach', '--no-checkout', path, base])
    try:
        git.run(['reset', '-q', '--hard'], cwd=path)
        yield
    finally:
        if keep:
            output.say(f"kept the worktree at {path.as_posix()}")
        else:
            worktree.remove_worktree(git, path)


def _differs(git: GitRunner, path: Path, local_tree: str, pathspec: list[str]) -> bool:
    """Whether the worktree at `path` differs from `local_tree`."""
    return git.run(['diff', '--quiet', 'HEAD', local_tree, '--', *pathspec], cwd=path, may_fail=True).returncode != 0


def check_patches(git: GitRunner, config: NestedConfig, subref: str, subdir: Path, tmp: Path) -> None:
    """Refuse if subdir has changes that are not in its patches."""
    local_tree = git.check_output(['rev-parse', f'HEAD:{subdir.as_posix()}'])
    base = _upstream_base(git, config, subref, subdir)
    pathspec = patches.pathspec(patches.local_paths(git, config, subdir))
    path = tmp / 'verify' / subref
    with _worktree_at(git, path, base):
        _apply(git, path, patches.files(config, subdir), quiet=True)
        if _differs(git, path, local_tree, pathspec):
            raise GitNestedError(
                f"{subdir.as_posix()}: has changes that are not in its patches; "
                f"'git nested verify {subdir.as_posix()}' writes the missing one"
            )


def _files(ctx: CommandContext, config: NestedConfig, subdir: Path) -> list[Path]:
    """The files to apply: the given ones, else the patches folder from .gitnested."""
    patches.check(config, subdir)
    if config.patches and ctx.verify_mode != 'diff' and not ctx.patches:
        _use_patches_folder(ctx, config, subdir)
    files = [Path(file) for file in ctx.patches or []]
    missing = next((file for file in files if not file.is_file()), None)
    if missing:
        output.usage_error(f"{missing.as_posix()}: no such file")
    return files


def _use_patches_folder(ctx: CommandContext, config: NestedConfig, subdir: Path) -> None:
    """Take the patches from the folder, and write the missing one there too."""
    ctx.patches = [file.as_posix() for file in patches.files(config, subdir)]
    ctx.flags.output_dir = ctx.flags.output_dir or (subdir / config.patches).as_posix()


def cmd_verify(ctx: CommandContext) -> None:
    """Check that a nested repo is its upstream commit plus the given files."""
    git = ctx.git
    subdir, _, subref, config = setup.setup_command(git, 'verify', ctx.flags, ctx.subdir, ctx.upstream)
    files = _files(ctx, config, subdir)

    local_tree = git.check_output(['rev-parse', f'HEAD:{subdir.as_posix()}'])
    base = _upstream_base(git, config, subref, subdir)
    pathspec = patches.pathspec(patches.local_paths(git, config, subdir), filters.ignored_paths(ctx.flags, subdir))

    path = ctx.tmp / 'verify' / subref
    with _worktree_at(git, path, base, keep=ctx.flags.keep):
        _apply(git, path, files)
        if _differs(git, path, local_tree, pathspec):
            raise GitNestedError(_report_difference(ctx, path, base, local_tree, pathspec, subdir))

    output.say(
        f"{subdir.as_posix()}: matches upstream {config.commit[:9]} with {_counted(len(files), ctx.verify_mode)}"
    )
