"""Reporting on the nested repositories of the current repository."""

from __future__ import annotations

import re
from pathlib import Path

from .. import discovery, gitfile, output, refs
from ..constants import GITNESTED_FILENAME
from ..git import GitRunner
from ..models import CommandContext, Flags, NestedConfig
from . import fetch


def get_status(git: GitRunner, flags: Flags, git_tmp: Path) -> tuple[str, list[tuple[Path, NestedConfig]]]:
    """Get nested repository status.

    Returns:
        tuple: (output_text, list of (subdir, config) tuples)
    """
    nesteds = discovery.find_all_nested_repositories(git, flags)
    count = len(nesteds)
    header, done = _status_header(flags, count)
    if done:
        return header, []
    report = [header] if header else []

    status_list = []
    for subdir in nesteds:
        lines, status_entries = _status_for_subdir(git, flags, git_tmp, subdir)
        report.extend(lines)
        status_list.extend(status_entries)

    return ''.join(report), status_list


def _status_header(flags: Flags, count: int) -> tuple[str, bool]:
    """Build the status output header.

    Returns:
        tuple: (header_text, done). done=True means the whole status is just header_text
        (the "No nested repositories." early-exit case).
    """
    if flags.quiet:
        return "", False
    if count == 0:
        return "No nested repositories.\n", True
    ies = 'ies' if count != 1 else 'y'
    return f"{count} nested repositor{ies}:\n", False


def _status_for_subdir(
    git: GitRunner, flags: Flags, git_tmp: Path, subdir: Path
) -> tuple[list[str], list[tuple[Path, NestedConfig]]]:
    """Build the status output lines for one nested subdir.

    Returns:
        tuple: (output_lines, status_entries). status_entries is empty when
        subdir isn't a nested repository, else a single (subdir, config) entry.
    """
    subdir = subdir if isinstance(subdir, Path) else Path(subdir)
    subref = refs.sanitize_subref(git, str(subdir))

    gitrepo = subdir / GITNESTED_FILENAME
    if not gitrepo.is_file():
        return [f"'{subdir}' is not a nested repository\n"], []

    refs_fetch = f'refs/nested/{subref}/fetch'
    upstream_head = git.check_output(['rev-parse', '--short', refs_fetch], may_fail=True)

    config = gitfile.read_config(gitrepo, flags)

    if flags.fetch:
        fetch.do_fetch(git, config, subref)

    if flags.quiet:
        return [f"{subdir}\n"], [(subdir, config)]

    lines = _status_detail_lines(git, flags, git_tmp, subdir, subref, config, upstream_head)
    return lines, [(subdir, config)]


def _status_detail_lines(
    git: GitRunner,
    flags: Flags,
    git_tmp: Path,
    subdir: Path,
    subref: str,
    config: NestedConfig,
    upstream_head: str,
) -> list[str]:
    """Build the verbose per-subdir status lines shown when --quiet is not set."""
    lines = [f"Git nested repository '{subdir}':\n"]
    lines.extend(_status_identity_lines(git, subref, config, upstream_head))
    lines.extend(_status_commit_lines(git, config))
    lines.extend(_status_worktree_lines(git, git_tmp, subdir))

    if flags.verbose:
        lines.append(format_refs(git, subref))

    lines.append("\n")
    return lines


def _status_identity_lines(git: GitRunner, subref: str, config: NestedConfig, upstream_head: str) -> list[str]:
    """Build the branch/remote/tracking status lines for one nested subdir."""
    lines = []
    if git.branch_exists(f'nested/{subref}'):
        lines.append(f"  Nested Branch:  nested/{subref}\n")

    remote = f'nested/{subref}'
    url = git.check_output(['config', f'remote.{remote}.url'], may_fail=True)
    if url:
        lines.append(f"  Remote Name:     nested/{subref}\n")

    lines.append(f"  Remote URL:      {config.remote}\n")
    if upstream_head:
        lines.append(f"  Upstream Ref:    {upstream_head}\n")
    lines.append(f"  Tracking Branch: {config.branch}\n")
    return lines


def _status_commit_lines(git: GitRunner, config: NestedConfig) -> list[str]:
    """Build the pulled-commit/pull-parent status lines for one nested subdir."""
    lines = []
    if config.commit:
        short = git.check_output(['rev-parse', '--short', config.commit])
        lines.append(f"  Pulled Commit:   {short}\n")

    if config.parent:
        short = git.check_output(['rev-parse', '--short', config.parent])
        lines.append(f"  Pull Parent:     {short}\n")
    return lines


def _status_worktree_lines(git: GitRunner, git_tmp: Path, subdir: Path) -> list[str]:
    """Build the worktree status line(s) for one nested subdir, if any exist."""
    worktree_list = git.check_output(['worktree', 'list'], may_fail=True) or ''
    return [f"  Worktree: {line}\n" for line in worktree_list.splitlines() if f'{git_tmp}/nested/{subdir}' in line]


def _format_ref_line(git: GitRunner, subref: str, line: str) -> str | None:
    """Format one `git show-ref` line into a status display line, or None if not applicable."""
    m = re.match(rf'^([0-9a-f]+)\s+refs/nested/{subref}/([a-z]+)', line)
    if not m:
        return None

    sha = git.check_output(['rev-parse', '--short', m.group(1)])
    ref_type = m.group(2)
    ref = f'refs/nested/{subref}/{ref_type}'

    labels = {
        'branch': 'Branch Ref',
        'commit': 'Commit Ref',
        'fetch': 'Fetch Ref',
        'pull': 'Pull Ref',
        'push': 'Push Ref',
    }
    if ref_type not in labels:
        return None
    return f"    {labels[ref_type]:14} {sha} ({ref})\n"


def format_refs(git: GitRunner, subref: str) -> str:
    """Format refs for status."""
    show_ref = git.check_output(['show-ref'], may_fail=True) or ''

    lines = []
    for line in show_ref.splitlines():
        formatted = _format_ref_line(git, subref, line)
        if formatted:
            lines.append(formatted)

    if lines:
        return "  Refs:\n" + ''.join(lines)
    return ""


def cmd_status(ctx: CommandContext) -> None:
    """Get status of a nested repo (or all of them)."""
    git = ctx.git
    flags, git_tmp = ctx.flags, ctx.tmp
    report, _ = get_status(git, flags, git_tmp)
    output.payload(report)
