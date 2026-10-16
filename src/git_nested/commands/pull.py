"""Pulling upstream changes into a nested subdirectory."""

from __future__ import annotations

from pathlib import Path

from .. import content, filters, messages, output, refs, worktree
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
) -> tuple[str, Path] | None:
    """Rebuild the nested branch and merge or rebase upstream into it.

    Returns:
        tuple: (branch, subdir_worktree) holding the result, or None if upstream had nothing new.
    """
    upstream_head_commit = fetch.do_fetch(git, config, subref)
    if upstream_head_commit == config.commit and not flags.update:
        return None

    branch = refs.nested_branch(git, subref)
    worktree.delete_branch(git, branch, git_tmp)
    output.verbose(f"creating nested branch {branch}")
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

    # The nested branch only ever held the filtered subset of upstream, so a
    # merge of the raw upstream would see every file left out as deleted
    # locally, and conflict wherever upstream touched one. A filtered view of
    # the fetched commit leaves only the files that matter to conflict.
    merge_target = f'refs/nested/{subref}/fetch'
    if config.filter:
        merge_target = filters.build_filtered_commit(git, subdir_worktree, config.filter, upstream_head_commit)

    method = flags.method or config.method
    cmd = _join_command(method, config, merge_target, branch)
    try:
        git.run(cmd, cwd=subdir_worktree)
    except GitNestedError as e:
        help_text = messages.pull_conflict_help(subdir, subdir_worktree, method, flags.message_file, subref)
        # e.message ends with git's own stderr, and so with however many
        # newlines git felt like; rstrip normalises that, and the one added
        # here plus the one help_text opens with leave a blank line between
        # what failed and what to do about it.
        output.error(
            f"{subdir.as_posix()}: the pull is unfinished, git {method} failed:\n{e.message.rstrip()}\n{help_text}"
        )

    refs.create_nested_ref(git, subref, 'branch', branch)
    return branch, subdir_worktree


def _join_command(method: str, config: NestedConfig, merge_target: str, branch: str) -> list[str]:
    """The git command that joins upstream into the nested branch."""
    if method == 'rebase':
        # --onto: only the local commits move, also onto an upstream whose history was rewritten
        return ['rebase', '--onto', merge_target, config.commit or merge_target, branch]
    # --ff and --no-edit: the user's merge.ff must not apply here.
    # Without a parent the histories are unrelated (nested-in-nested repos).
    return ['merge', '--ff', '--no-edit', merge_target, *([] if config.parent else ['--allow-unrelated-histories'])]


def cmd_pull(ctx: CommandContext) -> None:
    """Pull upstream changes to the nested repo."""
    git, flags = ctx.git, ctx.flags
    subdir, gitnested, subref, config = setup.setup_command(git, 'pull', flags, ctx.subdir, ctx.upstream)

    if flags.force:
        config, up_to_date = clone.do_clone(git, flags, config, subdir, gitnested, subref, ctx.head)
        verb = "already up to date with" if up_to_date else "pulled from"
        output.say(f"{subdir.as_posix()}: {verb} {config.remote} ({config.branch})")
        return

    pulled = do_pull(git, flags, config, subdir, gitnested, ctx.tmp, subref)
    if pulled is None:
        output.say(f"{subdir.as_posix()}: already up to date with {config.remote} ({config.branch})")
        return

    branch, subdir_worktree = pulled
    output.verbose(f"committing the new {branch} content")
    content.commit_nested_branch(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        nested_commit_ref=branch,
        upstream_head_commit=git.check_output(['rev-parse', f'refs/nested/{subref}/fetch']),
        head_commit=ctx.head,
        subdir_worktree=subdir_worktree,
        command='pull',
    )
    output.say(f"{subdir.as_posix()}: pulled from {config.remote} ({config.branch})")
