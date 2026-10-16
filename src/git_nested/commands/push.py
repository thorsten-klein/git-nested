"""Pushing a nested subdirectory's commits back upstream."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from .. import content, discovery, gitfile, output, refs, worktree
from ..cli import setup
from ..constants import FETCH_HEAD_REV
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig


def _fetch_push_target(git: GitRunner, flags: Flags, config: NestedConfig, branch_name: str) -> str | None:
    """The upstream commit to push on top of; None when branch_name does not exist upstream yet."""
    # Ask with an exit code, not git's message: that one is translated.
    ref = branch_name if branch_name.startswith('refs/') else f'refs/heads/{branch_name}'
    found = git.run(['ls-remote', '--exit-code', config.remote, ref], may_fail=True)
    if found.returncode == 2:  # no such ref
        return None
    if found.returncode != 0:
        raise GitNestedError(f"the fetch before the push failed: {found.stderr}")
    git.run(['fetch', '--no-tags', '--quiet', config.remote, branch_name])
    upstream = git.check_output(['rev-parse', FETCH_HEAD_REV])
    if upstream == config.commit:
        return upstream
    if not flags.force:
        raise GitNestedError(f"upstream {branch_name} has commits you do not have; pull first")
    git.run(['fetch', '--no-tags', '--quiet', config.remote, config.branch])
    return git.check_output(['rev-parse', FETCH_HEAD_REV])


def _build_push_branch(
    git: GitRunner, flags: Flags, config: NestedConfig, subdir: Path, gitnested: Path, git_tmp: Path, subref: str
) -> str:
    """Build the nested branch to push, rebased onto the fetched upstream when that is the method."""
    branch = refs.nested_branch(git, subref)
    worktree.delete_branch(git, branch, git_tmp)
    subdir_worktree = content.create_nested_branch(
        git=git,
        flags=flags,
        config=dataclasses.replace(config, parent='HEAD^') if flags.squash else config,
        branch=branch,
        subdir=subdir,
        gitnested=gitnested,
        git_tmp=git_tmp,
        subref=subref,
        command='push',
    )
    if (flags.method or config.method) == 'rebase':
        try:
            git.run(['rebase', f'refs/nested/{subref}/fetch', branch], cwd=subdir_worktree)
        except GitNestedError:
            output.error(f"{subdir.as_posix()}: git rebase failed, so nothing was pushed")
    return branch


def do_push(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    git_tmp: Path,
    subref: str,
    branch_name: str,
    branch: str | None,
) -> str | None:
    """Push `branch`, or else a nested branch built for the purpose, to branch_name upstream.

    Returns:
        the pushed commit, or None if upstream already has it.
    """
    # Only a branch built here is known to sit on upstream, so only then is
    # there an upstream commit to compare against.
    upstream_head = None
    if branch is None:
        upstream_head = _fetch_push_target(git, flags, config, branch_name)
        branch = _build_push_branch(git, flags, config, subdir, gitnested, git_tmp, subref)

    if not git.branch_exists(branch):
        raise GitNestedError(f"no nested branch {branch} to push")
    new_commit = git.check_output(['rev-parse', branch])
    if new_commit == upstream_head:
        return None
    if upstream_head and not flags.force and not git.commit_in_rev_list(upstream_head, branch):
        raise GitNestedError(f"can't commit: {branch} does not contain the upstream HEAD {upstream_head}")

    git.run(['push', *(['--force'] if flags.force else []), config.remote, f'{branch}:{branch_name}'])
    refs.create_nested_ref(git, subref, 'push', branch)
    return new_commit


def _record_push_commit(
    git: GitRunner, flags: Flags, subdir: Path, gitnested: Path, config: NestedConfig, new_commit: str, head_commit: str
) -> None:
    """Update `.gitnested` and create a commit recording the push (the --commit flag)."""
    output.verbose(f"writing {subdir.as_posix()}/.gitnested")
    gitfile.update_gitrepo_file(
        git=git,
        flags=flags,
        config=config,
        gitnested=gitnested,
        upstream_head_commit=new_commit,
        nested_commit_ref=new_commit,
        head_commit=head_commit,
        command='push',
    )
    msg = flags.message or discovery.build_commit_message(git, config, new_commit, new_commit, subdir, 'push')
    content.commit_gitnested_update(git, flags, subdir, msg)


def cmd_push(ctx: CommandContext) -> None:
    """Push local nested repo changes upstream."""
    git, flags, branch = ctx.git, ctx.flags, ctx.nested_commit_ref
    subdir, gitnested, subref, config = setup.setup_command(git, 'push', flags, ctx.subdir, ctx.upstream)
    if branch and flags.squash:
        raise GitNestedError("--squash can't be combined with an explicit branch")

    output.verbose(f"pushing {subdir.as_posix()} upstream")
    branch_name = flags.branch or f"{Path(git.check_output(['rev-parse', '--show-toplevel'])).name}-{config.branch}"
    # A commit recorded on another branch than the tracked one breaks the next pull.
    if flags.commit and branch_name != config.branch:
        raise GitNestedError(
            f"{subdir.as_posix()}: --commit records the push in .gitnested, but it goes to {branch_name}, "
            f"not to the tracked branch {config.branch}; push there with -b {config.branch}"
        )
    new_commit = do_push(git, flags, config, subdir, gitnested, ctx.tmp, subref, branch_name, branch)

    if branch is None:
        # The branch was built for this push alone.
        worktree.delete_branch(git, refs.nested_branch(git, subref), ctx.tmp)
    if new_commit is None:
        output.say(f"{subdir.as_posix()}: nothing to push")
        return
    if flags.commit:
        _record_push_commit(git, flags, subdir, gitnested, config, new_commit, ctx.head)
    output.say(f"{subdir.as_posix()}: pushed to {config.remote} ({branch_name})")
