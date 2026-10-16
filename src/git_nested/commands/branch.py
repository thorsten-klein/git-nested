"""Creating a branch that holds the nested repository's own commits."""

from __future__ import annotations

from pathlib import Path

from .. import content, messages, output, refs, worktree
from ..cli import setup
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig
from . import fetch


def cmd_branch(ctx: CommandContext) -> None:
    """Create a branch containing the local nested repo commits."""
    git = ctx.git
    flags, subdir, upstream, git_tmp = ctx.flags, ctx.subdir, ctx.upstream, ctx.tmp
    subdir, gitnested, subref, config = setup.setup_command(git, 'branch', flags, subdir, upstream)

    if flags.fetch:
        fetch.do_fetch(git, config, subref)

    # `current` is this nested repository's branch as things stand; `branch`
    # the one to build, which differs only when --name renames it.
    current = refs.nested_branch(git, subref)
    branch = _branch_to_build(git, flags, current, subdir)
    target = Path(flags.dir) if flags.dir else git_tmp / branch
    _clear_the_way(git, flags, config, current, subdir, target, git_tmp)

    subdir_worktree = content.create_nested_branch(
        git=git,
        flags=flags,
        config=config,
        branch=branch,
        subdir=subdir,
        gitnested=gitnested,
        git_tmp=git_tmp,
        subref=subref,
        command='branch',
        worktree_dir=target,
    )
    refs.record_nested_branch(git, subref, branch)
    output.say(f"{subdir.as_posix()}: branch {branch} created, worktree at {subdir_worktree.as_posix()}")


def _branch_to_build(git: GitRunner, flags: Flags, current: str, subdir: Path) -> str:
    """The branch to build: --name if given and acceptable, else the `current` one."""
    if flags.name and flags.name != current:
        _check_new_name(git, flags.name, subdir)
    return flags.name or current


def _clear_the_way(
    git: GitRunner, flags: Flags, config: NestedConfig, current: str, subdir: Path, target: Path, git_tmp: Path
) -> None:
    """Remove the `current` branch and its worktree where asked to, and abort where not."""
    # Naming a directory that already holds this nested repository's worktree
    # asks for it to be rebuilt there, so that needs no --force.
    if (flags.dir and _target_holds_branch(git, target, current, subdir)) or flags.force:
        worktree.delete_branch(git, current, git_tmp)
    elif git.branch_exists(current):
        output.error(_branch_exists_error(git, config, current, subdir))


def _check_new_name(git: GitRunner, branch: str, subdir: Path) -> None:
    """Refuse a --name that git would not take, or that belongs to a branch git-nested does not own.

    Not even --force replaces such a branch: it would be one of the user's
    own, and `--name main --force` must not be a way to lose it.
    """
    if git.run(['check-ref-format', '--branch', branch], may_fail=True).returncode != 0:
        output.usage_error(f"{branch}: not a valid branch name")
    if git.branch_exists(branch):
        output.error(f"branch {branch} already exists and is not the nested branch of {subdir.as_posix()}")


def _target_holds_branch(git: GitRunner, target: Path, branch: str, subdir: Path) -> bool:
    """Whether `target` is already the worktree of `branch`; abort if it is in use otherwise.

    A worktree of anything else -- another nested repository, or the parent
    repository itself -- is never taken over, and neither is a directory
    with files in it that git does not know as a worktree.
    """
    if not target.exists():
        return False
    is_worktree, checked_out = worktree.branch_at(git, target)
    if not is_worktree:
        _check_plain_directory(target, subdir)
        return False
    if checked_out != branch:
        what = f"branch {checked_out}" if checked_out else "a detached HEAD"
        output.error(f"{target.as_posix()}: already a worktree, of {what} -- not of {subdir.as_posix()}")
    return True


def _check_plain_directory(target: Path, subdir: Path) -> None:
    """Abort unless `target`, which is no worktree, is an empty directory git can put one in."""
    if not target.is_dir() or any(target.iterdir()):
        output.error(f"{target.as_posix()}: already exists and is not a worktree of {subdir.as_posix()}")


def _created(git: GitRunner, branch: str) -> str | None:
    """When `branch` was created, from the oldest entry of its reflog (None without a reflog)."""
    reflog = git.check_output(
        ['reflog', 'show', '--format=%gd', '--date=relative', f'refs/heads/{branch}'], may_fail=True
    )
    if not reflog:
        return None
    # The selector reads 'nested/foo@{3 hours ago}'; the date is between the braces.
    oldest = reflog.splitlines()[-1]
    return oldest[oldest.find('@{') + 2 : -1] if oldest.endswith('}') else None


def _upstream_fact(git: GitRunner, config: NestedConfig, branch: str) -> str | None:
    """How `branch` relates to the upstream commit recorded in .gitnested; None if that is not known here."""
    if not (config.commit and git.rev_exists(config.commit)):
        return None
    commit = config.commit[:9]
    if not git.commit_in_rev_list(config.commit, branch):
        return f"not based on {commit} recorded in .gitnested (outdated)"
    count = int(git.check_output(['rev-list', '--count', f'{config.commit}..{branch}']))
    return f"{count} local commit{'' if count == 1 else 's'} on top of {commit}"


def _content_fact(git: GitRunner, branch: str, subdir: Path) -> str | None:
    """Whether `branch` still matches the subdir as committed in HEAD; None if git could not tell."""
    # The branch drops .gitnested, so that file aside the two should be equal.
    diff = git.run(
        ['diff', '--quiet', branch, f'HEAD:{subdir.as_posix()}', '--', '.', ':(exclude).gitnested'], may_fail=True
    )
    if diff.returncode > 1:
        return None
    state = "up to date with" if diff.returncode == 0 else "differs from"
    return f"{state} {subdir.as_posix()}/ in HEAD"


def _branch_exists_error(git: GitRunner, config: NestedConfig, branch: str, subdir: Path) -> str:
    """Describe the existing `branch`, so the user can tell whether to reuse or replace it."""
    checked_out = worktree.find_worktree(git, branch)
    facts = [
        ('branch', branch),
        ('tip', git.check_output(['log', '-1', '--format=%h %s', branch])),
        ('created', _created(git, branch)),
        ('upstream', _upstream_fact(git, config, branch)),
        ('content', _content_fact(git, branch, subdir)),
        ('worktree', checked_out.as_posix() if checked_out else None),
    ]
    return messages.branch_exists(subdir, branch, facts)
