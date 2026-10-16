"""The .gitnested file itself.

Reading it, updating it, and the nested-in-nested level files.
"""

from __future__ import annotations

from pathlib import Path

from . import output, yamlio
from ._version import VERSION
from .constants import GITNESTED_FILENAME, GITNESTED_LEVEL_PREFIX
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
    'readonly': "'true' makes push refuse, for a repository that is only pulled",
}

# The rest are written by the nested operations themselves; setting one by
# hand would describe a state the repository is not in.
WRITABLE_CONFIG_FIELDS = ('remote', 'branch', 'method', 'parent', 'readonly')


def create_level_gitnested_files(git: GitRunner, subdir: Path, level: int | None = None) -> None:
    """Create .gitnested.levelN files for nested-in-nested repositories.

    This allows sub-nested repositories to be pulled/pushed independently
    even when they are nested within another nested repository. `level` is
    auto-detected from existing level files when not given.
    """
    tracked = git.check_output(['ls-files', '-z', '--', subdir], may_fail=True).split('\0')
    level = level or _next_level(subdir, tracked)
    own = f'{subdir.as_posix()}/{GITNESTED_FILENAME}'
    for path in tracked:
        if path.endswith(GITNESTED_FILENAME) and path != own:
            _create_one_level_file(git, Path(path), level)


def _next_level(subdir: Path, tracked: list[str]) -> int:
    """The level after the highest .gitnested.levelN file among subdir's `tracked` files."""
    prefix = f'{subdir.as_posix()}/{GITNESTED_LEVEL_PREFIX}'
    levels = [int(p.removeprefix(prefix)) for p in tracked if p.startswith(prefix) and p.removeprefix(prefix).isdigit()]
    # Level 1 is the plain .gitnested of the outer nested repo, so the first
    # sub-nested repo inside it starts numbering at 2.
    return max(levels, default=1) + 1


def _create_one_level_file(git: GitRunner, gitnested_file: Path, level: int) -> None:
    """Write one .gitnested.levelN file (parent field cleared) and recurse into it."""
    level_file = gitnested_file.parent / f'{GITNESTED_LEVEL_PREFIX}{level}'
    output.verbose(f"creating {level_file.as_posix()} for the sub-nested repository")
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
    create_level_gitnested_files(git, gitnested_file.parent, level + 1)


def read_config(gitnested: Path, flags: Flags) -> NestedConfig:
    """Read .gitnested file, with the --remote/--branch/--method overrides applied."""
    config = NestedConfig.from_file(gitnested)
    config.remote = flags.remote or config.remote
    config.branch = flags.branch or config.branch
    config.method = flags.method or config.method
    return config


def update_gitrepo_file(
    git: GitRunner,
    flags: Flags,
    config: NestedConfig,
    gitnested: Path,
    upstream_head_commit: str,
    nested_commit_ref: str,
    head_commit: str | None,
    command: str,
) -> None:
    """Update .gitnested YAML file, and stage it."""
    initial = not gitnested.exists() and not _recreate_gitnested_from_parent(git, gitnested, head_commit)

    data = yamlio._read_yaml_config(gitnested) if gitnested.exists() else {}
    nested = data.setdefault('nested', {})
    nested['commit'] = upstream_head_commit
    nested['method'] = flags.method or config.method or 'merge'
    nested['cmdver'] = VERSION
    if flags.filter:
        nested['filter'] = flags.filter

    _update_lineage(nested, initial, flags, config, command)
    # The parent only moves once the nested commit has caught up with upstream.
    if head_commit and nested_commit_ref and git.check_output(['rev-parse', nested_commit_ref]) == upstream_head_commit:
        nested['parent'] = head_commit

    yamlio._write_yaml_config(gitnested, data)
    git.run(['add', '-f', '--', gitnested])


def _update_lineage(nested: dict, initial: bool, flags: Flags, config: NestedConfig, command: str) -> None:
    """Write remote and branch where this is a new file, or the command line overrides them.

    An override is written when --update asks for it, and always by clone.
    A clone always records its branch and remote, even a forced reclone.
    """
    overriding = flags.update or command == 'clone'
    if initial or command == 'clone' or (overriding and flags.remote):
        nested['remote'] = config.remote
    if initial or command == 'clone' or (overriding and flags.branch):
        nested['branch'] = config.branch


def _recreate_gitnested_from_parent(git: GitRunner, gitnested: Path, head_commit: str | None) -> bool:
    """Try to recreate an initial .gitnested from the parent commit's copy of it.

    Returns:
        True if the file was recreated from head_commit.
    """
    if not head_commit:
        return False
    content = git.run(['cat-file', '-p', f'{head_commit}:{gitnested.as_posix()}'], may_fail=True)
    if content.returncode != 0:
        return False
    gitnested.write_text(content.stdout.strip(), encoding='utf-8', newline='\n')
    return True
