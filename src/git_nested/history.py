"""Building the nested commit chain -- the algorithmic core."""

from __future__ import annotations

import os
import re
import shlex
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

from . import messages, output
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


def _check_rebase_safety(git: GitRunner, command: str, subdir: Path, subref: str, gitrepo_commit: str) -> None:
    """Raise if a pull would silently accept a rewritten/unreachable upstream history."""
    refs_fetch = f'refs/nested/{subref}/fetch'
    if not (git.rev_exists(refs_fetch) and command == 'pull'):
        return
    if git.commit_in_rev_list(gitrepo_commit, refs_fetch):
        return
    problem = (
        f"upstream commit {gitrepo_commit} is missing locally"
        if not git.rev_exists(gitrepo_commit)
        else f"upstream history was rewritten: {gitrepo_commit} is no longer part of it"
    )
    raise GitNestedError(
        f"{problem}; run 'git nested pull --force {subdir.as_posix()}' to take upstream as it is. "
        "This drops local changes that are not pushed."
    )


def _create_chain_commit(git: GitRunner, commit: str, tree: str, parents: list[str]) -> str:
    """A nested commit of `tree`, with the author, committer and message of `commit`."""
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
    parent_args = [arg for parent in parents for arg in ('-p', parent)]
    return git.check_output(['commit-tree', '-F', '-', *parent_args, tree], input=message.strip(), env=env)


@dataclass
class _Replay:
    """Replays commits of this repository as nested commits of one subdir.

    `nested` maps each commit to its nested commit. A commit that adds
    nothing maps to the nested commit it would sit on.
    """

    git: GitRunner
    subdir: Path
    subref: str
    command: str
    merge: bool
    index_env: dict[str, str]
    removed: list[str]
    nested: dict[str, str] = field(default_factory=dict)
    joined: dict[str, str | None] = field(default_factory=dict)
    trees: dict[str, str] = field(default_factory=dict)

    def add(self, commit: str, parents: list[str]) -> None:
        """Replay one commit, whose `parents` came before it."""
        known = [parent for parent in parents if parent in self.nested]
        last = self.joined.get(known[0]) if known else None
        upstream = _recorded_commit(self.git, commit, self.subdir / GITNESTED_FILENAME)
        if not upstream:
            # No .gitnested here: the history passes through.
            if known:
                self.nested[commit], self.joined[commit] = self.nested[known[0]], last
            return
        _check_rebase_safety(self.git, self.command, self.subdir, self.subref, upstream)
        # An upstream commit joins the first time, and with merge each time a new one is recorded.
        joins = upstream != last if self.merge else not known
        self.joined[commit] = upstream if joins else last
        nested_parents = [*dict.fromkeys(self.nested[parent] for parent in known), *([upstream] if joins else [])]
        self.nested[commit] = self._commit(commit, self._independent(nested_parents))

    def _commit(self, commit: str, parents: list[str]) -> str:
        """The nested commit of `commit` on `parents`; the one parent itself if nothing changes."""
        tree = self._subdir_tree(commit)
        if len(parents) == 1 and tree == self._tree_of(parents[0]):
            return parents[0]
        nested = _create_chain_commit(self.git, commit, tree, parents)
        self.trees[nested] = tree
        return nested

    def _independent(self, commits: list[str]) -> list[str]:
        """`commits` without those that are ancestors of another one."""
        if len(commits) < 2:
            return commits
        independent = self.git.check_output(['merge-base', '--independent', *commits]).split()
        return [commit for commit in commits if commit in independent]

    def _tree_of(self, commit: str) -> str:
        if commit not in self.trees:
            self.trees[commit] = self.git.check_output(['rev-parse', f'{commit}^{{tree}}'])
        return self.trees[commit]

    def _subdir_tree(self, commit: str) -> str:
        """The tree of subdir in `commit`, without the `removed` paths."""
        self.git.run(['read-tree', f'{commit}:{self.subdir.as_posix()}'], env=self.index_env)
        # -f: this index has nothing to do with the working tree
        self.git.run(['rm', '--cached', '-r', '-q', '-f', '--ignore-unmatch', '--', *self.removed], env=self.index_env)
        return self.git.check_output(['write-tree'], env=self.index_env)


def _usable_parent(git: GitRunner, parent: str, gitnested: Path, subdir: Path) -> str:
    """The recorded parent; if it is no longer in HEAD's history, the sync point found there.

    A rebase or a squash merge leaves the recorded one behind.
    """
    if parent_is_ancestor(git, parent):
        return parent
    found = find_sync_point(git, gitnested)
    if found is None:
        raise GitNestedError(messages.sync_point_lost(gitnested, subdir))
    output.warn(
        f"{subdir.as_posix()}: the recorded sync point is not in this history; using {found[:9]} instead. "
        f"'git nested repair {subdir.as_posix()}' records it"
    )
    return found


def _create_branch_from_parent(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    command: str,
    branch: str,
    removed: list[str],
) -> None:
    """Build branch by replaying the commits from the recorded parent to HEAD.

    Merges stay merges where both sides changed the subdir. So a change
    that came in through a merge keeps its own commit and message.
    """
    parent = _usable_parent(git, config.parent, gitnested, subdir)
    lines = git.check_output([
        'rev-list',
        '--reverse',
        '--topo-order',
        '--ancestry-path',
        '--parents',
        f'{parent}..HEAD',
    ]).splitlines()
    with tempfile.TemporaryDirectory() as tmp:
        merge = (flags.method or config.method) != 'rebase'
        index_env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        replay = _Replay(git, subdir, subref, command, merge, index_env, removed)
        for line in lines:
            commit, *parents = line.split()
            replay.add(commit, parents)
    tip = replay.nested.get(lines[-1].split()[0]) if lines else None
    if tip is None:
        raise GitNestedError(
            f"{subdir.as_posix()}: no commit between {parent} and HEAD touches it, so there is no nested history to rebuild"
        )
    git.run(['branch', branch, tip])


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
    history, filtered down to the subdir. For a push it also leaves out what
    upstream must not get.
    """
    removed = [GITNESTED_FILENAME, *(_local_only_paths(git, config, subdir) if command == 'push' else [])]
    if config.parent:
        _create_branch_from_parent(git, flags, config, subdir, gitnested, subref, command, branch, removed)
        return
    git.run(['branch', branch, 'HEAD'])
    git.run(['filter-branch', '-f', '--subdirectory-filter', subref, branch], may_fail=True)
    tree_filter = 'rm -rf -- ' + ' '.join(shlex.quote(path) for path in removed)
    git.run(
        ['filter-branch', '-f', '--prune-empty', '--tree-filter', tree_filter, '--', branch, '--first-parent'],
        may_fail=True,
    )


def _local_only_paths(git: GitRunner, config: NestedConfig, subdir: Path) -> list[str]:
    """The paths in subdir that upstream must not get, relative to subdir.

    These are the .gitnested.levelN files, and the nested repositories added
    in this repository. A nested repository that upstream has stays.
    """
    paths = []
    prefix = f'{subdir.as_posix()}/'
    for path in git.check_output(['ls-tree', '-r', '-z', '--name-only', 'HEAD', '--', subdir]).split('\0'):
        relative = PurePosixPath(path.removeprefix(prefix))
        if re.fullmatch(r'\.gitnested\.level\d+', relative.name):
            paths.append(relative.as_posix())
        elif relative.name == GITNESTED_FILENAME and relative.parent.name and not _upstream_has(git, config, relative):
            paths.append(relative.parent.as_posix())
    return paths


def _upstream_has(git: GitRunner, config: NestedConfig, path: PurePosixPath) -> bool:
    """Whether the recorded upstream commit has `path`."""
    return bool(config.commit) and git.run(['cat-file', '-e', f'{config.commit}:{path}'], may_fail=True).returncode == 0
