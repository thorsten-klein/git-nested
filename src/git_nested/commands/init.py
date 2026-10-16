"""Turning an existing subdirectory into a nested repository."""

from __future__ import annotations

from .. import content, discovery, gitfile, output, refs
from ..cli import setup
from ..errors import GitNestedError
from ..models import CommandContext


def cmd_init(ctx: CommandContext) -> None:
    """Initialize a subdirectory as a nested repo."""
    git, flags, head_commit = ctx.git, ctx.flags, ctx.head
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
