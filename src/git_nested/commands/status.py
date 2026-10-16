"""Reporting on the nested repositories of the current repository."""

from __future__ import annotations

import re
from pathlib import Path

from .. import discovery, gitfile, output, refs
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
    if flags.quiet:
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

    report = _details(git, subdir, subref, config, upstream_head)
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
        lines.append(f"  Pulled Commit:   {git.check_output(['rev-parse', '--short', config.commit])}")
    if config.parent:
        lines.append(f"  Pull Parent:     {git.check_output(['rev-parse', '--short', config.parent])}")
    # By branch, not by path: `git nested branch -d` puts it anywhere.
    worktree_list = git.check_output(['worktree', 'list'], may_fail=True)
    lines += [f"  Worktree: {line}" for line in worktree_list.splitlines() if line.endswith(f'[{branch}]')]
    return ''.join(f"{line}\n" for line in lines)


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
