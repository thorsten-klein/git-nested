"""Building the nested commit chain -- the algorithmic core."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from . import messages
from .constants import GIT_LOG_DATE_DEFAULT_FLAG
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags, NestedConfig


def _check_parent_is_ancestor(git: GitRunner, config: NestedConfig, gitnested: Path, subdir: Path) -> None:
    """Raise a recovery-hint error unless config.parent is an ancestor of HEAD."""
    result = git.run(['merge-base', '--is-ancestor', config.parent, 'HEAD'], may_fail=True)
    if result.returncode == 0:
        return
    prev = git.check_output(['log', '-1', '-G', 'commit =', '--format=%H', gitnested], may_fail=True)
    if prev:
        prev = git.check_output(['log', '-1', '--format=%H', f'{prev.strip()}^'])
    raise GitNestedError(messages.sync_point_lost(gitnested, subdir, prev))


def _extract_gitrepo_commit(git: GitRunner, commit: str, subdir: Path) -> str | None:
    """Extract the recorded nested commit from commit's .gitnested file, or None."""
    gitrepo_content = git.check_output(['cat-file', '-p', f'{commit}:{subdir}/.gitnested'], may_fail=True)
    if not gitrepo_content:
        return None
    try:
        gitrepo_data = yaml.safe_load(gitrepo_content) or {}
        gitrepo_commit = gitrepo_data.get('nested', {}).get('commit', '')
    except yaml.YAMLError:
        return None
    if not gitrepo_commit:
        return None
    return gitrepo_commit.strip()


def _is_direct_child(git: GitRunner, ancestor: str | None, commit: str) -> bool:
    """Check whether commit is a direct child of ancestor (always true if there's no ancestor yet)."""
    if not ancestor:
        return True
    parents = git.check_output(['show', '-s', '--pretty=format:%P', commit])
    return ancestor in parents


def _check_rebase_safety(git: GitRunner, command: str, subref: str, gitrepo_commit: str) -> None:
    """Raise if a pull would silently accept a rewritten/unreachable upstream history."""
    refs_fetch = f'refs/nested/{subref}/fetch'
    if not (git.rev_exists(refs_fetch) and command == 'pull'):
        return
    result = git.run(['merge-base', '--is-ancestor', gitrepo_commit, refs_fetch], may_fail=True)
    if result.returncode == 0:
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


def _compute_second_parent(flags: Flags, config: NestedConfig, gitrepo_commit: str, state: dict) -> list[str]:
    """Compute the commit-tree second parent, tracking the first/last gitrepo commit seen."""
    second_parent: list[str] = []
    if not state['first_gitrepo_commit']:
        state['first_gitrepo_commit'] = gitrepo_commit
        second_parent = ['-p', gitrepo_commit]

    method = flags.method or config.method
    if method != 'rebase' and gitrepo_commit != state['last_gitrepo_commit']:
        second_parent = ['-p', gitrepo_commit]
        state['last_gitrepo_commit'] = gitrepo_commit

    return second_parent


def _commit_has_subdir_content(git: GitRunner, commit: str, subdir: Path) -> bool:
    """Check whether commit has content under subdir/."""
    result = git.run(['cat-file', '-e', f'{commit}:{subdir}'], may_fail=True)
    return result.returncode == 0


def _create_chain_commit(
    git: GitRunner, commit: str, subdir: Path, first_parent: list[str], second_parent: list[str]
) -> str:
    """Create one nested commit-tree entry, preserving the original author/committer/date."""
    author_date = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%ad', commit])
    author_email = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%ae', commit])
    author_name = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%an', commit])
    committer_date = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%cd', commit])
    committer_email = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%ce', commit])
    committer_name = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%cn', commit])
    commit_msg = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%B', commit])

    # Set author and committer info for deterministic commits
    env = os.environ.copy()
    env.update({
        'GIT_AUTHOR_DATE': author_date,
        'GIT_AUTHOR_EMAIL': author_email,
        'GIT_AUTHOR_NAME': author_name,
        'GIT_COMMITTER_DATE': committer_date,
        'GIT_COMMITTER_EMAIL': committer_email,
        'GIT_COMMITTER_NAME': committer_name,
    })

    tree_cmd = ['commit-tree', '-F', '-', *first_parent, *second_parent, f'{commit}:{subdir}']
    return git.check_output(tree_cmd, input=commit_msg, env=env)


def _process_chain_commit(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    subref: str,
    command: str,
    commit: str,
    state: dict,
) -> None:
    """Process one commit into the nested commit chain, updating state in place."""
    gitrepo_commit = _extract_gitrepo_commit(git, commit, subdir)
    if not gitrepo_commit:
        return

    if not _is_direct_child(git, state['ancestor'], commit):
        return
    state['ancestor'] = commit

    _check_rebase_safety(git, command, subref, gitrepo_commit)

    first_parent: list[str] = ['-p', state['prev_commit']] if state['prev_commit'] else []
    second_parent = _compute_second_parent(flags, config, gitrepo_commit, state)

    if _commit_has_subdir_content(git, commit, subdir):
        state['prev_commit'] = _create_chain_commit(git, commit, subdir, first_parent, second_parent)


def _build_nested_commit_chain(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    commits: list[str],
    subdir: Path,
    subref: str,
    command: str,
) -> tuple[str | None, str | None]:
    """Walk commits and build the nested commit chain.

    Returns:
        tuple: (prev_commit, first_gitrepo_commit)
    """
    state = {'ancestor': None, 'first_gitrepo_commit': None, 'last_gitrepo_commit': None, 'prev_commit': None}
    for commit in commits:
        _process_chain_commit(git, flags, config, subdir, subref, command, commit, state)
    return state['prev_commit'], state['first_gitrepo_commit']


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
    _check_parent_is_ancestor(git, config, gitnested, subdir)

    commits = git.check_output([
        'rev-list',
        '--reverse',
        '--ancestry-path',
        '--topo-order',
        f'{config.parent}..HEAD',
    ]).splitlines()

    prev_commit, first_gitrepo_commit = _build_nested_commit_chain(git, flags, config, commits, subdir, subref, command)

    if prev_commit is None:
        # No commit in the parent..HEAD range ever touched subdir, so the
        # chain builder above never had content to build a nested commit from.
        raise GitNestedError(
            f"{subdir}: no commit between {config.parent} and HEAD touches it, so there is no nested history to rebuild"
        )
    git.run(['branch', branch, prev_commit])
    return first_gitrepo_commit


def _create_branch_without_parent(git: GitRunner, subref: str, branch: str) -> None:
    """Build branch by taking the full HEAD history and filtering it down to subdir/."""
    git.run(['branch', branch, 'HEAD'])
    git.run(['filter-branch', '-f', '--subdirectory-filter', subref, branch], may_fail=True)


def _filter_branch_history(git: GitRunner, branch: str, first_gitrepo_commit: str | None) -> None:
    """Strip the .gitnested file from branch's history."""
    filter_range = f'{first_gitrepo_commit}..{branch}' if first_gitrepo_commit else branch
    git.check_output(
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
