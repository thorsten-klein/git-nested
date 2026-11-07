"""Check a nested repository against its upstream commit plus patches or diffs."""

from __future__ import annotations

import re
from pathlib import Path

from .. import filters, output, worktree
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, NestedConfig
from . import fetch

# .gitnested files are not part of the upstream content.
GITNESTED_EXCLUDE = ':(exclude,glob)**/.gitnested*'

# Placeholders in a written patch, for the user to fill in.
TODO_TITLE = "TODO: title"
TODO_DESCRIPTION = "TODO: description"

# `git commit` needs an identity; CI often has none.
_FALLBACK_IDENTITY = ['-c', 'user.name=git-nested', '-c', 'user.email=git-nested@localhost']

_LEADING_NUMBER = re.compile(r'^(\d+)-')


def _identity(git: GitRunner) -> list[str]:
    """A stand-in identity if git has none."""
    return [] if git.check_output(['config', 'user.email'], may_fail=True) else _FALLBACK_IDENTITY


def _commit(git: GitRunner, path: Path, *message: str) -> None:
    """Commit in the worktree at `path`, without hooks or signing."""
    paragraphs = [arg for paragraph in message for arg in ('-m', paragraph)]
    git.run(
        [*_identity(git), 'commit', '--quiet', '--allow-empty', '--no-verify', '--no-gpg-sign', *paragraphs], cwd=path
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


def _apply(git: GitRunner, path: Path, files: list[Path]) -> None:
    """Apply `files` in order in the worktree at `path`, then commit.

    `git apply`, not `git am`: it takes plain diffs too.
    """
    for file in files:
        output.say(f"applying {_shown(file)}")
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


def _diff(git: GitRunner, path: Path, base: str, local_tree: str, *options: str) -> str:
    """The diff from `base` to `local_tree`, without .gitnested files."""
    return git.run(['diff', *options, base, local_tree, '--', '.', GITNESTED_EXCLUDE], cwd=path).stdout


def _write_missing_patch(git: GitRunner, path: Path, local_tree: str, directory: Path) -> Path:
    """Write the missing patch into `directory`."""
    git.run(['apply', '--index'], cwd=path, input=_diff(git, path, 'HEAD', local_tree, '--binary', '--full-index'))
    _commit(git, path, TODO_TITLE, TODO_DESCRIPTION)
    directory.mkdir(parents=True, exist_ok=True)
    number = _next_number(directory)
    return Path(
        git.check_output(
            ['format-patch', '-1', f'--start-number={number}', '-o', directory.resolve(), 'HEAD'], cwd=path
        )
    )


def _write_diff(git: GitRunner, path: Path, base: str, local_tree: str, file: Path) -> Path:
    """Write the whole diff from upstream to `file`."""
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(_diff(git, path, base, local_tree, '--binary'), encoding='utf-8', errors='surrogateescape')
    return file


def _report_difference(ctx: CommandContext, path: Path, base: str, local_tree: str, subdir: Path) -> str:
    """The error message when `subdir` differs; writes the missing file if it can."""
    git, files, out = ctx.git, [Path(file) for file in ctx.patches or []], ctx.flags.output_dir
    stat = _diff(git, path, 'HEAD', local_tree, '--stat').rstrip()
    message = (
        f"{subdir.as_posix()}: differs from its upstream commit with {_counted(len(files), ctx.verify_mode)}\n{stat}"
    )

    if ctx.verify_mode == 'diff':
        return _diff_hint(git, path, base, local_tree, message, out)

    directory = Path(out) if out else files[-1].parent if files else None
    if directory is None:
        return f"{message}\nname the patches, or use --output to have the missing one written"
    patch = _write_missing_patch(git, path, local_tree, directory)
    return (
        f"{message}\nwrote the missing patch {_shown(patch)}\n"
        f"replace '{TODO_TITLE}' and '{TODO_DESCRIPTION}' in it, rename it to match, and commit it"
    )


def _diff_hint(git: GitRunner, path: Path, base: str, local_tree: str, message: str, out: str | None) -> str:
    """`message` for 'diff' mode, after writing the whole diff to `out` if given."""
    if not out:
        return f"{message}\nuse --output to have the whole diff written"
    return f"{message}\nwrote the whole diff to {_shown(_write_diff(git, path, base, local_tree, Path(out)))}"


def _shown(path: Path) -> str:
    """`path`, relative to the current directory if inside it."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def cmd_verify(ctx: CommandContext) -> None:
    """Check that a nested repo is its upstream commit plus the given files."""
    git = ctx.git
    subdir, _, subref, config = setup.setup_command(git, 'verify', ctx.flags, ctx.subdir, ctx.upstream)
    files = [Path(file) for file in ctx.patches or []]
    for file in files:
        if not file.is_file():
            output.usage_error(f"{file.as_posix()}: no such file")

    local_tree = git.check_output(['rev-parse', f'HEAD:{subdir.as_posix()}'])
    base = _upstream_base(git, config, subref, subdir)

    path = ctx.tmp / 'verify' / subref
    worktree.remove_worktree(git, path)
    # --no-checkout and reset: skip the parent's post-checkout hook
    git.run(['worktree', 'add', '--quiet', '--detach', '--no-checkout', path, base])
    try:
        git.run(['reset', '-q', '--hard'], cwd=path)
        _apply(git, path, files)
        differs = git.run(
            ['diff', '--quiet', 'HEAD', local_tree, '--', '.', GITNESTED_EXCLUDE], cwd=path, may_fail=True
        )
        if differs.returncode != 0:
            raise GitNestedError(_report_difference(ctx, path, base, local_tree, subdir))
    finally:
        if ctx.flags.keep:
            output.say(f"kept the worktree at {path.as_posix()}")
        else:
            worktree.remove_worktree(git, path)

    output.say(
        f"{subdir.as_posix()}: matches upstream {config.commit[:9]} with {_counted(len(files), ctx.verify_mode)}"
    )
