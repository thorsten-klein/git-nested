"""Deriving and sanitising git ref names."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .errors import GitNestedError
from .git import GitRunner


def create_nested_ref(git: GitRunner, subref: str, ref_type: str, commit: str):
    """Create a git ref pointing to commit."""
    ref_name = f'refs/nested/{subref}/{ref_type}'
    git.run(['update-ref', ref_name, commit])
    return ref_name


def guess_subdir(remote: str) -> str:
    """Guess subdirectory name from remote URL."""
    if not remote:
        raise GitNestedError("No remote specified for guessing subdir")
    name = Path(remote).name
    if name.endswith('.git'):
        name = name[:-4]
    return name


def _is_valid_ref(git: GitRunner, ref: str) -> bool:
    """Check whether ref is already a valid git ref name (as a nested/ subref)."""
    result = git.run(['check-ref-format', f'nested/{ref}'], may_fail=True)
    return result.returncode == 0


def _strip_forbidden_ref_chars(sanitized: str) -> str:
    """Replace or trim characters that aren't allowed in a git ref name."""
    # Remove forbidden characters
    for c in ['~', '..', ' ', '/']:
        sanitized = sanitized.replace(c, '_')
    # Remove forbidden leading characters
    if sanitized[:1] in ('.', '-'):
        sanitized = '_' + sanitized[1:]
    if sanitized.endswith('.lock'):  # .lock ending is not allowed
        sanitized = sanitized[:-5] + '_lock'
    # Ref cannot end with a dot
    if sanitized.endswith('.'):
        sanitized = sanitized[:-1]
    return sanitized


def sanitize_subref(git: GitRunner, ref: str) -> str:
    """Sanitize subref to be a valid git ref."""
    # Check if already valid (check-ref-format succeeds), so no encoding needed
    if _is_valid_ref(git, ref):
        return ref

    # URL encode the subdir, then remove forbidden characters
    sanitized = _strip_forbidden_ref_chars(quote(ref, safe='/'))

    if not _is_valid_ref(git, sanitized):
        raise GitNestedError(f"Can't determine valid subref from '{ref}'.")
    return sanitized
