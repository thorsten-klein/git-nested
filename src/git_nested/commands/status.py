"""Reporting on the nested repositories of the current repository."""

from __future__ import annotations

import re
from pathlib import Path

from .. import content, discovery, filters, gitfile, history, output, refs
from ..constants import GITNESTED_FILENAME
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig
from . import fetch

# How `-v` labels each of a nested repository's refs.
_REF_LABELS = {
    'branch': 'Branch Ref',
    'commit': 'Commit Ref',
    'fetch': 'Fetch Ref',
    'pull': 'Pull Ref',
    'push': 'Push Ref',
}


def get_status(git: GitRunner, flags: Flags) -> str:
    """The status report of every nested repository; with --quiet, just their paths."""
    nesteds = discovery.find_all_nested_repositories(git, flags)
    count = len(nesteds)
    if flags.quiet or flags.short:
        header = ""
    elif count == 0:
        return "No nested repositories.\n"
    else:
        header = f"{count} nested repositor{'y' if count == 1 else 'ies'}:\n"
    return header + ''.join(_status_for_subdir(git, flags, subdir) for subdir in nesteds)


def _status_for_subdir(git: GitRunner, flags: Flags, subdir: Path) -> str:
    """The status report of one nested subdir."""
    subref = refs.sanitize_subref(git, subdir.as_posix())
    gitnested = subdir / GITNESTED_FILENAME
    if not gitnested.is_file():
        return f"'{subdir.as_posix()}' is not a nested repository\n"

    upstream_head = git.check_output(['rev-parse', '--short', f'refs/nested/{subref}/fetch'], may_fail=True)
    config = gitfile.read_config(gitnested, flags)
    if flags.fetch:
        fetch.do_fetch(git, config, subref)
    if flags.quiet:
        return f"{subdir.as_posix()}\n"
    local, behind, state = _changes(git, subdir, subref, config)
    if flags.short:
        return f"{subdir.as_posix()} {local} {behind} {state}\n"

    report = _details(git, subdir, subref, config, upstream_head)
    report += f"  Local Commits:   {local}\n  Behind Upstream: {behind}\n  Content:         {state}\n"
    if flags.verbose:
        report += format_refs(git, subref)
    return report + "\n"


def _details(git: GitRunner, subdir: Path, subref: str, config: NestedConfig, upstream_head: str) -> str:
    """Where one nested repository comes from, what it has pulled, and its branch and worktree."""
    branch = refs.nested_branch(git, subref)
    lines = [f"Git nested repository '{subdir.as_posix()}':"]
    if git.branch_exists(branch):
        lines.append(f"  Nested Branch:  {branch}")
    if git.check_output(['config', f'remote.nested/{subref}.url'], may_fail=True):
        lines.append(f"  Remote Name:     nested/{subref}")
    lines.append(f"  Remote URL:      {config.remote}")
    if upstream_head:
        lines.append(f"  Upstream Ref:    {upstream_head}")
    lines.append(f"  Tracking Branch: {config.branch}")
    if config.commit:
        lines.append(f"  Pulled Commit:   {_short(git, config.commit)}")
    if config.parent:
        lines.append(f"  Pull Parent:     {_short(git, config.parent)}")
    # By branch, not by path: `git nested branch -d` puts it anywhere.
    worktree_list = git.check_output(['worktree', 'list'], may_fail=True)
    lines += [f"  Worktree: {line}" for line in worktree_list.splitlines() if line.endswith(f'[{branch}]')]
    return ''.join(f"{line}\n" for line in lines)


def _changes(git: GitRunner, subdir: Path, subref: str, config: NestedConfig) -> tuple[str, str, str]:
    """Local commits since the sync point, upstream commits not pulled yet, and whether the content changed.

    '-' where git-nested can't tell. Inner nested repositories have their own status.
    """
    inner = tuple(
        path.relative_to(subdir).as_posix() + '/'
        for path in discovery.find_all_nested_repositories(git, Flags(all_deep=True))
        if path != subdir and path.is_relative_to(subdir)
    )
    return (_local_commits(git, subdir, config, inner), *_against_upstream(git, subdir, subref, config, inner))


def _local_commits(git: GitRunner, subdir: Path, config: NestedConfig, inner: tuple[str, ...]) -> str:
    """How many commits since the sync point changed subdir, not counting clone, pull and repair."""
    if not (config.parent and history.parent_is_ancestor(git, config.parent)):
        return '-'
    since = f'{config.parent}..HEAD'
    excluded = [f':(exclude){subdir.as_posix()}/{path}' for path in inner]
    touched = git.check_output(['rev-list', since, '--', subdir, *excluded]).split()
    # clone, pull and repair commits change .gitnested; the rest is local work
    synced = git.check_output(['rev-list', since, '--', subdir / GITNESTED_FILENAME]).split()
    return str(len(set(touched) - set(synced)))


def _against_upstream(
    git: GitRunner, subdir: Path, subref: str, config: NestedConfig, inner: tuple[str, ...]
) -> tuple[str, str]:
    """How many fetched upstream commits are not pulled yet, and whether the content differs from upstream."""
    if not (config.commit and git.rev_exists(config.commit)):
        return '-', '-'
    fetched = f'refs/nested/{subref}/fetch'
    behind = (
        git.check_output(['rev-list', '--count', f'{config.commit}..{fetched}']) if git.rev_exists(fetched) else '-'
    )
    upstream = (
        filters.build_filtered_commit(git, Path.cwd(), config.filter, config.commit) if config.filter else config.commit
    )
    return behind, 'same' if content.matches_upstream(git, subdir, upstream, inner) else 'changed'


def _short(git: GitRunner, rev: str) -> str:
    """`rev` abbreviated; a rebase or squash merge may have taken it away."""
    return git.check_output(['rev-parse', '--short', rev], may_fail=True) or rev[:9]


def format_refs(git: GitRunner, subref: str) -> str:
    """The refs of a nested repository, one line each."""
    lines = []
    for line in git.check_output(['show-ref'], may_fail=True).splitlines():
        m = re.match(rf'^([0-9a-f]+)\s+refs/nested/{subref}/([a-z]+)', line)
        if m and m.group(2) in _REF_LABELS:
            ref_type = m.group(2)
            sha = git.check_output(['rev-parse', '--short', m.group(1)])
            lines.append(f"    {_REF_LABELS[ref_type]:14} {sha} (refs/nested/{subref}/{ref_type})\n")
    return "  Refs:\n" + ''.join(lines) if lines else ""


def cmd_status(ctx: CommandContext) -> None:
    """Get status of a nested repo (or all of them)."""
    output.payload(get_status(ctx.git, ctx.flags))
