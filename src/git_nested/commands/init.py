"""Turning an existing subdirectory into a nested repository."""

from __future__ import annotations

from pathlib import Path

from .. import checks, discovery, gitfile, output, refs
from ..cli import setup
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig


def do_init(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    head_commit: str,
    subref: str,
) -> str:
    """Initialize a nested repository.

    Returns:
        nested_commit_ref
    """
    checks.check_subdir_for_init(git, subdir, gitnested)
    nested_commit_ref = head_commit

    output.verbose(f"Put info into '{subdir}/.gitnested' file.")
    gitfile.update_gitrepo_file(
        git=git,
        flags=flags,
        config=config,
        gitnested=gitnested,
        upstream_head_commit='',  # No upstream for init
        nested_commit_ref=nested_commit_ref,
        head_commit=head_commit,
        command='init',
    )

    output.verbose(f"Add the new '{subdir}/.gitnested' file.")
    git.run(['add', '-f', '--', gitnested])

    output.verbose("Commit the changes.")
    msg = discovery.build_commit_message(
        git=git,
        config=config,
        upstream_head_commit=head_commit,
        nested_commit_ref=nested_commit_ref,
        subdir=subdir,
        command='init',
    )
    git.run(['commit', '-m', msg])

    refs.create_nested_ref(git, subref, 'commit', nested_commit_ref)

    return nested_commit_ref


def cmd_init(ctx: CommandContext) -> None:
    """Initialize a subdirectory as a nested repo."""
    git = ctx.git
    flags, subdir, upstream, head_commit = ctx.flags, ctx.subdir, ctx.upstream, ctx.head
    subdir, gitnested, subref, config = setup.setup_command(git, 'init', flags, subdir, upstream)

    # Set defaults
    config.remote = config.remote or 'none'
    config.branch = config.branch or discovery.get_default_branch(git)

    do_init(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        head_commit=head_commit,
        subref=subref,
    )

    remote_msg = "(with no remote)." if config.remote == 'none' else f"with remote '{config.remote}' ({config.branch})."
    output.say(f"Nested repository created from '{subdir}' {remote_msg}")
