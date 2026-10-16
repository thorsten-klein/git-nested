"""Turning an existing subdirectory into a nested repository."""

from __future__ import annotations

from pathlib import Path

from .. import content, discovery, gitfile, output, refs, submodules
from .._compat import rmtree
from ..cli import setup
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext, Flags
from . import clone

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


def cmd_init(ctx: CommandContext) -> None:
    """Initialize a subdirectory as a nested repo."""
    git, flags, head_commit = ctx.git, ctx.flags, ctx.head
    if flags.from_submodule:
        _init_from_submodule(git, flags, setup.resolve_subdir(ctx.subdir))
        return
    subdir, gitnested, subref, config = setup.setup_command(git, 'init', flags, ctx.subdir, ctx.upstream)

    if not subdir.exists():
        raise GitNestedError(f"{subdir.as_posix()}: does not exist")
    if gitnested.exists():
        raise GitNestedError(f"{subdir.as_posix()}: is already a nested repository")
    if not git.is_tracked(subdir):
        raise GitNestedError(f"{subdir.as_posix()}: exists, but git tracks nothing in it")

    config.remote = config.remote or 'none'
    config.branch = (
        config.branch or git.check_output(['config', '--get', 'init.defaultbranch'], may_fail=True) or 'main'
    )

    output.verbose(f"writing {subdir.as_posix()}/.gitnested")
    gitfile.update_gitrepo_file(
        git=git,
        flags=flags,
        config=config,
        gitnested=gitnested,
        upstream_head_commit='',  # No upstream for init
        nested_commit_ref=head_commit,
        head_commit=head_commit,
        command='init',
    )
    msg = discovery.build_commit_message(git, config, head_commit, head_commit, subdir, 'init')
    content.commit_gitnested_update(git, flags, subdir, msg)
    refs.create_nested_ref(git, subref, 'commit', head_commit)

    remote = "no remote" if config.remote == 'none' else f"{config.remote} ({config.branch})"
    output.say(f"{subdir.as_posix()}: initialised as a nested repository with {remote}")
