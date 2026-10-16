"""Cloning an upstream repository into a subdirectory of this one."""

from __future__ import annotations

from pathlib import Path

from .. import content, discovery, gitfile, output, submodules
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
    head_commit: str,
) -> tuple[NestedConfig, bool]:
    """Clone upstream into subdir and commit it; with --force over an existing clone, reclone it.

    Returns:
        tuple: (config, up_to_date). up_to_date means a reclone found nothing new, and did nothing.
    """
    if not git.rev_exists('HEAD'):
        raise GitNestedError("can't clone into a repository that has no commits yet")

    fetched = None
    if flags.force and gitnested.is_file():
        fetched = fetch.do_fetch(git, config, subref)
        recorded = NestedConfig.from_file(gitnested)
        # A given URL wins over the recorded remote.
        given_remote = config.remote
        config = gitfile.read_config(gitnested, flags)
        config.remote = given_remote or config.remote
        output.verbose("checking whether it is already up to date")
        if _is_up_to_date(git, config, recorded, subdir, fetched):
            return config, True
        output.verbose("removing the existing subdir")
        git.run(['rm', '-r', '--', subdir])
    elif subdir.exists() and any(subdir.iterdir()):
        raise GitNestedError(f"{subdir.as_posix()}: exists and is not empty")

    _clone_into(git, flags, config, subdir, gitnested, subref, head_commit, fetched)
    return config, False


def _is_up_to_date(git: GitRunner, config: NestedConfig, recorded: NestedConfig, subdir: Path, fetched: str) -> bool:
    """Whether a reclone would change nothing: same source, and the local content is upstream's."""
    # The same commit on another branch or remote is still a switch to record.
    same_source = (fetched, config.branch, config.remote) == (recorded.commit, recorded.branch, recorded.remote)
    return same_source and content.matches_upstream(git, subdir, fetched)


def _clone_into(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    head_commit: str,
    fetched: str | None,
) -> None:
    """Commit the upstream branch's content into subdir, fetching it unless `fetched` already is it."""
    if not flags.branch:
        output.verbose("determining the upstream default branch")
        config.branch = discovery.get_upstream_branch(git, config)
        fetched = None  # whatever was fetched before was not that branch
    upstream_head_commit = fetched or fetch.do_fetch(git, config, subref)

    config.filter = flags.filter or config.filter
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


def nest_submodules(git: GitRunner, flags: Flags, subdir: Path, remote: str) -> None:
    """Turn each submodule under subdir into a nested repository, at the commit it pins.

    Each one is cloned with -b <commit>, so it stays at that commit.
    """
    for path, pinned in submodules.gitlinks(git, subdir):
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


def cmd_clone(ctx: CommandContext) -> None:
    """Clone a remote repository into a local subdirectory."""
    git = ctx.git
    subdir, gitnested, subref, config = setup.setup_command(git, 'clone', ctx.flags, ctx.subdir, ctx.upstream)
    config, up_to_date = do_clone(git, ctx.flags, config, subdir, gitnested, subref, ctx.head)
    if up_to_date:
        output.say(f"{subdir.as_posix()}: already up to date with {config.remote} ({config.branch})")
    else:
        output.say(f"{subdir.as_posix()}: cloned from {config.remote} ({config.branch})")
