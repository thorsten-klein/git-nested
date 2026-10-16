"""Deriving and sanitising git ref names."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .errors import GitNestedError
from .git import GitRunner


def create_nested_ref(git: GitRunner, subref: str, ref_type: str, commit: str) -> str:
    """Create a git ref pointing to commit."""
    ref_name = f'refs/nested/{subref}/{ref_type}'
    git.run(['update-ref', ref_name, commit])
    return ref_name


def _branch_name_key(subref: str) -> str:
    """The .git/config key recording a nested repository's branch name, when it is not the default."""
    return f'nested.{subref}.branchname'


def nested_branch(git: GitRunner, subref: str) -> str:
    """The local branch holding the nested commits of `subref`.

    'nested/<subref>' unless `git nested branch --name` chose another name,
    which it records in .git/config so that every other command finds it too.
    """
    recorded = git.check_output(['config', '--get', _branch_name_key(subref)], may_fail=True)
    return recorded or f'nested/{subref}'


def record_nested_branch(git: GitRunner, subref: str, branch: str | None) -> None:
    """Record `branch` as the nested branch of `subref`; None, or the default name, forgets it."""
    if branch and branch != f'nested/{subref}':
        git.run(['config', _branch_name_key(subref), branch])
    else:
        # exits 5 when there is nothing to unset, which is just as good
        git.run(['config', '--unset', _branch_name_key(subref)], may_fail=True)


def guess_subdir(remote: str) -> str:
    """Guess subdirectory name from remote URL."""
    if not remote:
        raise GitNestedError("no subdir given, and no remote to guess one from")
    return Path(remote).name.removesuffix('.git')


def _is_valid_ref(git: GitRunner, ref: str) -> bool:
    """Check whether ref is already a valid git ref name (as a nested/ subref)."""
    return git.run(['check-ref-format', f'nested/{ref}'], may_fail=True).returncode == 0


def sanitize_subref(git: GitRunner, ref: str) -> str:
    """Sanitize subref to be a valid git ref."""
    if _is_valid_ref(git, ref):
        return ref

    sanitized = quote(ref, safe='/')
    for c in ['~', '..', ' ', '/']:
        sanitized = sanitized.replace(c, '_')
    if sanitized[:1] in ('.', '-'):
        sanitized = '_' + sanitized[1:]
    # Neither a '.lock' nor a '.' ending is allowed
    if sanitized.endswith('.lock'):
        sanitized = sanitized.removesuffix('.lock') + '_lock'
    sanitized = sanitized.removesuffix('.')

    if not _is_valid_ref(git, sanitized):
        raise GitNestedError(f"can't derive a git ref name from {ref}")
    return sanitized
