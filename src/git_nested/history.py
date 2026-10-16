"""Building the nested commit chain -- the algorithmic core."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from . import messages
from .constants import GIT_LOG_DATE_DEFAULT_FLAG, GITNESTED_FILENAME
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags, NestedConfig


def parent_is_ancestor(git: GitRunner, parent: str) -> bool:
    """Check whether the recorded parent is still part of HEAD's history."""
    return git.run(['merge-base', '--is-ancestor', parent, 'HEAD'], may_fail=True).returncode == 0


def _recorded_commit(git: GitRunner, rev: str, gitnested: Path) -> str | None:
    """The upstream commit gitnested records as of rev, or None if it records none there."""
    gitrepo_content = git.check_output(['cat-file', '-p', f'{rev}:{gitnested.as_posix()}'], may_fail=True)
    try:
        commit = (yaml.safe_load(gitrepo_content) or {}).get('nested', {}).get('commit')
    except yaml.YAMLError:
        return None
    return commit.strip() if commit else None


def find_sync_point(git: GitRunner, gitnested: Path) -> str | None:
    """The sync point HEAD's own history has for gitnested, or None if it has none.

    The newest commit that changed the recorded upstream commit is the one
    that brought the subdir in step with upstream: a pull or clone, or the
    rebased or squash-merged copy of one. The commit before it is what that
    pull would have written as the parent, had it been made on this history.
    """
    for rev in git.check_output(['log', '--format=%H', '--', gitnested]).splitlines():
        parents = git.check_output(['show', '-s', '--format=%P', rev]).split()
        parent = parents[0] if parents else None
        before = _recorded_commit(git, parent, gitnested) if parent else None
        if _recorded_commit(git, rev, gitnested) not in (None, before):
            # None for a root commit: it has nothing before it to hang off.
            return parent
    return None


def _check_rebase_safety(git: GitRunner, command: str, subref: str, gitrepo_commit: str) -> None:
    """Raise if a pull would silently accept a rewritten/unreachable upstream history."""
    refs_fetch = f'refs/nested/{subref}/fetch'
    if not (git.rev_exists(refs_fetch) and command == 'pull'):
        return
    if git.commit_in_rev_list(gitrepo_commit, refs_fetch):
        return
    if not git.rev_exists(gitrepo_commit):
        raise GitNestedError(
            f"upstream commit {gitrepo_commit} is missing locally; "
            f"run 'git nested fetch {subref}' or pass -F to take upstream as it is"
        )
    raise GitNestedError(
        f"upstream history was rewritten: {gitrepo_commit} is no longer part of it; "
        f"run 'git nested fetch {subref}' or pass -F to take upstream as it is"
    )


def _create_chain_commit(
    git: GitRunner, commit: str, subdir: Path, prev: str | None, upstream: str | None
) -> str | None:
    """Add the nested commit of `commit` on top of `prev`, joined to `upstream` if given.

    It is subdir's tree in `commit`, with that commit's author, committer and
    message. A commit without the subdir adds nothing, and `prev` stays the tip.

    Returns:
        the new tip of the chain
    """
    if git.run(['cat-file', '-e', f'{commit}:{subdir.as_posix()}'], may_fail=True).returncode != 0:
        return prev
    # Unstripped, so that even an empty message leaves the six lines before it intact.
    *identity, message = git.run([
        'log',
        '-1',
        GIT_LOG_DATE_DEFAULT_FLAG,
        '--format=%ad%n%ae%n%an%n%cd%n%ce%n%cn%n%B',
        commit,
    ]).stdout.split('\n', 6)
    names = ('AUTHOR_DATE', 'AUTHOR_EMAIL', 'AUTHOR_NAME', 'COMMITTER_DATE', 'COMMITTER_EMAIL', 'COMMITTER_NAME')
    env = {**os.environ, **{f'GIT_{name}': value for name, value in zip(names, identity, strict=True)}}
    parent_args = [arg for parent in (prev, upstream) if parent for arg in ('-p', parent)]
    return git.check_output(
        ['commit-tree', '-F', '-', *parent_args, f'{commit}:{subdir.as_posix()}'], input=message.strip(), env=env
    )


def _chain_commits(git: GitRunner, commits: list[str], gitnested: Path) -> list[tuple[str, str]]:
    """Those of `commits` that record an upstream commit, in the direct line of descent from the first.

    Returns:
        list: (commit, the upstream commit it records)
    """
    chain: list[tuple[str, str]] = []
    for commit in commits:
        upstream = _recorded_commit(git, commit, gitnested)
        if upstream and (not chain or chain[-1][0] in git.check_output(['show', '-s', '--format=%P', commit])):
            chain.append((commit, upstream))
    return chain


def _build_nested_commit_chain(
    git: GitRunner, flags: Flags, config: NestedConfig, commits: list[str], subdir: Path, subref: str, command: str
) -> tuple[str | None, str | None]:
    """Replay each of `commits` that records an upstream commit as a nested commit of subdir's content.

    A recorded upstream commit becomes the second parent of the nested commit
    that joins it: the first one always, and with the merge method every new
    one after it, which is what ties the nested history to upstream.

    Returns:
        tuple: (the last nested commit, the first upstream commit recorded)
    """
    chain = _chain_commits(git, commits, subdir / GITNESTED_FILENAME)
    merge = (flags.method or config.method) != 'rebase'
    prev = joined = None
    for commit, upstream in chain:
        _check_rebase_safety(git, command, subref, upstream)
        second_parent = upstream if upstream != joined and (merge or joined is None) else None
        joined = second_parent or joined
        prev = _create_chain_commit(git, commit, subdir, prev, second_parent)
    return prev, chain[0][1] if chain else None


def _create_branch_from_parent(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    command: str,
    branch: str,
) -> str | None:
    """Build branch by replaying subdir content across the parent..HEAD commit range.

    Returns:
        first_gitrepo_commit (or None), used to scope the later history filtering.
    """
    if not parent_is_ancestor(git, config.parent):
        raise GitNestedError(messages.sync_point_lost(gitnested, subdir))

    commits = git.check_output([
        'rev-list',
        '--reverse',
        '--ancestry-path',
        '--topo-order',
        f'{config.parent}..HEAD',
    ]).splitlines()
    prev_commit, first_gitrepo_commit = _build_nested_commit_chain(git, flags, config, commits, subdir, subref, command)
    if prev_commit is None:
        raise GitNestedError(
            f"{subdir.as_posix()}: no commit between {config.parent} and HEAD touches it, so there is no nested history to rebuild"
        )
    git.run(['branch', branch, prev_commit])
    return first_gitrepo_commit


def create_branch(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    command: str,
    branch: str,
) -> None:
    """Create `branch` holding the nested history of subdir, without its .gitnested file.

    From the recorded parent on when there is one; else the whole of HEAD's
    history, filtered down to the subdir.
    """
    first_gitrepo_commit = None
    if config.parent:
        first_gitrepo_commit = _create_branch_from_parent(
            git, flags, config, subdir, gitnested, subref, command, branch
        )
    else:
        git.run(['branch', branch, 'HEAD'])
        git.run(['filter-branch', '-f', '--subdirectory-filter', subref, branch], may_fail=True)

    filter_range = f'{first_gitrepo_commit}..{branch}' if first_gitrepo_commit else branch
    git.run(
        [
            'filter-branch',
            '-f',
            '--prune-empty',
            '--tree-filter',
            'rm -f .gitnested',
            '--',
            filter_range,
            '--first-parent',
        ],
        may_fail=True,
    )
