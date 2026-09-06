"""Pushing a nested subdirectory's commits back upstream."""

from __future__ import annotations

import re
from pathlib import Path

from .. import content, discovery, gitfile, output, refs, worktree
from ..cli import setup
from ..constants import FETCH_HEAD_REV
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig


def do_push(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    git_tmp: Path,
    subref: str,
    branch: str | None = None,
) -> tuple[bool, str, Path | None, bool, str | None]:
    """Push implementation.

    Returns:
        tuple: (success, branch_name, subdir_worktree, branch_created, new_commit)
    """
    branch_name = _push_branch_name(git, flags, config)

    branch, subdir_worktree, branch_created, new_upstream, upstream_head_commit, early_exit = _push_branch_setup(
        git, flags, config, subdir, gitnested, git_tmp, subref, branch, branch_name
    )
    if early_exit:
        return early_exit

    if not git.branch_exists(branch):
        raise GitNestedError(f"no nested branch {branch} to push")

    new_commit = git.check_output(['rev-parse', branch])
    up_to_date_result = _push_up_to_date_result(
        new_upstream, upstream_head_commit, new_commit, branch, branch_name, branch_created, git, git_tmp
    )
    if up_to_date_result:
        return up_to_date_result

    _push_check_ancestry(git, flags, new_upstream, upstream_head_commit, branch)

    _push_run_push(git, flags, config, branch, branch_name, subref)

    return True, branch_name, subdir_worktree, branch_created, new_commit


def _push_branch_name(git: GitRunner, flags: Flags, config: NestedConfig) -> str:
    """Compute the resulting remote branch name for a push."""
    branch_name = flags.branch
    if not branch_name:
        toplevel = git.check_output(['rev-parse', '--show-toplevel'])
        repo_name = Path(toplevel).name
        branch_name = f"{repo_name}-{config.branch}"
    return branch_name


def _push_fetch_missing_upstream(stderr: str) -> bool:
    """Check whether a failed fetch means 'no such branch upstream yet' (ok) vs a real error.

    Returns:
        True when the fetch failed because the branch doesn't exist upstream yet.
    """
    if re.search(r"(^|\n)fatal: couldn't find remote ref ", stderr.lower()):
        return True
    raise GitNestedError(f"the fetch before the push failed: {stderr}")


def _push_verify_or_refetch(git: GitRunner, flags: Flags, config: NestedConfig, branch_name: str, upstream: str) -> str:
    """Ensure upstream hasn't moved past config.commit, or refetch the original branch under --force."""
    if upstream == config.commit:
        return upstream
    if not flags.force:
        raise GitNestedError(f"upstream {branch_name} has commits you do not have; pull first")
    # Force mode: fetch original branch to be based on correct commit
    git.run(['fetch', '--no-tags', '--quiet', config.remote, config.branch])
    return git.check_output(['rev-parse', FETCH_HEAD_REV])


def _push_fetch_upstream(
    git: GitRunner, flags: Flags, config: NestedConfig, branch_name: str
) -> tuple[bool, str | None]:
    """Auto-fetch the push target branch and validate we're not behind upstream.

    Returns:
        tuple: (new_upstream, upstream_head_commit)
    """
    result = git.run(['fetch', '--no-tags', '--quiet', config.remote, branch_name], may_fail=True)
    if result.returncode != 0:
        return _push_fetch_missing_upstream(result.stderr), None
    upstream = git.check_output(['rev-parse', FETCH_HEAD_REV])
    upstream = _push_verify_or_refetch(git, flags, config, branch_name, upstream)
    return False, upstream


def _push_branch_setup(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    git_tmp: Path,
    subref: str,
    branch: str | None,
    branch_name: str,
) -> tuple[str, Path | None, bool, bool, str | None, tuple | None]:
    """Resolve the local branch to push: prepare a fresh nested branch, or validate an explicit one.

    Returns:
        tuple: (branch, subdir_worktree, branch_created, new_upstream, upstream_head_commit, early_exit)
    """
    if not branch:
        return _push_prepare_branch(git, flags, config, subdir, gitnested, git_tmp, subref, branch_name)
    if flags.squash:
        raise GitNestedError("--squash can't be combined with an explicit branch")
    return branch, None, False, False, None, None


def _push_prepare_branch(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    git_tmp: Path,
    subref: str,
    branch_name: str,
) -> tuple[str, Path, bool, bool, str | None, tuple | None]:
    """Auto-fetch, create the local nested branch, and rebase it onto the fetched upstream.

    Returns:
        tuple: (branch, subdir_worktree, branch_created, new_upstream, upstream_head_commit, early_exit).
        early_exit is the do_push result to return immediately if the rebase fails, else None.
    """
    new_upstream, upstream_head_commit = _push_fetch_upstream(git, flags, config, branch_name)

    branch = f'nested/{subref}'
    subdir_worktree = git_tmp / branch
    worktree.delete_branch(git, branch, git_tmp)

    updated_config = config
    if flags.squash:
        updated_config = NestedConfig(
            remote=config.remote,
            branch=config.branch,
            commit=config.commit,
            parent='HEAD^',
            method=config.method,
        )

    subdir_worktree = content.create_nested_branch(
        git=git,
        flags=flags,
        config=updated_config,
        branch=branch,
        subdir=subdir,
        gitnested=gitnested,
        git_tmp=git_tmp,
        subref=subref,
        command='push',
    )

    method = flags.method or config.method
    if method == 'rebase':
        refs_fetch = f'refs/nested/{subref}/fetch'
        try:
            git.run(['rebase', refs_fetch, branch], cwd=subdir_worktree)
        except GitNestedError:
            early_exit = (False, branch_name, subdir_worktree, True, None)
            return branch, subdir_worktree, True, new_upstream, upstream_head_commit, early_exit

    return branch, subdir_worktree, True, new_upstream, upstream_head_commit, None


def _push_up_to_date_result(
    new_upstream: bool,
    upstream_head_commit: str | None,
    new_commit: str,
    branch: str,
    branch_name: str,
    branch_created: bool,
    git: GitRunner,
    git_tmp: Path,
) -> tuple | None:
    """Check whether the branch is already up to date with upstream.

    Returns:
        the do_push result to return if up to date, else None.
    """
    if new_upstream or upstream_head_commit != new_commit:
        return None
    if branch_created:
        worktree.delete_branch(git, branch, git_tmp)
    return False, branch_name, None, branch_created, new_commit


def _push_check_ancestry(
    git: GitRunner, flags: Flags, new_upstream: bool, upstream_head_commit: str | None, branch: str
) -> None:
    """Ensure branch contains upstream HEAD before pushing, unless --force or nothing to compare against.

    upstream_head_commit is only known when we auto-fetched above (branch was
    None on entry); when the caller passes an explicit branch we have nothing
    to compare ancestry against, so the safety check is skipped rather than
    spuriously failing against a None commit-ish.
    """
    if flags.force or new_upstream or upstream_head_commit is None:
        return
    if not git.commit_in_rev_list(upstream_head_commit, branch):
        raise GitNestedError(f"can't commit: {branch} does not contain the upstream HEAD {upstream_head_commit}")


def _push_run_push(
    git: GitRunner, flags: Flags, config: NestedConfig, branch: str, branch_name: str, subref: str
) -> None:
    """Run the actual `git push` for the nested branch and record the push ref."""
    cmd = ['push']
    if flags.force:
        cmd.append('--force')
    cmd.extend([config.remote, f'{branch}:{branch_name}'])
    git.run(cmd)

    refs.create_nested_ref(git, subref, 'push', branch)


def cmd_push(ctx: CommandContext) -> None:
    """Push local nested repo changes upstream."""
    git = ctx.git
    flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit = (
        ctx.flags,
        ctx.subdir,
        ctx.upstream,
        ctx.nested_commit_ref,
        ctx.tmp,
        ctx.head,
    )
    subdir, gitnested, subref, config = setup.setup_command(git, 'push', flags, subdir, upstream)

    output.verbose(f"pushing {subdir} upstream")
    success, branch_name, subdir_worktree, branch_created, new_commit = do_push(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        git_tmp=git_tmp,
        subref=subref,
        branch=nested_commit_ref,
    )

    if _handle_push_failure(success, subdir_worktree, subdir):
        return

    # do_push only returns success=True together with a non-None new_commit
    # (the None case is paired exclusively with success=False above).
    if new_commit is None:
        raise AssertionError(
            'do_push returned success=True with new_commit=None'
        )  # pragma: no cover -- invariant guard, unreachable via the public API

    if branch_created:
        output.verbose(f"removing branch nested/{subref}")
        worktree.delete_branch(git, f'nested/{subref}', git_tmp)

    # Update .gitnested if --commit or if --remote/--branch specified
    if flags.commit:
        _record_push_commit(git, flags, subdir, gitnested, config, new_commit, head_commit)

    output.say(f"{subdir}: pushed to {config.remote} ({branch_name})")


def _handle_push_failure(success: bool, subdir_worktree: Path | None, subdir: Path) -> bool:
    """Handle a failed do_push call (rebase failure or nothing to push).

    Returns:
        True if the caller should stop (push did not succeed), else False.
    """
    if not success and subdir_worktree:
        # Rebase failed
        output.error(f"{subdir}: git rebase failed, so nothing was pushed")

    if not success:
        output.say(f"{subdir}: nothing to push")
        return True

    return False


def _record_push_commit(
    git: GitRunner,
    flags: Flags,
    subdir: Path,
    gitnested: Path,
    config: NestedConfig,
    new_commit: str,
    head_commit: str,
) -> None:
    """Update `.gitnested` and create a commit recording the push (the --commit flag)."""
    output.verbose(f"writing {subdir}/.gitnested")

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

    msg = flags.message or discovery.build_commit_message(
        git=git,
        config=config,
        upstream_head_commit=new_commit,
        nested_commit_ref=new_commit,
        subdir=subdir,
        command='push',
    )

    if flags.message_file:
        git.run(['commit', '--file', flags.message_file])
    else:
        git.run(['commit', '-m', msg])
