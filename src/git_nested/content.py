"""Creating and committing a nested branch, and placing its content."""

from __future__ import annotations

import dataclasses
from pathlib import Path, PurePosixPath
from typing import cast

from . import discovery, filters, gitfile, history, output, patches, refs, submodules, worktree
from .constants import GITNESTED_FILENAME
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
    worktree_dir: Path | None = None,
    start: str | None = None,
) -> Path:
    """Create a nested branch, checked out at `worktree_dir` or else in the default place under git_tmp.

    The branch starts at `start` if given. Else it is built from the history of HEAD.

    Returns:
        subdir_worktree
    """
    output.verbose(f"checking whether branch {branch} exists")
    if git.branch_exists(branch):
        return worktree.find_worktree(git, branch) or git_tmp / branch

    # git cannot create nested/lib next to a branch named nested.
    for prefix in PurePosixPath(branch).parents[:-1]:
        if git.branch_exists(prefix.as_posix()):
            raise GitNestedError(
                f"{subdir.as_posix()}: the branch {prefix} is in the way of {branch}; "
                f"rename it, or pick another name with 'git nested branch --name <name> {subdir.as_posix()}'"
            )

    if start:
        git.run(['branch', branch, start])
    else:
        output.verbose(f"nested parent is {config.parent}")
        history.create_branch(git, flags, config, subdir, gitnested, subref, command, branch)

    subdir_worktree = worktree_dir or git_tmp / branch
    # --no-checkout and reset: so the parent's post-checkout hook does not run
    git.run(['worktree', 'add', '--no-checkout', subdir_worktree, branch])
    git.run(['reset', '-q', '--hard'], cwd=subdir_worktree)
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
    head_commit: str | None,
    subdir_worktree: Path | None,
    command: str,
) -> None:
    """Replace subdir/ with the content of nested_commit_ref, and commit that with the updated .gitnested."""
    if not git.rev_exists(nested_commit_ref):
        raise GitNestedError(f"no such commit: {nested_commit_ref}")
    if not flags.force and not git.commit_in_rev_list(upstream_head_commit, nested_commit_ref):
        raise GitNestedError(f"can't commit: {nested_commit_ref} does not contain the upstream HEAD")

    local = place_with_patches(git, config, subdir, nested_commit_ref)
    gitfile.create_level_gitnested_files(git, subdir)
    # After the level files: an inner nested repo of our own needs none
    keep_inner_nested(git, flags, config, subdir, head_commit)

    # A level file has the regular .gitnested next to it, which is kept in
    # step so that operating on the nested repo directly still sees current info.
    regular = gitnested.parent / GITNESTED_FILENAME
    for path in [gitnested] + ([regular] if regular != gitnested and regular.exists() else []):
        output.verbose(f"writing {path.as_posix()}")
        gitfile.update_gitrepo_file(
            git=git,
            flags=flags,
            config=config,
            gitnested=path,
            upstream_head_commit=upstream_head_commit,
            nested_commit_ref=nested_commit_ref,
            head_commit=head_commit,
            command=command,
        )
    if local is not None:
        patches.write(git, config, subdir, upstream_head_commit, nested_commit_ref, local)

    if git.run(['diff', '--cached', '--quiet'], may_fail=True).returncode == 0:
        output.verbose("nothing to commit for the .gitnested update")
    else:
        msg = flags.message or discovery.build_commit_message(
            git, config, upstream_head_commit, nested_commit_ref, subdir, command
        )
        commit_gitnested_update(git, flags, subdir, msg)

    worktree.remove_worktree(git, subdir_worktree)
    refs.create_nested_ref(git, refs.sanitize_subref(subdir.as_posix()), 'commit', nested_commit_ref)


def place_with_patches(git: GitRunner, config: NestedConfig, subdir: Path, nested_commit_ref: str) -> list[str] | None:
    """Place the content, and keep the inner nested repos if the patches are used.

    Returns:
        the paths the patches leave out, or None if the patches are not in use.
    """
    if not patches.in_use(git, config, subdir):
        _place_content(git, config, subdir, nested_commit_ref)
        return None
    local = patches.local_paths(git, config, subdir)
    added_here = set(history.inner_repos(git, config, subdir)) - set(history.gitlinked_inner(git, config, subdir))
    _place_content(git, config, subdir, nested_commit_ref)
    patches.restore_inner_repos(git, subdir, sorted(added_here))
    patches.restore_ignored(git, config, subdir)
    return local


def keep_inner_nested(git: GitRunner, flags: Flags, config: NestedConfig, subdir: Path, head: str | None) -> None:
    """Do not commit a gitlink where a nested repo belongs.

    An inner nested repo comes back from `head`, with its local changes.
    Not with --force: that takes upstream as it is.
    With --recurse-submodules a new submodule is left out. It is nested next.
    """
    drop_new = flags.recurse_submodules and not (config.filter or config.exclude)
    for path, _ in submodules.gitlinks(git, subdir):
        if not flags.force and _was_nested(git, head, path):
            git.run(['update-index', '--force-remove', '--', path])
            git.run(['checkout', cast('str', head), '--', path])
        elif drop_new:
            _drop_gitlink(git, Path(path))


def _was_nested(git: GitRunner, head: str | None, path: str) -> bool:
    return (
        bool(head) and git.run(['cat-file', '-e', f'{head}:{path}/{GITNESTED_FILENAME}'], may_fail=True).returncode == 0
    )


def _drop_gitlink(git: GitRunner, path: Path) -> None:
    git.run(['update-index', '--force-remove', '--', path])
    if path.is_dir() and not any(path.iterdir()):
        path.rmdir()


def nested_tree(config: NestedConfig, subdir: Path) -> str:
    """The tree that subdir got its content from in the last clone, pull or commit."""
    tree = f'refs/nested/{refs.sanitize_subref(subdir.as_posix())}/commit'
    return f'{tree}:{config.path}' if config.path else tree


def _place_content(git: GitRunner, config: NestedConfig, subdir: Path, nested_commit_ref: str) -> None:
    """Replace whatever subdir/ holds with the (filtered) tree of nested_commit_ref."""
    if git.check_output(['ls-files', '--', subdir], may_fail=True):
        output.verbose("removing the old subdir content")
        git.run(['rm', '-r', '--', subdir])

    output.verbose(f"placing the upstream content in {subdir.as_posix()}/")
    if config.path:
        git.run(['read-tree', f'--prefix={subdir.as_posix()}', '-u', f'{nested_commit_ref}:{config.path}'])
    elif config.filter or config.exclude:
        filters.place_filtered_content(git, subdir, config.filter or [], config.exclude or [], nested_commit_ref)
    else:
        git.run(['read-tree', f'--prefix={subdir.as_posix()}', '-u', nested_commit_ref])


def matches_upstream(git: GitRunner, subdir: Path, upstream_commit: str, ignored: tuple[str, ...] = ()) -> bool:
    """Whether subdir at HEAD holds the upstream tree.

    Its top-level .gitnested files don't count, nor the `ignored` paths in it.
    """
    local = git.check_output(['rev-parse', f'HEAD:{subdir.as_posix()}'])
    changed = git.check_output(['diff-tree', '-r', '--name-only', f'{upstream_commit}^{{tree}}', local])
    return all(
        (Path(name).name.startswith(GITNESTED_FILENAME) and '/' not in name) or name.startswith(ignored)
        for name in changed.splitlines()
    )


def commit_gitnested_update(git: GitRunner, flags: Flags, subdir: Path, msg: str) -> None:
    """Commit what is staged onto the current branch, with --file's message if given, else `msg`.

    If the commit fails, e.g. a hook rejects it, the staged changes are undone.
    The tree was clean before the command, so nothing else is lost.
    """
    if flags.single_commit:
        output.verbose("staged; it goes into one commit with the others")
        return
    output.verbose("committing the .gitnested update")
    message = ['--file', flags.message_file] if flags.message_file else ['-m', msg]
    # The parent's hooks are for its own changes. `git config nested.verify true` runs them.
    verify = git.check_output(['config', '--type=bool', '--get', 'nested.verify'], may_fail=True) == 'true'
    try:
        signing = [*(['--signoff'] if flags.signoff else []), *(['-S'] if flags.gpg_sign else [])]
        git.run(['commit', *([] if verify else ['--no-verify']), *signing, *message])
    except GitNestedError as e:
        git.run(['reset', '-q', '--hard', 'HEAD'])
        raise GitNestedError(f"{subdir.as_posix()}: the commit failed, so nothing was changed:\n{e.message}") from None


def commit_all(git: GitRunner, flags: Flags, command: str) -> None:
    """Make the one commit --single-commit asks for, listing the nested repositories in it."""
    staged = git.check_output(['diff', '--cached', '--name-only', '-z']).split('\0')
    subdirs = sorted(Path(path).parent.as_posix() for path in staged if Path(path).name == GITNESTED_FILENAME)
    if not subdirs:
        return
    msg = f"git nested {command} --all\n\n" + "\n".join(f"- {subdir}" for subdir in subdirs)
    one_commit = cast('Flags', dataclasses.replace(flags, single_commit=False))
    commit_gitnested_update(git, one_commit, Path(), flags.message or msg)
