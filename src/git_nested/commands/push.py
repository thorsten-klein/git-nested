"""Pushing a nested subdirectory's commits back upstream."""

from __future__ import annotations

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
    found = git.network(
        ['ls-remote', '--exit-code', config.remote, ref], f"asking {config.remote} for {branch_name}", may_fail=True
    )
    if found.returncode == 2:  # no such ref
        return None
    if found.returncode != 0:
        raise GitNestedError(f"the fetch before the push failed: {found.stderr}")
    git.network(
        ['fetch', '--no-tags', '--quiet', config.remote, branch_name], f"fetching {config.remote} ({branch_name})"
    )
    upstream = git.check_output(['rev-parse', FETCH_HEAD_REV])
    if upstream == config.commit:
        return upstream
    if not flags.force:
        raise GitNestedError(f"upstream {branch_name} has commits you do not have; pull first")
    git.network(
        ['fetch', '--no-tags', '--quiet', config.remote, config.branch], f"fetching {config.remote} ({config.branch})"
    )
    return git.check_output(['rev-parse', FETCH_HEAD_REV])


def _build_push_branch(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    git_tmp: Path,
    subref: str,
    upstream_head: str | None,
) -> str:
    """Build the nested branch to push, rebased onto the fetched upstream when that is the method."""
    branch = refs.nested_branch(git, subref)
    worktree.delete_branch(git, branch, git_tmp)
    subdir_worktree = content.create_nested_branch(
        git=git,
        flags=flags,
        config=config,
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
            worktree.delete_branch(git, branch, git_tmp)
            output.error(f"{subdir.as_posix()}: git rebase failed, so nothing was pushed")
    if flags.squash:
        _squash(git, flags, branch, upstream_head or config.commit)
    return branch


def _squash(git: GitRunner, flags: Flags, branch: str, upstream: str) -> None:
    """Make `branch` one commit on top of where it meets `upstream`.

    The message is -m or --file. Else it lists the squashed commits.
    """
    base = git.check_output(['merge-base', branch, upstream], may_fail=True) if upstream else ''
    subjects = git.check_output(['log', '--reverse', '--format=%s', *([f'{base}..{branch}'] if base else [branch])])
    lines = subjects.splitlines()
    if len(lines) == 1:
        message = git.check_output(['log', '-1', '--format=%B', branch])
    else:
        message = f"Squash {len(lines)} commits\n\n" + "\n".join(f"- {line}" for line in lines)
    message = flags.message or message
    parent = ['-p', base] if base else []
    source = flags.message_file or '-'
    squashed = git.check_output(['commit-tree', *parent, '-F', source, f'{branch}^{{tree}}'], input=message)
    git.run(['update-ref', f'refs/heads/{branch}', squashed])


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

    A branch built here is removed afterwards, also when the push fails.

    Returns:
        the pushed commit, or None if upstream already has it.
    """
    if branch is not None:
        upstream_head = _fetch_push_target(git, flags, config, branch_name) if flags.dry_run else None
        return (
            _dry_run_push(git, flags, config, subdir, branch, branch_name, upstream_head)
            if flags.dry_run
            else _push(git, flags, config, subref, branch, branch_name, None)
        )
    upstream_head = _fetch_push_target(git, flags, config, branch_name)
    built = _build_push_branch(git, flags, config, subdir, gitnested, git_tmp, subref, upstream_head)
    try:
        if flags.dry_run:
            return _dry_run_push(git, flags, config, subdir, built, branch_name, upstream_head)
        return _push(git, flags, config, subref, built, branch_name, upstream_head)
    finally:
        worktree.delete_branch(git, built, git_tmp)


def _new_push_commit(git: GitRunner, flags: Flags, branch: str, upstream_head: str | None) -> str | None:
    """The commit a push would add upstream, or None if upstream already has it."""
    if not git.branch_exists(branch):
        raise GitNestedError(f"no nested branch {branch} to push")
    new_commit = git.check_output(['rev-parse', branch])
    if new_commit == upstream_head:
        return None
    if upstream_head and not flags.force and not git.commit_in_rev_list(upstream_head, branch):
        raise GitNestedError(f"can't commit: {branch} does not contain the upstream HEAD {upstream_head}")
    return new_commit


def _dry_run_push(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    branch: str,
    branch_name: str,
    upstream_head: str | None,
) -> str | None:
    """Show what a push would do, without pushing or recording it."""
    new_commit = _new_push_commit(git, flags, branch, upstream_head)
    if new_commit is None:
        return None
    rev = f'{upstream_head}..{branch}' if upstream_head else branch
    commits = git.check_output(['log', '--oneline', rev])
    output.say(f"{subdir.as_posix()}: would push to {config.remote} ({branch_name})")
    output.say('\n'.join(f"  {line}" for line in commits.splitlines()))
    return new_commit


def _push(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subref: str,
    branch: str,
    branch_name: str,
    upstream_head: str | None,
) -> str | None:
    """Push `branch` to branch_name upstream, unless upstream_head already is its tip.

    Only a branch built for the push is known to sit on upstream, so only
    then is there an upstream_head to compare against.
    """
    new_commit = _new_push_commit(git, flags, branch, upstream_head)
    if new_commit is None:
        return None
    git.network(
        ['push', *(['--force'] if flags.force else []), config.remote, f'{branch}:{branch_name}'],
        f"pushing to {config.remote} ({branch_name})",
    )
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


def _check_commit_target(flags: Flags, subdir: Path, gitnested: Path, config: NestedConfig, branch_name: str) -> None:
    """Refuse --commit unless the push goes to what .gitnested tracks.

    A recorded commit from elsewhere would break the next pull.
    """
    # Without -u, -r and -b do not change what .gitnested tracks.
    recorded = NestedConfig.from_file(gitnested)
    if not flags.update and (config.remote, config.branch) != (recorded.remote, recorded.branch):
        raise GitNestedError(
            f"{subdir.as_posix()}: --commit records the push in .gitnested, but -r and -b only change this push; "
            "add -u to track them"
        )
    if branch_name != config.branch:
        raise GitNestedError(
            f"{subdir.as_posix()}: --commit records the push in .gitnested, but it goes to {branch_name}, "
            f"not to the tracked branch {config.branch}; push there with -b {config.branch}"
        )


def _skip_read_only(flags: Flags, subdir: Path) -> None:
    """Skip a read-only repository with --all; refuse it otherwise."""
    if not flags.all:
        raise GitNestedError(
            f"{subdir.as_posix()}: is read-only, so push refuses; "
            f"'git nested config {subdir.as_posix()} readonly false' allows it"
        )
    output.say(f"{subdir.as_posix()}: skipped, it is read-only")


def _default_target(git: GitRunner, config: NestedConfig) -> str:
    """'<repo>-<branch>', or the tracked branch itself while upstream does not have it yet."""
    if discovery.has_branch(git, config.remote, config.branch) is False:
        output.verbose(f"{config.remote} has no branch {config.branch} yet, so the push makes it")
        return config.branch
    return f"{Path(git.check_output(['rev-parse', '--show-toplevel'])).name}-{config.branch}"


def cmd_push(ctx: CommandContext) -> None:
    """Push local nested repo changes upstream."""
    git, flags, branch = ctx.git, ctx.flags, ctx.nested_commit_ref
    subdir, gitnested, subref, config = setup.setup_command(git, 'push', flags, ctx.subdir, ctx.upstream)
    if config.readonly and not flags.dry_run:
        _skip_read_only(flags, subdir)
        return
    if branch and flags.squash:
        raise GitNestedError("--squash can't be combined with an explicit branch")

    output.verbose(f"pushing {subdir.as_posix()} upstream")
    branch_name = flags.branch or _default_target(git, config)
    if flags.commit:
        _check_commit_target(flags, subdir, gitnested, config, branch_name)
    new_commit = do_push(git, flags, config, subdir, gitnested, ctx.tmp, subref, branch_name, branch)
    if new_commit is None:
        output.say(f"{subdir.as_posix()}: nothing to push")
    elif not flags.dry_run:
        _pushed(ctx, config, subdir, gitnested, new_commit, branch_name)


def _pushed(
    ctx: CommandContext, config: NestedConfig, subdir: Path, gitnested: Path, new_commit: str, branch_name: str
) -> None:
    """Record the pushed commit when --commit asks for it, and report the push."""
    if ctx.flags.commit:
        _record_push_commit(ctx.git, ctx.flags, subdir, gitnested, config, new_commit, ctx.head)
    output.say(f"{subdir.as_posix()}: pushed to {config.remote} ({branch_name})")
