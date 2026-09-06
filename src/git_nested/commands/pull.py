"""Pulling upstream changes into a nested subdirectory."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from .. import content, filters, output, refs, worktree
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig
from . import clone, fetch


def do_pull(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    git_tmp: Path,
    subref: str,
) -> tuple[bool, str | None, Path | None, str | None]:
    """Pull implementation.

    Returns:
        tuple: (success, nested_commit_ref, subdir_worktree, error_msg)
    """
    upstream_head_commit = fetch.do_fetch(git, config, subref)

    # Force reclone is handled entirely by the caller (cmd_pull), which
    # never calls do_pull() when flags.force is set.
    if upstream_head_commit == config.commit and not flags.update:
        return False, None, None, None

    branch = f'nested/{subref}'
    worktree.delete_branch(git, branch, git_tmp)
    nested_commit_ref = branch

    output.verbose(f"Create nested branch '{branch}'.")
    subdir_worktree = content.create_nested_branch(
        git=git,
        flags=flags,
        config=config,
        branch=branch,
        subdir=subdir,
        gitnested=gitnested,
        git_tmp=git_tmp,
        subref=subref,
        command='pull',
    )

    method = flags.method or config.method
    merge_target = _pull_merge_target(git, subref, config, subdir_worktree, upstream_head_commit)

    error_msg = _run_merge_or_rebase(git, method, merge_target, branch, config, subdir_worktree)
    if error_msg:
        # Merge/rebase failed - return failure with error message
        return False, nested_commit_ref, subdir_worktree, error_msg

    refs.create_nested_ref(git, subref, 'branch', branch)

    return True, nested_commit_ref, subdir_worktree, None


def _pull_merge_target(
    git: GitRunner, subref: str, config: NestedConfig, subdir_worktree: Path, upstream_head_commit: str
) -> str:
    """Determine what to merge/rebase onto: the raw fetch, or a filtered view of it."""
    refs_fetch = f'refs/nested/{subref}/fetch'
    if not config.filter:
        return refs_fetch

    # The local nested branch only ever contained the filtered subset of
    # files. Merging the raw (unfiltered) upstream fetch against it makes
    # git see files that were "deleted" locally (because they were never
    # pulled in) as delete/modify conflicts whenever upstream touches
    # them. Build a filtered view of the fetched commit so only files
    # that actually matter to the local checkout can conflict.
    return filters.build_filtered_commit(git, subdir_worktree, config, upstream_head_commit)


def _run_merge_or_rebase(
    git: GitRunner, method: str, merge_target: str, branch: str, config: NestedConfig, subdir_worktree: Path
) -> str | None:
    """Run the merge or rebase step of a pull; return an error message on failure, else None."""
    try:
        if method == 'rebase':
            git.run(['rebase', merge_target, branch], cwd=subdir_worktree, print_error=False)
        else:
            # If parent is empty, allow unrelated histories (for nested-in-nested repos)
            merge_cmd = ['merge', merge_target]
            if not config.parent:
                merge_cmd.append('--allow-unrelated-histories')
            git.run(merge_cmd, cwd=subdir_worktree, print_error=False)
    except GitNestedError as e:
        return f'The "git {method}" command failed:\n{e.message}'
    return None


def _pull_forced(git, flags, subdir, gitnested, subref, config, head_commit) -> None:
    """Handle cmd_pull's `--force` path: reclone via do_clone, committing the result if needed."""
    up_to_date, config, nested_commit_ref, upstream_head_commit = clone.do_clone(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        subref=subref,
    )
    if not up_to_date:
        # do_clone only returns a None nested_commit_ref together with up_to_date=True.
        if nested_commit_ref is None:
            raise AssertionError(
                'do_clone returned nested_commit_ref=None with up_to_date=False'
            )  # pragma: no cover -- invariant guard, unreachable via the public API
        content.commit_nested_branch(
            git=git,
            flags=flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            nested_commit_ref=nested_commit_ref,
            upstream_head_commit=upstream_head_commit,
            head_commit=head_commit,
            subdir_worktree=None,
            command='clone',
        )
    output.say(f"Nested repository '{subdir}' pulled from '{config.remote}' ({config.branch}).")


def _build_pull_conflict_help(subdir, subdir_worktree, method, flags, subref) -> str:
    """Build the operator-facing help text shown when a pull's merge/rebase conflicts."""
    branch_name = f'nested/{subref}'
    rebase_step = "git rebase --continue" if method == 'rebase' else "git commit"
    commit_cmd = (
        f"git nested commit --file={flags.message_file} {subdir}"
        if flags.message_file
        else f"git nested commit {subdir}"
    )
    rebase_note = ""
    if method == 'rebase':
        rebase_note = textwrap.dedent(
            f"""

            After you have performed the steps above you can push your local changes
            without repeating the rebase by:
              1. git nested push {subdir} {branch_name}
            """
        )
    return textwrap.dedent(
        f"""\
        You will need to finish the pull by hand. A new working tree has been
        created at {subdir_worktree} so that you can resolve the conflicts
        shown in the output above.

        This is the common conflict resolution workflow:

          1. cd {subdir_worktree}
          2. Resolve the conflicts (see "git status").
          3. "git add" the resolved files.
          4. {rebase_step}
          5. If there are more conflicts, restart at step 2.
          6. cd {Path.cwd()}
          7. {commit_cmd}
        {rebase_note}
        See "git help {method}" for details.

        Alternatively, you can abort the pull and reset back to where you started:

          1. git nested clean {subdir}

        See "git help nested" for more help.
        """
    )


def cmd_pull(ctx: CommandContext) -> None:
    """Pull upstream changes to the nested repo.

    _nested_commit_ref is unused: unlike push/commit, pull has no positional argument
    that populates it, but dispatch_command() calls every cmd_* with the same signature.
    """
    git = ctx.git
    flags, subdir, upstream, git_tmp, head_commit = ctx.flags, ctx.subdir, ctx.upstream, ctx.tmp, ctx.head
    subdir, gitnested, subref, config = setup.setup_command(git, 'pull', flags, subdir, upstream)

    if flags.force:
        _pull_forced(git, flags, subdir, gitnested, subref, config, head_commit)
        return

    success, pulled_commit_ref, subdir_worktree, error_msg = do_pull(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        git_tmp=git_tmp,
        subref=subref,
    )

    if not success and pulled_commit_ref is None:
        output.say(f"Nested repository '{subdir}' is up to date with upstream branch '{config.branch}'.")
        return

    if not success:
        # do_pull's only other failure path (merge/rebase conflict) always pairs a
        # non-None pulled_commit_ref, subdir_worktree, and error_msg together.
        # _handle_pull_conflict() never returns: it always exits or raises.
        _handle_pull_conflict(subdir, subdir_worktree, error_msg, config, flags, subref)

    _finalize_successful_pull(
        git, flags, subdir, gitnested, subref, config, pulled_commit_ref, subdir_worktree, head_commit
    )


def _handle_pull_conflict(subdir, subdir_worktree, error_msg, config, flags, subref) -> None:
    """Report a pull's merge/rebase conflict and exit, per do_pull's failure path."""
    if error_msg is None:
        raise AssertionError(
            'do_pull returned error_msg=None with success=False and nested_commit_ref set'
        )  # pragma: no cover -- invariant guard, unreachable via the public API
    # Print the error message to stdout
    output.say(error_msg)
    # Merge/rebase failed
    method = flags.method or config.method
    msg = _build_pull_conflict_help(subdir, subdir_worktree, method, flags, subref)
    output.say(msg)
    sys.exit(1)


def _finalize_successful_pull(
    git, flags, subdir, gitnested, subref, config, nested_commit_ref, subdir_worktree, head_commit
) -> None:
    """Commit a successfully-pulled nested branch and report success.

    do_pull's success path always pairs non-None nested_commit_ref and subdir_worktree.
    """
    if nested_commit_ref is None or subdir_worktree is None:
        raise AssertionError(
            'do_pull returned success=True without nested_commit_ref/subdir_worktree set'
        )  # pragma: no cover -- invariant guard, unreachable via the public API
    output.verbose(f"Commit the new '{nested_commit_ref}' content.")
    upstream_head_commit = git.check_output(['rev-parse', f'refs/nested/{subref}/fetch'])
    content.commit_nested_branch(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        nested_commit_ref=nested_commit_ref,
        upstream_head_commit=upstream_head_commit,
        head_commit=head_commit,
        subdir_worktree=subdir_worktree,
        command='pull',
    )
    output.say(f"Nested repository '{subdir}' pulled from '{config.remote}' ({config.branch}).")
