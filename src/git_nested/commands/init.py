"""Turning an existing subdirectory into a nested repository."""

from __future__ import annotations

from pathlib import Path

from .. import content, discovery, gitfile, output, refs, submodules
from .._compat import rmtree
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig
from . import clone, fetch

# Where this repository lists its submodules
_GITMODULES = Path('.gitmodules')


def _init_from_submodule(git: GitRunner, flags: Flags, subdir: Path) -> None:
    """Replace the submodule at subdir by a nested repository, at the same commit and url."""
    path = subdir.as_posix()
    found = submodules.entry(git, _GITMODULES, path)
    link = git.check_output(['ls-tree', 'HEAD', '--', path]).split()
    if found is None or link[:1] != ['160000']:
        raise GitNestedError(f"{path}: is not a submodule")
    name, url = found
    pinned = link[2]
    # A relative url is relative to this repository's own remote.
    url = submodules.resolve(url, git.check_output(['remote', 'get-url', 'origin'], may_fail=True))

    output.verbose(f"removing the submodule {name}")
    git.run(['submodule', 'deinit', '-q', '-f', '--', path], may_fail=True)
    git.run(['rm', '-q', '-f', '--', path])
    if not _GITMODULES.read_text().strip():
        git.run(['rm', '-q', '-f', '--', _GITMODULES])
    rmtree(Path(git.check_output(['rev-parse', '--git-common-dir'])) / 'modules' / name)

    clone.clone_at(git, flags, subdir, url, pinned)


def _resolve_upstream_commit(git: GitRunner, flags: Flags, config: NestedConfig, subref: str) -> str:
    """The upstream commit to record for an adopted directory."""
    if not flags.upstream_commit:
        return ''
    if not config.remote:
        raise GitNestedError("--commit needs --remote")
    if not config.branch:
        output.verbose("determining the upstream default branch")
        config.branch = discovery.get_upstream_branch(git, config)
    fetched = fetch.do_fetch(git, config, subref)
    if not git.rev_exists(flags.upstream_commit):
        raise GitNestedError(f"no such upstream commit: {flags.upstream_commit}")
    if not git.commit_in_rev_list(flags.upstream_commit, fetched):
        raise GitNestedError(f"{flags.upstream_commit}: is not part of {config.remote} ({config.branch})")
    return flags.upstream_commit


def _validate_init_target(subdir: Path, gitnested: Path, git: GitRunner) -> None:
    """Reject targets that cannot become nested repositories."""
    if not subdir.exists():
        raise GitNestedError(f"{subdir.as_posix()}: does not exist")
    if gitnested.exists():
        raise GitNestedError(f"{subdir.as_posix()}: is already a nested repository")
    if not git.is_tracked(subdir):
        raise GitNestedError(f"{subdir.as_posix()}: exists, but git tracks nothing in it")


def _default_branch(git: GitRunner, config: NestedConfig) -> str:
    """The branch init should record when none was given."""
    return config.branch or git.check_output(['config', '--get', 'init.defaultbranch'], may_fail=True) or 'main'


def cmd_init(ctx: CommandContext) -> None:
    """Initialize a subdirectory as a nested repo."""
    git, flags, head_commit = ctx.git, ctx.flags, ctx.head
    if flags.from_submodule:
        _init_from_submodule(git, flags, setup.resolve_subdir(ctx.subdir))
        return
    subdir, gitnested, subref, config = setup.setup_command(git, 'init', flags, ctx.subdir, ctx.upstream)
    _validate_init_target(subdir, gitnested, git)

    upstream_commit = _resolve_upstream_commit(git, flags, config, subref)
    config.remote = config.remote or 'none'
    config.branch = _default_branch(git, config)

    output.verbose(f"writing {subdir.as_posix()}/.gitnested")
    nested_commit_ref = upstream_commit or head_commit
    gitfile.update_gitrepo_file(
        git=git,
        flags=flags,
        config=config,
        gitnested=gitnested,
        upstream_head_commit=upstream_commit,
        nested_commit_ref=nested_commit_ref,
        head_commit=head_commit,
        command='init',
    )
    msg = discovery.build_commit_message(git, config, upstream_commit or head_commit, nested_commit_ref, subdir, 'init')
    content.commit_gitnested_update(git, flags, subdir, msg)
    refs.create_nested_ref(git, subref, 'commit', nested_commit_ref)

    remote = "no remote" if config.remote == 'none' else f"{config.remote} ({config.branch})"
    at = f" at {git.check_output(['rev-parse', '--short', upstream_commit])}" if upstream_commit else ''
    output.say(f"{subdir.as_posix()}: initialised as a nested repository with {remote}{at}")
