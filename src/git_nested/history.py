"""Building the nested commit chain -- the algorithmic core."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import configio, filters, messages, output
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
        commit = configio.parse(gitrepo_content).get('nested', {}).get('commit')
    except GitNestedError:
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


def _check_rebase_safety(
    git: GitRunner, command: str, subdir: Path, subref: str, gitrepo_commit: str, rebase: bool
) -> None:
    """Raise if a pull would silently accept a rewritten/unreachable upstream history.

    With the rebase method a rewritten upstream is fine: the pull rebases
    the local commits onto it.
    """
    refs_fetch = f'refs/nested/{subref}/fetch'
    if not (git.rev_exists(refs_fetch) and command == 'pull'):
        return
    if git.commit_in_rev_list(gitrepo_commit, refs_fetch):
        return
    force = f"run 'git nested pull --force {subdir.as_posix()}' to take upstream as it is. This drops local changes that are not pushed."
    if not git.rev_exists(gitrepo_commit):
        raise GitNestedError(f"upstream commit {gitrepo_commit} is missing locally; {force}")
    if rebase:
        return
    raise GitNestedError(
        f"upstream history was rewritten: {gitrepo_commit} is no longer part of it; {force} "
        f"Or run 'git nested pull -M rebase {subdir.as_posix()}' to rebase your local changes onto it."
    )


def _create_chain_commit(git: GitRunner, commit: str, tree: str, parents: list[str], sign: bool) -> str:
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
    sign_args = ['-S'] if sign else []
    return git.check_output(['commit-tree', *sign_args, '-F', '-', *parent_args, tree], input=message.strip(), env=env)


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
    sign: bool = False
    gitlinked: tuple[str, ...] = ()
    keep: tuple[list[str], list[str]] | None = None
    path: str = ''
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
        _check_rebase_safety(self.git, self.command, self.subdir, self.subref, upstream, rebase=not self.merge)
        # An upstream commit joins the first time, and with merge each time a new one is recorded.
        joins = upstream != last if self.merge else not known
        self.joined[commit] = upstream if joins else last
        nested_parents = [*dict.fromkeys(self.nested[parent] for parent in known), *([upstream] if joins else [])]
        self.nested[commit] = self._commit(commit, self._independent(nested_parents))

    def add_plain(self, commit: str, parents: list[str]) -> None:
        """Replay one commit as it is, with no upstream commit to join."""
        nested_parents = self._independent([*dict.fromkeys(self.nested[p] for p in parents if p in self.nested)])
        if self.git.run(['cat-file', '-e', f'{commit}:{self.subdir.as_posix()}'], may_fail=True).returncode != 0:
            # The subdir is gone here: the history passes through.
            if nested_parents:
                self.nested[commit] = nested_parents[0]
            return
        self.nested[commit] = self._commit(commit, nested_parents)

    def _upstream_with_room(self, commit: str) -> None:
        """Load the upstream tree `commit` records, without the directory subdir stands for."""
        upstream = _recorded_commit(self.git, commit, self.subdir / GITNESTED_FILENAME)
        self.git.run(['read-tree', upstream or '--empty'], env=self.index_env)
        self.git.run(['rm', '--cached', '-r', '-q', '-f', '--ignore-unmatch', '--', self.path], env=self.index_env)

    def _commit(self, commit: str, parents: list[str]) -> str:
        """The nested commit of `commit` on `parents`; the one parent itself if nothing changes."""
        tree = self._subdir_tree(commit)
        if len(parents) == 1 and tree == self._tree_of(parents[0]):
            return parents[0]
        nested = _create_chain_commit(self.git, commit, tree, parents, self.sign)
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
        """The tree of subdir in `commit`, without the `removed` paths.

        With a path, it is upstream's tree with that directory taken from subdir.
        """
        prefix = f'{self.path}/' if self.path else ''
        local = f'{commit}:{self.subdir.as_posix()}'
        if self.path:
            self._upstream_with_room(commit)
            self.git.run(['read-tree', f'--prefix={prefix}', local], env=self.index_env)
        else:
            self.git.run(['read-tree', local], env=self.index_env)
        removed = [f'{prefix}{path}' for path in self.removed]
        # -f: this index has nothing to do with the working tree
        self.git.run(['rm', '--cached', '-r', '-q', '-f', '--ignore-unmatch', '--', *removed], env=self.index_env)
        for path in self.gitlinked:
            self._as_gitlink(commit, path, prefix)
        if self.keep:
            self._keep_unmanaged(commit, *self.keep)
        return self.git.check_output(['write-tree'], env=self.index_env)

    def _as_gitlink(self, commit: str, path: str, prefix: str) -> None:
        """Put the inner nested repository at `path` back as the submodule it came from.

        Its gitlink pins the commit its .gitnested records in `commit`. In
        the index it sits under `prefix`.
        """
        pinned = _recorded_commit(self.git, commit, self.subdir / path / GITNESTED_FILENAME)
        if pinned:
            entry = f'{prefix}{path}'
            self.git.run(['rm', '--cached', '-r', '-q', '-f', '--ignore-unmatch', '--', entry], env=self.index_env)
            self.git.run(['update-index', '--add', '--cacheinfo', f'160000,{pinned},{entry}'], env=self.index_env)

    def _keep_unmanaged(self, commit: str, entries: list[str], exclude: list[str]) -> None:
        """Put back the upstream files git-nested does not manage, so a push does not delete them.

        They come from the upstream commit `commit` records.
        """
        upstream = _recorded_commit(self.git, commit, self.subdir / GITNESTED_FILENAME)
        if upstream:
            _, rest = filters.split(self.git, upstream, entries, exclude)
            info = ''.join(f'{line}\0' for line in rest)
            self.git.run(['update-index', '-z', '--index-info'], env=self.index_env, input=info)


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


def _replay_into_branch(replay: _Replay, rev_list: list[str], branch: str, plain: bool) -> bool:
    """Replay the commits `rev_list` lists, oldest first, into `branch`.

    Returns:
        False if none of them touched the subdir, so there is no branch.
    """
    git = replay.git
    lines = git.check_output(['rev-list', '--reverse', '--topo-order', '--parents', *rev_list]).splitlines()
    add = replay.add_plain if plain else replay.add
    for done, line in enumerate(lines, 1):
        commit, *parents = line.split()
        add(commit, parents)
        output.progress(f'{replay.subdir.as_posix()}: rebuilding the nested history', done, len(lines))
    tip = replay.nested.get(lines[-1].split()[0]) if lines else None
    if tip is None:
        return False
    git.run(['branch', branch, tip])
    return True


def _unmanaged_to_keep(config: NestedConfig, command: str) -> tuple[list[str], list[str]] | None:
    """For a push with a filter or excludes: (filter, exclude), so it gives back what git-nested does not manage."""
    if command != 'push' or not (config.filter or config.exclude):
        return None
    return config.filter or [], config.exclude or []


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

    From the recorded parent on when there is one. Merges stay merges where
    both sides changed the subdir, so a change that came in through a merge
    keeps its own commit and message. Without a parent, every commit of HEAD
    that touched the subdir is replayed. For a push it also leaves out what
    upstream must not get.
    """
    parent = _usable_parent(git, config.parent, gitnested, subdir) if config.parent else ''
    gitlinked = gitlinked_inner(git, config, subdir)
    local_only = _local_only_paths(git, config, subdir, gitlinked) if command == 'push' else []
    removed = [GITNESTED_FILENAME, *local_only]
    merge = (flags.method or config.method) != 'rebase'
    with tempfile.TemporaryDirectory() as tmp:
        index_env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        keep = _unmanaged_to_keep(config, command)
        replay = _Replay(
            git,
            subdir,
            subref,
            command,
            merge,
            index_env,
            removed,
            flags.gpg_sign,
            gitlinked,
            keep=keep,
            path=config.path,
        )
        if parent:
            built = _replay_into_branch(replay, ['--ancestry-path', f'{parent}..HEAD'], branch, plain=False)
        else:
            # Path limited: only the commits that touch subdir, with their parents rewritten
            built = _replay_into_branch(replay, ['HEAD', '--', subdir.as_posix()], branch, plain=True)
    if not built:
        since = f" between {parent} and HEAD" if parent else ""
        raise GitNestedError(
            f"{subdir.as_posix()}: no commit{since} touches it, so there is no nested history to rebuild"
        )


def gitlinked_inner(git: GitRunner, config: NestedConfig, subdir: Path) -> tuple[str, ...]:
    """The inner nested repositories that are submodules in the recorded upstream commit, relative to subdir."""
    if not config.commit:
        return ()
    prefix = f'{subdir.as_posix()}/'
    inner = [
        PurePosixPath(path.removeprefix(prefix)).parent.as_posix()
        for path in git.check_output(['ls-tree', '-r', '-z', '--name-only', 'HEAD', '--', subdir]).split('\0')
        if PurePosixPath(path).name == GITNESTED_FILENAME and path != f'{prefix}{GITNESTED_FILENAME}'
    ]
    return tuple(
        path
        for path in inner
        if git.check_output(['ls-tree', config.commit, '--', path], may_fail=True).startswith('160000 ')
    )


def _local_only_paths(git: GitRunner, config: NestedConfig, subdir: Path, gitlinked: tuple[str, ...]) -> list[str]:
    """The paths in subdir that upstream must not get, relative to subdir.

    These are the .gitnested.levelN files, and the nested repositories added
    in this repository. A nested repository that upstream has stays, also as
    a submodule.
    """
    paths = []
    prefix = f'{subdir.as_posix()}/'
    for path in git.check_output(['ls-tree', '-r', '-z', '--name-only', 'HEAD', '--', subdir]).split('\0'):
        relative = PurePosixPath(path.removeprefix(prefix))
        if re.fullmatch(r'\.gitnested\.level\d+', relative.name):
            paths.append(relative.as_posix())
        elif (
            relative.name == GITNESTED_FILENAME
            and relative.parent.name
            and relative.parent.as_posix() not in gitlinked
            and not _upstream_has(git, config, relative)
        ):
            paths.append(relative.parent.as_posix())
    return paths


def _upstream_has(git: GitRunner, config: NestedConfig, path: PurePosixPath) -> bool:
    """Whether the recorded upstream commit has `path`."""
    return bool(config.commit) and git.run(['cat-file', '-e', f'{config.commit}:{path}'], may_fail=True).returncode == 0
