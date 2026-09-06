"""Creating and committing a nested branch, and placing its content."""

from __future__ import annotations

from pathlib import Path

from . import discovery, filters, gitfile, history, output, refs, worktree
from .constants import GITNESTED_FILENAME, GITNESTED_LEVEL_PREFIX
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags, NestedConfig


def create_nested_branch(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    branch: str,
    subdir: Path,
    gitnested: Path,
    git_tmp: Path,
    subref: str,
    command: str,
) -> Path:
    """Create a nested branch.

    Returns:
        subdir_worktree
    """
    output.verbose(f"Check if the '{branch}' branch already exists.")
    if git.branch_exists(branch):
        return git_tmp / branch

    output.verbose(f"Nested repository parent: {config.parent}")

    if config.parent:
        first_gitrepo_commit = history._create_branch_from_parent(
            git, flags, config, subdir, gitnested, subref, command, branch
        )
    else:
        first_gitrepo_commit = None
        history._create_branch_without_parent(git, subref, branch)

    # Remove .gitnested file
    history._filter_branch_history(git, branch, first_gitrepo_commit)

    subdir_worktree = worktree.create_worktree(git, branch, git_tmp)

    refs.create_nested_ref(git, subref, 'branch', branch)

    return subdir_worktree


def commit_nested_branch(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    gitnested: Path,
    nested_commit_ref: str,
    upstream_head_commit: str,
    head_commit: str,
    subdir_worktree: Path | None,
    command: str,
):
    """Commit a nested branch."""
    _verify_commit_ref(git, flags, nested_commit_ref, upstream_head_commit)

    _replace_subdir_content(git, subdir)

    output.verbose(f"Put remote nested content into '{subdir}/'.")
    if not config.filter:
        _place_full_content(git, subdir, nested_commit_ref)
    else:
        filters._place_filtered_content(git, subdir, config, nested_commit_ref)

    # Create .gitnested.levelN files for nested-in-nested repositories
    # Level will be auto-detected based on existing level files
    gitfile.create_level_gitnested_files(git, flags, subdir, head_commit)

    _sync_gitnested_files(git, flags, config, gitnested, upstream_head_commit, nested_commit_ref, head_commit, command)

    _finalize_commit(git, flags, config, subdir, nested_commit_ref, upstream_head_commit, subdir_worktree, command)


def _verify_commit_ref(git: GitRunner, flags: Flags, nested_commit_ref: str, upstream_head_commit: str) -> None:
    """Verify the nested commit exists and (unless --force) contains upstream HEAD."""
    output.verbose("Checking that the nested repository commit exists.")
    if not git.rev_exists(nested_commit_ref):
        raise GitNestedError(f"Commit ref '{nested_commit_ref}' does not exist.")

    if flags.force:
        return
    output.verbose("Make sure that the commit contains the upstream HEAD.")
    if not git.commit_in_rev_list(upstream_head_commit, nested_commit_ref):
        raise GitNestedError(f"Can't commit: '{nested_commit_ref}' doesn't contain upstream HEAD.")


def _replace_subdir_content(git: GitRunner, subdir: Path) -> None:
    """Remove any existing content of subdir/ before placing fresh upstream content."""
    has_files = git.check_output(['ls-files', '--', subdir], may_fail=True)
    if not has_files:
        return
    output.verbose("Remove old content of the subdir.")
    git.run(['rm', '-r', '--', subdir])


def _place_full_content(git: GitRunner, subdir: Path, nested_commit_ref: str) -> None:
    """Place the full upstream tree into subdir/ (the no-filter case)."""
    git.run(['read-tree', f'--prefix={subdir}', '-u', nested_commit_ref])


def _sync_gitnested_files(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    gitnested: Path,
    upstream_head_commit: str,
    nested_commit_ref: str,
    head_commit: str,
    command: str,
) -> None:
    """Update .gitnested (and its sibling regular file, if this is a levelN file)."""
    output.verbose(f"Put info into '{gitnested}' file.")
    gitfile.update_gitrepo_file(
        git=git,
        flags=flags,
        config=config,
        gitnested=gitnested,
        upstream_head_commit=upstream_head_commit,
        nested_commit_ref=nested_commit_ref,
        head_commit=head_commit,
        command=command,
    )
    git.run(['add', '-f', '--', gitnested])

    # If this is a .gitnested.levelN file, also update the regular .gitnested
    # so that when the nested repo is operated on directly, it has current info
    if GITNESTED_LEVEL_PREFIX not in str(gitnested):
        return
    regular_gitnested = gitnested.parent / GITNESTED_FILENAME
    if not regular_gitnested.exists():
        return
    output.verbose(f"Also updating {regular_gitnested} for consistency")
    gitfile.update_gitrepo_file(
        git=git,
        flags=flags,
        config=config,
        gitnested=regular_gitnested,
        upstream_head_commit=upstream_head_commit,
        nested_commit_ref=nested_commit_ref,
        head_commit=head_commit,
        command=command,
    )
    git.run(['add', '-f', '--', regular_gitnested])


def _commit_gitnested_update(git: GitRunner, flags: Flags, msg: str) -> None:
    """Commit the staged .gitnested update directly onto the current branch.

    By the time this runs, check_repository()/check_worktree_clean() have already
    guaranteed a non-empty outer repo for every command that reaches here (clone's own
    do_clone() separately rejects an empty repo before any commit logic runs), so a
    plain 'git commit' -- which needs no pre-existing HEAD anyway -- always applies.
    """
    output.verbose("Commit .gitnested update to the current branch.")
    if flags.message_file:
        git.run(['commit', '--file', flags.message_file])
    else:
        git.run(['commit', '-m', msg])


def _finalize_commit(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    subdir: Path,
    nested_commit_ref: str,
    upstream_head_commit: str,
    subdir_worktree: Path | None,
    command: str,
) -> None:
    """Commit the staged .gitnested update (if any), clean up, and record the commit ref."""
    # Check if there are changes to commit
    result = git.run(['diff', '--cached', '--quiet'], may_fail=True)
    has_changes = result.returncode != 0

    if has_changes:
        msg = flags.message or discovery.build_commit_message(
            git=git,
            config=config,
            upstream_head_commit=upstream_head_commit,
            nested_commit_ref=nested_commit_ref,
            subdir=subdir,
            command=command,
        )
        _commit_gitnested_update(git, flags, msg)
    else:
        output.verbose("No changes to commit for .gitnested update")

    worktree.remove_worktree(git, subdir_worktree)

    refs.create_nested_ref(git, refs.sanitize_subref(git, str(subdir)), 'commit', nested_commit_ref)
