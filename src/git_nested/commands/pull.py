"""Pulling upstream changes into a nested subdirectory."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from .. import content, discovery, filters, gitfile, history, messages, output, refs, submodules, worktree
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

    merge_target = _merge_target(git, config, subdir_worktree, subref, upstream_head_commit)

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


def _merge_target(git: GitRunner, config: NestedConfig, worktree_dir: Path, subref: str, upstream: str) -> str:
    """What the nested branch is merged with: upstream, or the part of it git-nested manages.

    The nested branch only ever held that part. A merge of all of upstream
    would see every file left out as deleted locally, and conflict wherever
    upstream touched one.
    """
    if not (config.filter or config.exclude):
        return f'refs/nested/{subref}/fetch'
    return filters.build_filtered_commit(git, worktree_dir, config.filter or [], config.exclude or [], upstream)


def _prefixed_tree(git: GitRunner, commit: str, subdir: Path, index_env: dict[str, str]) -> str:
    """The tree of `commit`, rewritten under `subdir/`."""
    git.run(['read-tree', '--empty'], env=index_env)
    git.run(['read-tree', f'--prefix={subdir.as_posix()}', f'{commit}^{{tree}}'], env=index_env)
    return git.check_output(['write-tree'], env=index_env)


def _rewrite_history_with_prefix(
    git: GitRunner, flags: Flags, nested_commit_ref: str, subdir: Path, git_tmp: Path, subref: str
) -> str:
    """Replay `nested_commit_ref` as commits whose trees live under `subdir/`."""
    scratch = git_tmp / '.pull-no-squash' / f'{refs.sanitize_subref(git, subref)}-{uuid4().hex}'
    scratch.mkdir(parents=True, exist_ok=True)
    index_env = {**os.environ, 'GIT_INDEX_FILE': str(scratch / 'index')}
    rewritten: dict[str, str] = {}
    tip = ''
    try:
        for line in git.check_output([
            'rev-list',
            '--reverse',
            '--topo-order',
            '--parents',
            nested_commit_ref,
        ]).splitlines():
            commit, *parents = line.split()
            tree = _prefixed_tree(git, commit, subdir, index_env)
            rewritten[commit] = history._create_chain_commit(
                git, commit, tree, [rewritten[parent] for parent in parents], flags.gpg_sign
            )
            tip = rewritten[commit]
        return tip
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _commit_without_squash(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    nested_commit_ref: str,
    upstream_head_commit: str,
    head_commit: str,
    subdir_worktree: Path,
    git_tmp: Path,
    subref: str,
) -> None:
    """Commit the pull as a merge commit, keeping the nested history as the second parent."""
    rewritten = _rewrite_history_with_prefix(git, flags, nested_commit_ref, subdir, git_tmp, subref)
    git.run(['merge', '--no-commit', '--no-ff', '-s', 'ours', '--allow-unrelated-histories', rewritten])
    content._place_content(git, config, subdir, nested_commit_ref)
    gitfile.create_level_gitnested_files(git, subdir)

    regular = gitnested.parent / '.gitnested'
    for path in [gitnested] + ([regular] if regular != gitnested and regular.exists() else []):
        output.verbose(f"writing {path.as_posix()}")
        gitfile.update_gitrepo_file(
            git=git,
            flags=flags,
            config=config,
            gitnested=path,
            upstream_head_commit=upstream_head_commit,
            nested_commit_ref=nested_commit_ref,
            head_commit=head_commit,
            command='pull',
        )

    msg = flags.message or discovery.build_commit_message(
        git, config, upstream_head_commit, nested_commit_ref, subdir, 'pull'
    )
    content.commit_gitnested_update(git, flags, subdir, msg)
    worktree.remove_worktree(git, subdir_worktree)
    refs.create_nested_ref(git, subref, 'commit', nested_commit_ref)


def _commit_pull(
    ctx: CommandContext,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    branch: str,
    subdir_worktree: Path,
) -> None:
    """Commit the pulled nested branch: squashed, or with upstream's history kept."""
    upstream_head_commit = ctx.git.check_output(['rev-parse', f'refs/nested/{subref}/fetch'])
    if ctx.flags.no_squash or (not config.squash and upstream_head_commit != config.commit):
        _commit_without_squash(
            git=ctx.git,
            flags=ctx.flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            nested_commit_ref=branch,
            upstream_head_commit=upstream_head_commit,
            head_commit=ctx.head,
            subdir_worktree=subdir_worktree,
            git_tmp=ctx.tmp,
            subref=subref,
        )
    else:
        content.commit_nested_branch(
            git=ctx.git,
            flags=ctx.flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            nested_commit_ref=branch,
            upstream_head_commit=upstream_head_commit,
            head_commit=ctx.head,
            subdir_worktree=subdir_worktree,
            command='pull',
        )


def _check_no_squash(flags: Flags, config: NestedConfig, subdir: Path) -> None:
    """Refuse to keep upstream's history when only a part of upstream is nested.

    Its commits would bring in the files that are left out.
    """
    if (flags.no_squash or not config.squash) and (config.filter or config.exclude or config.path):
        raise GitNestedError(
            f"{subdir.as_posix()}: --no-squash can't keep the history of a part of upstream; "
            "it does not work with --filter, --exclude or --path"
        )


def cmd_pull(ctx: CommandContext) -> None:
    """Pull upstream changes to the nested repo."""
    git, flags = ctx.git, ctx.flags
    subdir, gitnested, subref, config = setup.setup_command(git, 'pull', flags, ctx.subdir, ctx.upstream)
    _check_no_squash(flags, config, subdir)

    if flags.force:
        config, up_to_date = clone.do_clone(git, flags, config, subdir, gitnested, subref, ctx.head)
        verb = "already up to date with" if up_to_date else "pulled from"
        output.say(f"{subdir.as_posix()}: {verb} {config.remote} ({config.branch})")
        return

    # Submodules of upstream that are nested now stay nested, at the commit upstream pins after the pull
    nested_before = {f'{subdir.as_posix()}/{path}' for path in history.gitlinked_inner(git, config, subdir)}
    pulled = do_pull(git, flags, config, subdir, gitnested, ctx.tmp, subref)
    if pulled is None:
        output.say(f"{subdir.as_posix()}: already up to date with {config.remote} ({config.branch})")
        return

    branch, subdir_worktree = pulled
    output.verbose(f"committing the new {branch} content")
    _commit_pull(ctx, config, subdir, gitnested, subref, branch, subdir_worktree)
    clone.nest_submodules(git, flags, subdir, config.remote, None if flags.recurse_submodules else nested_before)
    submodules.warn_if_any(git, subdir)
    output.say(f"{subdir.as_posix()}: pulled from {config.remote} ({config.branch})")
