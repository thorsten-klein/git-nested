"""Cloning an upstream repository into a subdirectory of this one."""

from __future__ import annotations

from pathlib import Path

from .. import content, discovery, gitfile, output, refs, submodules
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig
from . import fetch


def do_clone(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    head_commit: str | None,
) -> tuple[NestedConfig, bool]:
    """Clone upstream into subdir and commit it; with --force over an existing clone, reclone it.

    Returns:
        tuple: (config, up_to_date). up_to_date means a reclone found nothing new, and did nothing.
    """
    config, fetched, done, up_to_date = _prepare_clone_target(
        git, flags, config, subdir, gitnested, subref, head_commit
    )
    if done:
        return config, up_to_date

    _clone_into(git, flags, config, subdir, gitnested, subref, head_commit, fetched)
    return config, False


def _prepare_clone_target(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    head_commit: str | None,
) -> tuple[NestedConfig, str | None, bool, bool]:
    """Handle reclone/adopt/empty-target setup before a plain clone."""
    if flags.force and gitnested.is_file():
        return _prepare_reclone(git, flags, config, subdir, gitnested, subref)
    if flags.adopt:
        _adopt_existing_subdir(git, flags, config, subdir, gitnested, subref, head_commit)
        return config, None, True, False
    if subdir.exists() and any(subdir.iterdir()):
        raise GitNestedError(f"{subdir.as_posix()}: exists and is not empty")
    return config, None, False, False


def _prepare_reclone(
    git: GitRunner, flags: Flags, config: NestedConfig, subdir: Path, gitnested: Path, subref: str
) -> tuple[NestedConfig, str, bool, bool]:
    """Fetch the recorded clone again, stopping early when nothing changed."""
    fetched = fetch.do_fetch(git, config, subref)
    recorded = NestedConfig.from_file(gitnested)
    # A given URL wins over the recorded remote.
    given_remote = config.remote
    config = gitfile.read_config(gitnested, flags)
    config.remote = given_remote or config.remote
    output.verbose("checking whether it is already up to date")
    if _is_up_to_date(git, config, recorded, subdir, fetched):
        return config, fetched, True, True
    output.verbose("removing the existing subdir")
    git.run(['rm', '-r', '--', subdir])
    return config, fetched, False, False


def _is_up_to_date(git: GitRunner, config: NestedConfig, recorded: NestedConfig, subdir: Path, fetched: str) -> bool:
    """Whether a reclone would change nothing: same source, and the local content is upstream's."""
    # The same commit on another branch or remote is still a switch to record.
    same_source = (fetched, config.branch, config.remote) == (recorded.commit, recorded.branch, recorded.remote)
    return same_source and content.matches_upstream(git, subdir, fetched)


def _matching_upstream_commit(git: GitRunner, subdir: Path, upstream_head_commit: str) -> str:
    """The newest upstream commit whose root tree matches subdir at HEAD."""
    local_tree = git.check_output(['rev-parse', f'HEAD:{subdir.as_posix()}'])
    history = git.check_output(['log', '--format=%H %T', upstream_head_commit])
    for line in history.splitlines():
        commit, tree = line.split()
        if tree == local_tree:
            return commit
    raise GitNestedError(
        f"{subdir.as_posix()}: no upstream commit matches its current content; "
        "use 'git nested init -r <url> --commit <sha> <subdir>' if you know it"
    )


def _adopt_existing_subdir(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    head_commit: str | None,
) -> None:
    """Record the existing tracked content as a nested repository."""
    if flags.filter:
        raise GitNestedError("--adopt can't be used with --filter")
    if flags.recurse_submodules:
        raise GitNestedError("--adopt can't be used with --recurse-submodules")
    if not subdir.exists() or not any(subdir.iterdir()):
        raise GitNestedError(f"{subdir.as_posix()}: does not exist or is empty")
    if gitnested.exists():
        raise GitNestedError(f"{subdir.as_posix()}: is already a nested repository")
    if not git.is_tracked(subdir):
        raise GitNestedError(f"{subdir.as_posix()}: exists, but git tracks nothing in it")

    if not flags.branch:
        output.verbose("determining the upstream default branch")
        config.branch = discovery.get_upstream_branch(git, config)
    upstream_head_commit = fetch.do_fetch(git, config, subref)
    output.verbose("looking for a matching upstream commit")
    upstream_commit = _matching_upstream_commit(git, subdir, upstream_head_commit)
    gitfile.create_level_gitnested_files(git, subdir)
    output.verbose(f"writing {gitnested.as_posix()}")
    gitfile.update_gitrepo_file(
        git=git,
        flags=flags,
        config=config,
        gitnested=gitnested,
        upstream_head_commit=upstream_commit,
        nested_commit_ref=upstream_commit,
        head_commit=head_commit,
        command='clone',
    )
    msg = flags.message or discovery.build_commit_message(
        git, config, upstream_commit, upstream_commit, subdir, 'clone'
    )
    content.commit_gitnested_update(git, flags, subdir, msg)
    refs.create_nested_ref(git, refs.sanitize_subref(git, subdir.as_posix()), 'commit', upstream_commit)


def _clone_into(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    head_commit: str | None,
    fetched: str | None,
) -> None:
    """Commit the upstream branch's content into subdir, fetching it unless `fetched` already is it."""
    if not flags.branch:
        output.verbose("determining the upstream default branch")
        config.branch = discovery.get_upstream_branch(git, config)
        fetched = None  # whatever was fetched before was not that branch
    upstream_head_commit = fetched or fetch.do_fetch(git, config, subref)

    config.filter = flags.filter or config.filter
    config.exclude = flags.exclude or config.exclude
    config.path = flags.path or config.path
    _check_path(git, config, subdir, upstream_head_commit)
    output.verbose(f"creating {subdir.as_posix()}/")
    subdir.mkdir(parents=True, exist_ok=True)
    output.verbose(f"committing the new {subdir.as_posix()}/ content")
    content.commit_nested_branch(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        nested_commit_ref=upstream_head_commit,
        upstream_head_commit=upstream_head_commit,
        head_commit=head_commit,
        subdir_worktree=None,
        command='clone',
    )
    if flags.recurse_submodules:
        nest_submodules(git, flags, subdir, config.remote)
    else:
        submodules.warn_if_any(git, subdir)


def nest_submodules(git: GitRunner, flags: Flags, subdir: Path, remote: str, only: set[str] | None = None) -> None:
    """Turn each submodule under subdir into a nested repository, at the commit it pins.

    Each one is cloned with -b <commit>, so it stays at that commit. With
    `only`, just the submodules at those paths.
    """
    for path, pinned in submodules.gitlinks(git, subdir):
        if only is not None and path not in only:
            continue
        url = submodules.url_of(git, subdir / '.gitmodules', path.removeprefix(f'{subdir.as_posix()}/'), remote)
        if url is None:
            output.warn(f"{path}: .gitmodules has no url for it, so it stays empty")
            continue
        git.run(['rm', '-q', '--cached', '--', path])
        clone_at(git, flags, Path(path), url, pinned)


def clone_at(git: GitRunner, flags: Flags, subdir: Path, url: str, commit: str) -> None:
    """Clone `url` at `commit` into subdir, and its submodules too."""
    inner = Flags(branch=commit, recurse_submodules=True, quiet=flags.quiet, verbose=flags.verbose)
    subdir, gitnested, subref, config = setup.setup_command(git, 'clone', inner, subdir, url)
    do_clone(git, inner, config, subdir, gitnested, subref, git.check_output(['rev-parse', 'HEAD']))
    output.say(f"{subdir.as_posix()}: cloned from {url} ({commit})")


def _check_path(git: GitRunner, config: NestedConfig, subdir: Path, upstream: str) -> None:
    """Refuse a --path that upstream has no directory at, or one together with --filter."""
    if not config.path:
        return
    if config.filter:
        raise GitNestedError("--path and --filter can't be used together")
    if git.check_output(['cat-file', '-t', f'{upstream}:{config.path}'], may_fail=True) != 'tree':
        raise GitNestedError(f"{subdir.as_posix()}: upstream has no directory {config.path}")


def cmd_clone(ctx: CommandContext) -> None:
    """Clone a remote repository into a local subdirectory."""
    git = ctx.git
    subdir, gitnested, subref, config = setup.setup_command(git, 'clone', ctx.flags, ctx.subdir, ctx.upstream)
    config, up_to_date = do_clone(git, ctx.flags, config, subdir, gitnested, subref, ctx.head)
    if up_to_date:
        output.say(f"{subdir.as_posix()}: already up to date with {config.remote} ({config.branch})")
    elif ctx.flags.adopt:
        output.say(f"{subdir.as_posix()}: adopted from {config.remote} ({config.branch})")
    else:
        output.say(f"{subdir.as_posix()}: cloned from {config.remote} ({config.branch})")
