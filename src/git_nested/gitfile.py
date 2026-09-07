"""The .gitnested file itself.

Reading it, updating it, and the nested-in-nested level files.
"""

from __future__ import annotations

from pathlib import Path

from . import output, yamlio
from ._version import VERSION
from .constants import GITNESTED_FILENAME, GITNESTED_LEVEL_PREFIX
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags, NestedConfig

# The fields of a .gitnested file, in the order `git nested config` prints
# them, and what each one is. The nested operations write the whole file, so
# this is also what `config` is allowed to talk about.
CONFIG_FIELDS: dict[str, str] = {
    'remote': "the upstream repository",
    'branch': "the upstream branch",
    'method': "how upstream history is joined: 'merge' or 'rebase'",
    'commit': "the upstream commit currently nested",
    'parent': "the commit the nested history hangs off",
    'filter': "the paths of the upstream repository that are nested",
    'cmdver': "the git-nested version that last wrote this file",
}

# The rest are written by the nested operations themselves; setting one by
# hand would describe a state the repository is not in.
WRITABLE_CONFIG_FIELDS = ('remote', 'branch', 'method', 'parent')


def create_level_gitnested_files(
    git: GitRunner, flags: Flags, subdir: Path, head_commit: str, level: int | None = None
) -> None:
    """Create .gitnested.levelN files for nested-in-nested repositories.

    This allows sub-nested repositories to be pulled/pushed independently
    even when they are nested within another nested repository. `level` is
    auto-detected from existing level files when not given.
    """
    if level is None:
        level = _detect_next_level(git, subdir)

    all_files = git.check_output(['ls-files', '--', subdir], may_fail=True) or ''

    gitnested_files = [line for line in all_files.splitlines() if _is_nested_gitnested_file(line, subdir)]

    for gitnested_path in gitnested_files:
        _create_one_level_file(git, flags, gitnested_path, level, head_commit)


def _is_nested_gitnested_file(line: str, subdir: Path) -> bool:
    """Check whether line is a tracked .gitnested file other than subdir's own."""
    return line.endswith(GITNESTED_FILENAME) and line != f'{subdir}/{GITNESTED_FILENAME}'


def _detect_next_level(git: GitRunner, subdir: Path) -> int:
    """Auto-detect the next .gitnested.levelN number for subdir from existing level files."""
    all_files = git.check_output(['ls-files', '--', subdir], may_fail=True) or ''
    existing_levels = [
        lvl for lvl in (_extract_level_number(line, subdir) for line in all_files.splitlines()) if lvl is not None
    ]

    # Level 1 is the plain .gitnested of the outer nested repo, so the first
    # sub-nested repo inside it starts numbering at 2.
    return max(existing_levels) + 1 if existing_levels else 2


def _extract_level_number(line: str, subdir: Path) -> int | None:
    """Extract the N from a `.gitnested.levelN` git-tracked path, or None if line isn't one."""
    if not (GITNESTED_LEVEL_PREFIX in line and line.startswith(f'{subdir}/{GITNESTED_LEVEL_PREFIX}')):
        return None
    parts = line.split(GITNESTED_LEVEL_PREFIX)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


def _create_one_level_file(git: GitRunner, flags: Flags, gitnested_path: str, level: int, head_commit: str) -> None:
    """Write one .gitnested.levelN file (parent field cleared) and recurse into it."""
    gitnested_file = Path(gitnested_path)
    level_file = gitnested_file.parent / f'{GITNESTED_LEVEL_PREFIX}{level}'

    output.verbose(f"creating {level_file} for the sub-nested repository")

    if not gitnested_file.exists():
        return
    data = yamlio._read_yaml_config(gitnested_file)
    # The parent field describes lineage in the intermediate repo's context,
    # which doesn't apply here; it gets set correctly on this sub-nested
    # repo's own first pull/push.
    if 'nested' in data:
        data['nested']['parent'] = ''

    yamlio._write_yaml_config(level_file, data)
    git.run(['add', '-f', '--', str(level_file)])

    sub_subdir = gitnested_file.parent
    create_level_gitnested_files(git, flags, sub_subdir, head_commit, level + 1)


def read_config(gitnested: Path, flags: Flags) -> NestedConfig:
    """Read .gitnested file."""
    if not gitnested.is_file():
        raise GitNestedError(f"{gitnested} does not exist")

    config = NestedConfig.from_file(gitnested)

    if flags.remote:
        config.remote = flags.remote
    if flags.branch:
        config.branch = flags.branch
    if flags.method:
        config.method = flags.method

    return config


def update_gitrepo_file(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    gitnested: Path,
    upstream_head_commit: str,
    nested_commit_ref: str,
    head_commit: str,
    command: str,
) -> None:
    """Update .gitnested YAML file."""
    initial = not gitnested.exists()
    if initial and _recreate_gitnested_from_parent(git, gitnested, head_commit):
        initial = False

    data = yamlio._read_yaml_config(gitnested) if gitnested.exists() else {}
    nested = data.setdefault('nested', {})

    nested['commit'] = upstream_head_commit
    nested['method'] = flags.method or config.method or 'merge'
    nested['cmdver'] = VERSION
    if flags.filter:
        nested['filter'] = flags.filter

    _update_remote_field(nested, initial, flags, config, command)
    _update_branch_field(nested, initial, flags, config, command)
    _update_parent_field(git, nested, head_commit, nested_commit_ref, upstream_head_commit)

    yamlio._write_yaml_config(gitnested, data)
    git.run(['add', '-f', '--', gitnested])


def _recreate_gitnested_from_parent(git: GitRunner, gitnested: Path, head_commit: str) -> bool:
    """Try to recreate an initial .gitnested from the parent commit's copy of it.

    Returns:
        True if the file was recreated from head_commit.
    """
    result = git.run(['cat-file', '-e', f'{head_commit}:{gitnested}'], may_fail=True)
    if result.returncode != 0:
        return False
    content = git.check_output(['cat-file', '-p', f'{head_commit}:{gitnested}'])
    gitnested.write_text(content)
    return True


def _should_update_field(flags_update: bool, command: str, override_value: object) -> bool:
    """Check if a config field should be overwritten, given --update and the command."""
    return bool(override_value) and (flags_update or command in ['push', 'clone'])


def _update_remote_field(nested: dict, initial: bool, flags: Flags, config: NestedConfig, command: str) -> None:
    """Set nested['remote'] when it is initial or an override applies."""
    if initial or _should_update_field(flags.update, command, flags.remote):
        nested['remote'] = config.remote


def _update_branch_field(nested: dict, initial: bool, flags: Flags, config: NestedConfig, command: str) -> None:
    """Set nested['branch'] when it is initial, a clone, or an override applies."""
    # For clone command, always update branch (including force reclone to different branch)
    if initial or command == 'clone' or _should_update_field(flags.update, command, flags.branch):
        nested['branch'] = config.branch


def _update_parent_field(
    git: GitRunner, nested: dict, head_commit: str, nested_commit_ref: str, upstream_head_commit: str
) -> None:
    """Set nested['parent'] once the nested commit has caught up with upstream."""
    if not (head_commit and nested_commit_ref):
        return
    nested_commit = git.check_output(['rev-parse', nested_commit_ref])
    if upstream_head_commit == nested_commit:
        nested['parent'] = head_commit
