"""Creating a branch that holds the nested repository's own commits."""

from __future__ import annotations

from pathlib import Path

from .. import content, messages, output, worktree
from ..cli import setup
from ..git import GitRunner
from ..models import CommandContext, NestedConfig
from . import fetch


def cmd_branch(ctx: CommandContext) -> None:
    """Create a branch containing the local nested repo commits."""
    git = ctx.git
    flags, subdir, upstream, git_tmp = ctx.flags, ctx.subdir, ctx.upstream, ctx.tmp
    subdir, gitnested, subref, config = setup.setup_command(git, 'branch', flags, subdir, upstream)

    if flags.fetch:
        fetch.do_fetch(git, config, subref)

    branch = f'nested/{subref}'
    if flags.force:
        worktree.delete_branch(git, branch, git_tmp)
    elif git.branch_exists(branch):
        output.error(_branch_exists_error(git, config, branch, subdir))

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
    )
    output.say(f"{subdir.as_posix()}: branch {branch} created, worktree at {subdir_worktree.as_posix()}")


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
