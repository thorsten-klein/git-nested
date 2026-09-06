"""Cloning an upstream repository into a subdirectory of this one."""

from __future__ import annotations

from pathlib import Path

from .. import content, discovery, gitfile, output
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
) -> tuple[bool, NestedConfig, str | None, str]:
    """Clone implementation.

    Returns:
        tuple: (up_to_date, updated_config, nested_commit_ref, upstream_head_commit)
    """
    # Check if we can clone (fail if HEAD doesn't exist)
    if not git.rev_exists('HEAD'):
        raise GitNestedError("You can't clone into an empty repository")

    # Turn off force unless really a reclone
    force = _effective_force(flags, gitnested)

    up_to_date, config, upstream_head_commit = _do_clone_dispatch(git, flags, config, subdir, gitnested, subref, force)
    if up_to_date:
        return True, config, None, upstream_head_commit

    if flags.filter:
        config.filter = flags.filter

    output.verbose(f"Make the directory '{subdir}/' for the clone.")
    subdir.mkdir(parents=True, exist_ok=True)

    nested_commit_ref = upstream_head_commit
    return False, config, nested_commit_ref, upstream_head_commit


def _effective_force(flags: Flags, gitnested: Path) -> bool:
    """Force only applies to an actual reclone (there must be an existing .gitnested)."""
    return flags.force and gitnested.is_file()


def _do_clone_dispatch(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    subref: str,
    force: bool,
) -> tuple[bool, NestedConfig, str]:
    """Route to the force-reclone or fresh-clone path.

    Returns:
        tuple: (up_to_date, updated_config, upstream_head_commit)
    """
    if force:
        return _do_clone_forced(git, flags, config, subdir, gitnested, subref, flags.branch)
    config, upstream_head_commit = _do_clone_fresh(git, config, subdir, subref)
    return False, config, upstream_head_commit


def _do_clone_forced(
    git: GitRunner, flags: Flags, config: NestedConfig, subdir: Path, gitnested: Path, subref: str, branch
) -> tuple[bool, NestedConfig, str]:
    """Handle the force-reclone branch of do_clone.

    Returns:
        tuple: (up_to_date, updated_config, upstream_head_commit). When
        up_to_date is True the caller should return immediately.
    """
    upstream_head_commit = fetch.do_fetch(git, config, subref)
    config = gitfile.read_config(gitnested, flags)

    output.verbose("Check if we already are up to date.")
    if upstream_head_commit == config.commit:
        return True, config, upstream_head_commit

    output.verbose("Remove the existing subdir.")
    git.run(['rm', '-r', '--', subdir])

    if not branch:
        output.verbose("Determine the upstream head branch.")
        config.branch = discovery.get_upstream_branch(git, config)
        # Fetch again from the new branch
        upstream_head_commit = fetch.do_fetch(git, config, subref)

    return False, config, upstream_head_commit


def _do_clone_fresh(git: GitRunner, config: NestedConfig, subdir: Path, subref: str) -> tuple[NestedConfig, str]:
    """Handle the non-force branch of do_clone.

    Returns:
        tuple: (updated_config, upstream_head_commit)
    """
    if subdir.exists() and any(subdir.iterdir()):
        raise GitNestedError(f"The subdir '{subdir}' exists and is not empty.")

    if not config.branch:
        output.verbose("Determine the upstream head branch.")
        config.branch = discovery.get_upstream_branch(git, config)

    upstream_head_commit = fetch.do_fetch(git, config, subref)
    return config, upstream_head_commit


def cmd_clone(ctx: CommandContext) -> None:
    """Clone a remote repository into a local subdirectory."""
    git = ctx.git
    flags, subdir, upstream, head_commit = ctx.flags, ctx.subdir, ctx.upstream, ctx.head
    subdir, gitnested, subref, config = setup.setup_command(git, 'clone', flags, subdir, upstream)

    up_to_date, config, nested_commit_ref, upstream_head_commit = do_clone(
        git=git,
        flags=flags,
        config=config,
        subdir=subdir,
        gitnested=gitnested,
        subref=subref,
    )

    if not up_to_date:
        # do_clone only returns a None nested_commit_ref together with up_to_date=True.
        if nested_commit_ref is None:
            raise AssertionError(
                'do_clone returned nested_commit_ref=None with up_to_date=False'
            )  # pragma: no cover -- invariant guard, unreachable via the public API
        output.verbose(f"Commit the new '{subdir}/' content.")
        content.commit_nested_branch(
            git=git,
            flags=flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            nested_commit_ref=nested_commit_ref,
            upstream_head_commit=upstream_head_commit,
            head_commit=head_commit,
            subdir_worktree=None,
            command='clone',
        )

    if up_to_date:
        output.say(f"Nested repository '{subdir}' is up to date with upstream branch '{config.branch}'.")
    else:
        output.say(f"Nested repository '{config.remote}' ({config.branch}) cloned into '{subdir}'.")
