"""git-nested - Git Submodule Alternative.

Copyright 2026 - Thorsten Klein <thorsten.klein.git@gmail.com>
"""

# Postponed evaluation (PEP 563). The 3.9 floor that originally required this
# is gone, but it stays: annotations become lazily-parsed strings, which is
# what lets modules reference each other's types under `if TYPE_CHECKING:`
# without the import cycles a package of this shape would otherwise grow.
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import textwrap
from collections.abc import Callable
from contextlib import chdir
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

import yaml

from ._version import VERSION
from .constants import (
    FETCH_HEAD_REV,
    GIT_LOG_DATE_DEFAULT_FLAG,
    GITNESTED_FILENAME,
    GITNESTED_LEVEL_PREFIX,
)
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags, NestedConfig

# The package's public surface. Names are re-exported here so that
# `from git_nested import X` keeps working as the internals are split up --
# note that this means monkeypatching git_nested.X patches the re-export, not
# the definition, so tests must reach for the defining module instead.
__all__ = [
    'VERSION',
    'Flags',
    'GitNested',
    'GitNestedCommand',
    'GitNestedError',
    'GitNestedRepo',
    'GitRunner',
    'NestedConfig',
    'chdir',
    'main',
]


class GitNestedRepo:
    """Handles repository operations and business logic."""

    def __init__(self):
        """No state to initialize; all methods operate on their arguments."""

    # -------------------------------------
    # Logging helpers (delegated to maintain separation)
    # -------------------------------------

    def verbose(self, msg: str, flags: Flags):
        """Print verbose messages."""
        if flags.verbose:
            print(f"* {msg}")

    def say(self, msg: str, flags: Flags):
        """Print message unless quiet."""
        if not flags.quiet:
            print(msg)

    # -------------------------------------
    # Helper methods
    # -------------------------------------

    def _read_yaml_config(self, filepath: Path) -> dict:
        """Read YAML configuration file."""
        with filepath.open('r') as f:
            return yaml.safe_load(f) or {}

    def _write_yaml_config(self, filepath: Path, data: dict) -> None:
        """Write YAML configuration file with header."""
        GITREPO_HEADER = textwrap.dedent("""\
            # This subdirectory is managed by "git nested".
            # Refer to: https://github.com/thorsten-klein/git-nested#readme
            #
            """)
        with filepath.open('w') as f:
            f.write(GITREPO_HEADER)
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def create_level_gitnested_files(
        self, git: GitRunner, flags: Flags, subdir: Path, head_commit: str, level: int | None = None
    ):
        """Create .gitnested.levelN files for nested-in-nested repositories.

        This allows sub-nested repositories to be pulled/pushed independently
        even when they are nested within another nested repository.

        Args:
            git: GitRunner instance
            flags: Command flags
            subdir: The subdirectory being cloned/pulled
            head_commit: The parent commit (will be used as parent for level files)
            level: The nesting level (auto-detected if None)
        """
        # Auto-detect the level based on existing .gitnested.level* files in subdir
        if level is None:
            level = self._detect_next_level(git, subdir)

        # Find all .gitnested files within the subdirectory (excluding the subdir's own .gitnested)
        all_files = git.check_output(['ls-files', '--', subdir], may_fail=True) or ''

        gitnested_files = [line for line in all_files.splitlines() if self._is_nested_gitnested_file(line, subdir)]

        for gitnested_path in gitnested_files:
            self._create_one_level_file(git, flags, gitnested_path, level, head_commit)

    def _is_nested_gitnested_file(self, line: str, subdir: Path) -> bool:
        """Check whether line is a tracked .gitnested file other than subdir's own."""
        return line.endswith(GITNESTED_FILENAME) and line != f'{subdir}/{GITNESTED_FILENAME}'

    def _detect_next_level(self, git: GitRunner, subdir: Path) -> int:
        """Auto-detect the next .gitnested.levelN number for subdir from existing level files."""
        # Check what level files exist in the subdir itself
        all_files = git.check_output(['ls-files', '--', subdir], may_fail=True) or ''
        existing_levels = [
            lvl
            for lvl in (self._extract_level_number(line, subdir) for line in all_files.splitlines())
            if lvl is not None
        ]

        # Start at level 2 (first sub-nested), or one above the highest existing level
        return max(existing_levels) + 1 if existing_levels else 2

    def _extract_level_number(self, line: str, subdir: Path) -> int | None:
        """Extract the N from a `.gitnested.levelN` git-tracked path, or None if line isn't one."""
        if not (GITNESTED_LEVEL_PREFIX in line and line.startswith(f'{subdir}/{GITNESTED_LEVEL_PREFIX}')):
            return None
        # Extract level number
        parts = line.split(GITNESTED_LEVEL_PREFIX)
        if len(parts) != 2 or not parts[1].isdigit():
            return None
        return int(parts[1])

    def _create_one_level_file(
        self, git: GitRunner, flags: Flags, gitnested_path: str, level: int, head_commit: str
    ) -> None:
        """Write one .gitnested.levelN file (parent field cleared) and recurse into it."""
        gitnested_file = Path(gitnested_path)
        level_file = gitnested_file.parent / f'{GITNESTED_LEVEL_PREFIX}{level}'

        self.verbose(f"Creating {level_file} for sub-nested repository", flags)

        # Copy the .gitnested content to .gitnested.levelN, but clear the parent field
        # The parent field from the intermediate repo doesn't apply in this context
        # It will be set correctly on the first pull/push operation
        if not gitnested_file.exists():
            return
        data = self._read_yaml_config(gitnested_file)
        # Clear the parent field - it will be set on first pull/push
        if 'nested' in data:
            data['nested']['parent'] = ''

        # Write the modified config to .gitnested.levelN
        self._write_yaml_config(level_file, data)
        # Add the level file to git
        git.run(['add', '-f', '--', str(level_file)])

        # Recursively check for deeper nesting with incremented level
        sub_subdir = gitnested_file.parent
        self.create_level_gitnested_files(git, flags, sub_subdir, head_commit, level + 1)

    def create_nested_ref(self, git: GitRunner, subref: str, ref_type: str, commit: str):
        """Create a git ref pointing to commit."""
        ref_name = f'refs/nested/{subref}/{ref_type}'
        git.run(['update-ref', ref_name, commit])
        return ref_name

    # -------------------------------------
    # Worker Functions
    # -------------------------------------

    def do_clone(
        self,
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
        force = self._effective_force(flags, gitnested)

        up_to_date, config, upstream_head_commit = self._do_clone_dispatch(
            git, flags, config, subdir, gitnested, subref, force
        )
        if up_to_date:
            return True, config, None, upstream_head_commit

        if flags.filter:
            config.filter = flags.filter

        self.verbose(f"Make the directory '{subdir}/' for the clone.", flags)
        subdir.mkdir(parents=True, exist_ok=True)

        nested_commit_ref = upstream_head_commit
        return False, config, nested_commit_ref, upstream_head_commit

    def _effective_force(self, flags: Flags, gitnested: Path) -> bool:
        """Force only applies to an actual reclone (there must be an existing .gitnested)."""
        return flags.force and gitnested.is_file()

    def _do_clone_dispatch(
        self,
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
            return self._do_clone_forced(git, flags, config, subdir, gitnested, subref, flags.branch)
        config, upstream_head_commit = self._do_clone_fresh(git, flags, config, subdir, subref)
        return False, config, upstream_head_commit

    def _do_clone_forced(
        self, git: GitRunner, flags: Flags, config: NestedConfig, subdir: Path, gitnested: Path, subref: str, branch
    ) -> tuple[bool, NestedConfig, str]:
        """Handle the force-reclone branch of do_clone.

        Returns:
            tuple: (up_to_date, updated_config, upstream_head_commit). When
            up_to_date is True the caller should return immediately.
        """
        upstream_head_commit = self.do_fetch(git, flags, config, subref)
        config = self.read_config(gitnested, flags)

        self.verbose("Check if we already are up to date.", flags)
        if upstream_head_commit == config.commit:
            return True, config, upstream_head_commit

        self.verbose("Remove the existing subdir.", flags)
        git.run(['rm', '-r', '--', subdir])

        if not branch:
            self.verbose("Determine the upstream head branch.", flags)
            config.branch = self.get_upstream_branch(git, config)
            # Fetch again from the new branch
            upstream_head_commit = self.do_fetch(git, flags, config, subref)

        return False, config, upstream_head_commit

    def _do_clone_fresh(
        self, git: GitRunner, flags: Flags, config: NestedConfig, subdir: Path, subref: str
    ) -> tuple[NestedConfig, str]:
        """Handle the non-force branch of do_clone.

        Returns:
            tuple: (updated_config, upstream_head_commit)
        """
        if subdir.exists() and any(subdir.iterdir()):
            raise GitNestedError(f"The subdir '{subdir}' exists and is not empty.")

        if not config.branch:
            self.verbose("Determine the upstream head branch.", flags)
            config.branch = self.get_upstream_branch(git, config)

        upstream_head_commit = self.do_fetch(git, flags, config, subref)
        return config, upstream_head_commit

    def do_init(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        subdir: Path,
        gitnested: Path,
        head_commit: str,
        subref: str,
    ) -> str:
        """Initialize a nested repository.

        Returns:
            nested_commit_ref
        """
        self.check_subdir_for_init(git, subdir, gitnested)
        nested_commit_ref = head_commit

        self.verbose(f"Put info into '{subdir}/.gitnested' file.", flags)
        self.update_gitrepo_file(
            git=git,
            flags=flags,
            config=config,
            gitnested=gitnested,
            upstream_head_commit='',  # No upstream for init
            nested_commit_ref=nested_commit_ref,
            head_commit=head_commit,
            command='init',
        )

        self.verbose(f"Add the new '{subdir}/.gitnested' file.", flags)
        git.run(['add', '-f', '--', gitnested])

        self.verbose("Commit the changes.", flags)
        msg = self.build_commit_message(
            git=git,
            config=config,
            upstream_head_commit=head_commit,
            nested_commit_ref=nested_commit_ref,
            subdir=subdir,
            command='init',
        )
        git.run(['commit', '-m', msg])

        self.create_nested_ref(git, subref, 'commit', nested_commit_ref)

        return nested_commit_ref

    def do_pull(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        subdir: Path,
        gitnested: Path,
        git_tmp: Path,
        subref: str,
    ) -> tuple[bool, str | None, Path | None, str | None]:
        """Pull implementation.

        Returns:
            tuple: (success, nested_commit_ref, subdir_worktree, error_msg)
        """
        upstream_head_commit = self.do_fetch(git, flags, config, subref)

        # Force reclone is handled entirely by the caller (cmd_pull), which
        # never calls do_pull() when flags.force is set.
        if upstream_head_commit == config.commit and not flags.update:
            return False, None, None, None

        branch = f'nested/{subref}'
        self.delete_branch(git, branch, git_tmp)
        nested_commit_ref = branch

        self.verbose(f"Create nested branch '{branch}'.", flags)
        subdir_worktree = self.create_nested_branch(
            git=git,
            flags=flags,
            config=config,
            branch=branch,
            subdir=subdir,
            gitnested=gitnested,
            git_tmp=git_tmp,
            subref=subref,
            command='pull',
        )

        method = flags.method or config.method
        merge_target = self._pull_merge_target(git, subref, config, subdir_worktree, upstream_head_commit)

        error_msg = self._run_merge_or_rebase(git, method, merge_target, branch, config, subdir_worktree)
        if error_msg:
            # Merge/rebase failed - return failure with error message
            return False, nested_commit_ref, subdir_worktree, error_msg

        self.create_nested_ref(git, subref, 'branch', branch)

        return True, nested_commit_ref, subdir_worktree, None

    def _pull_merge_target(
        self, git: GitRunner, subref: str, config: NestedConfig, subdir_worktree: Path, upstream_head_commit: str
    ) -> str:
        """Determine what to merge/rebase onto: the raw fetch, or a filtered view of it."""
        refs_fetch = f'refs/nested/{subref}/fetch'
        if not config.filter:
            return refs_fetch

        # The local nested branch only ever contained the filtered subset of
        # files. Merging the raw (unfiltered) upstream fetch against it makes
        # git see files that were "deleted" locally (because they were never
        # pulled in) as delete/modify conflicts whenever upstream touches
        # them. Build a filtered view of the fetched commit so only files
        # that actually matter to the local checkout can conflict.
        return self.build_filtered_commit(git, subdir_worktree, config, upstream_head_commit)

    def _run_merge_or_rebase(
        self, git: GitRunner, method: str, merge_target: str, branch: str, config: NestedConfig, subdir_worktree: Path
    ) -> str | None:
        """Run the merge or rebase step of a pull; return an error message on failure, else None."""
        try:
            if method == 'rebase':
                git.run(['rebase', merge_target, branch], cwd=subdir_worktree, print_error=False)
            else:
                # If parent is empty, allow unrelated histories (for nested-in-nested repos)
                merge_cmd = ['merge', merge_target]
                if not config.parent:
                    merge_cmd.append('--allow-unrelated-histories')
                git.run(merge_cmd, cwd=subdir_worktree, print_error=False)
        except GitNestedError as e:
            return f'The "git {method}" command failed:\n{e.message}'
        return None

    def build_filtered_commit(self, git: GitRunner, cwd: Path, config: NestedConfig, commit: str) -> str:
        """Build a throwaway commit whose tree only contains the filtered paths.

        Applies the exact same literal/regex rules used when the filtered
        content is written into the working tree.

        The new commit keeps `commit` as its sole parent so its ancestry (and
        thus merge-base detection against the local nested branch) is unaffected.

        Returns:
            sha of the filtered commit
        """
        with tempfile.TemporaryDirectory() as tmp:
            index_file = Path(tmp) / 'index'
            env = os.environ.copy()
            env['GIT_INDEX_FILE'] = str(index_file)

            git.run(['read-tree', '--empty'], cwd=cwd, env=env)

            def already_indexed(path: str) -> bool:
                return bool(git.check_output(['ls-files', '--stage', '--', path], cwd=cwd, env=env, may_fail=True))

            # Callers only reach this method when config.filter is truthy (see
            # do_pull/commit_nested_branch's `if config.filter:` guards).
            if config.filter is None:
                raise AssertionError(
                    'config.filter must be set when build_filtered_commit is called'
                )  # pragma: no cover -- invariant guard, unreachable via the public API
            regex_patterns: list[re.Pattern] = []
            for p in config.filter:
                self._index_literal_filter_entry(git, cwd, env, commit, p, regex_patterns)

            if regex_patterns:
                self._index_regex_matches(git, cwd, env, commit, regex_patterns, already_indexed)

            filtered_tree = git.check_output(['write-tree'], cwd=cwd, env=env)
            return git.check_output(
                ['commit-tree', '-p', commit, '-m', 'git-nested: filtered view for merge', filtered_tree], cwd=cwd
            )

    def _index_literal_filter_entry(
        self, git: GitRunner, cwd: Path, env: dict, commit: str, p: str, regex_patterns: list[re.Pattern]
    ) -> None:
        """Index one filter entry: a tree or a blob, else collect it as a regex pattern."""
        obj_type = git.check_output(['cat-file', '-t', f'{commit}:{p}'], may_fail=True, cwd=cwd)
        if obj_type == 'tree':
            git.run(['read-tree', f'--prefix={p}', f'{commit}:{p}'], cwd=cwd, env=env)
        elif obj_type == 'blob':
            mode = git.check_output(['ls-tree', commit, '--', p]).split()[0]
            blob_sha = git.check_output(['rev-parse', f'{commit}:{p}'], cwd=cwd)
            git.run(['update-index', '--add', '--cacheinfo', f'{mode},{blob_sha},{p}'], cwd=cwd, env=env)
        else:
            try:
                regex_patterns.append(re.compile(p))
            except re.error as e:
                raise GitNestedError(f"Invalid filter pattern '{p}': {e}") from e

    def _index_regex_matches(
        self,
        git: GitRunner,
        cwd: Path,
        env: dict,
        commit: str,
        regex_patterns: list[re.Pattern],
        already_indexed: Callable[[str], bool],
    ) -> None:
        """Index every blob in `commit` whose path matches a regex filter pattern and isn't indexed yet."""
        tree_listing = git.check_output(['ls-tree', '-r', commit], may_fail=True, cwd=cwd) or ''
        for line in tree_listing.splitlines():
            meta, blob_path = line.split('\t', 1)
            if not self._blob_needs_regex_index(blob_path, regex_patterns, already_indexed):
                continue
            mode, _obj_type, blob_sha = meta.split()
            git.run(['update-index', '--add', '--cacheinfo', f'{mode},{blob_sha},{blob_path}'], cwd=cwd, env=env)

    def _blob_needs_regex_index(
        self, blob_path: str, regex_patterns: list[re.Pattern], already_indexed: Callable[[str], bool]
    ) -> bool:
        """Check whether blob_path matches a regex filter pattern and isn't already indexed."""
        if not any(pattern.fullmatch(blob_path) for pattern in regex_patterns):
            return False
        return not already_indexed(blob_path)

    def do_push(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        subdir: Path,
        gitnested: Path,
        git_tmp: Path,
        subref: str,
        branch: str | None = None,
    ) -> tuple[bool, str, Path | None, bool, str | None]:
        """Push implementation.

        Returns:
            tuple: (success, branch_name, subdir_worktree, branch_created, new_commit)
        """
        branch_name = self._push_branch_name(git, flags, config)

        branch, subdir_worktree, branch_created, new_upstream, upstream_head_commit, early_exit = (
            self._push_branch_setup(git, flags, config, subdir, gitnested, git_tmp, subref, branch, branch_name)
        )
        if early_exit:
            return early_exit

        if not git.branch_exists(branch):
            raise GitNestedError(f"No nested branch '{branch}' to push.")

        new_commit = git.check_output(['rev-parse', branch])
        up_to_date_result = self._push_up_to_date_result(
            new_upstream, upstream_head_commit, new_commit, branch, branch_name, branch_created, git, git_tmp
        )
        if up_to_date_result:
            return up_to_date_result

        self._push_check_ancestry(git, flags, new_upstream, upstream_head_commit, branch)

        self._push_run_push(git, flags, config, branch, branch_name, subref)

        return True, branch_name, subdir_worktree, branch_created, new_commit

    def _push_branch_name(self, git: GitRunner, flags: Flags, config: NestedConfig) -> str:
        """Compute the resulting remote branch name for a push."""
        branch_name = flags.branch
        if not branch_name:
            toplevel = git.check_output(['rev-parse', '--show-toplevel'])
            repo_name = Path(toplevel).name
            branch_name = f"{repo_name}-{config.branch}"
        return branch_name

    def _push_fetch_missing_upstream(self, stderr: str) -> bool:
        """Check whether a failed fetch means 'no such branch upstream yet' (ok) vs a real error.

        Returns:
            True when the fetch failed because the branch doesn't exist upstream yet.
        """
        if re.search(r"(^|\n)fatal: couldn't find remote ref ", stderr.lower()):
            return True
        raise GitNestedError(f"Fetch for push failed: {stderr}")

    def _push_verify_or_refetch(
        self, git: GitRunner, flags: Flags, config: NestedConfig, branch_name: str, upstream: str
    ) -> str:
        """Ensure upstream hasn't moved past config.commit, or refetch the original branch under --force."""
        if upstream == config.commit:
            return upstream
        if not flags.force:
            raise GitNestedError(f"There are new changes upstream ({branch_name}), you need to pull first.")
        # Force mode: fetch original branch to be based on correct commit
        git.run(['fetch', '--no-tags', '--quiet', config.remote, config.branch])
        return git.check_output(['rev-parse', FETCH_HEAD_REV])

    def _push_fetch_upstream(
        self, git: GitRunner, flags: Flags, config: NestedConfig, branch_name: str
    ) -> tuple[bool, str | None]:
        """Auto-fetch the push target branch and validate we're not behind upstream.

        Returns:
            tuple: (new_upstream, upstream_head_commit)
        """
        result = git.run(['fetch', '--no-tags', '--quiet', config.remote, branch_name], may_fail=True)
        if result.returncode != 0:
            return self._push_fetch_missing_upstream(result.stderr), None
        upstream = git.check_output(['rev-parse', FETCH_HEAD_REV])
        upstream = self._push_verify_or_refetch(git, flags, config, branch_name, upstream)
        return False, upstream

    def _push_branch_setup(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        subdir: Path,
        gitnested: Path,
        git_tmp: Path,
        subref: str,
        branch: str | None,
        branch_name: str,
    ) -> tuple[str, Path | None, bool, bool, str | None, tuple | None]:
        """Resolve the local branch to push: prepare a fresh nested branch, or validate an explicit one.

        Returns:
            tuple: (branch, subdir_worktree, branch_created, new_upstream, upstream_head_commit, early_exit)
        """
        if not branch:
            return self._push_prepare_branch(git, flags, config, subdir, gitnested, git_tmp, subref, branch_name)
        if flags.squash:
            raise GitNestedError("Squash option (-s) can't be used with branch parameter")
        return branch, None, False, False, None, None

    def _push_prepare_branch(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        subdir: Path,
        gitnested: Path,
        git_tmp: Path,
        subref: str,
        branch_name: str,
    ) -> tuple[str, Path, bool, bool, str | None, tuple | None]:
        """Auto-fetch, create the local nested branch, and rebase it onto the fetched upstream.

        Returns:
            tuple: (branch, subdir_worktree, branch_created, new_upstream, upstream_head_commit, early_exit).
            early_exit is the do_push result to return immediately if the rebase fails, else None.
        """
        new_upstream, upstream_head_commit = self._push_fetch_upstream(git, flags, config, branch_name)

        branch = f'nested/{subref}'
        subdir_worktree = git_tmp / branch
        self.delete_branch(git, branch, git_tmp)

        updated_config = config
        if flags.squash:
            updated_config = NestedConfig(
                remote=config.remote,
                branch=config.branch,
                commit=config.commit,
                parent='HEAD^',
                method=config.method,
            )

        subdir_worktree = self.create_nested_branch(
            git=git,
            flags=flags,
            config=updated_config,
            branch=branch,
            subdir=subdir,
            gitnested=gitnested,
            git_tmp=git_tmp,
            subref=subref,
            command='push',
        )

        method = flags.method or config.method
        if method == 'rebase':
            refs_fetch = f'refs/nested/{subref}/fetch'
            try:
                git.run(['rebase', refs_fetch, branch], cwd=subdir_worktree)
            except GitNestedError:
                early_exit = (False, branch_name, subdir_worktree, True, None)
                return branch, subdir_worktree, True, new_upstream, upstream_head_commit, early_exit

        return branch, subdir_worktree, True, new_upstream, upstream_head_commit, None

    def _push_up_to_date_result(
        self,
        new_upstream: bool,
        upstream_head_commit: str | None,
        new_commit: str,
        branch: str,
        branch_name: str,
        branch_created: bool,
        git: GitRunner,
        git_tmp: Path,
    ) -> tuple | None:
        """Check whether the branch is already up to date with upstream.

        Returns:
            the do_push result to return if up to date, else None.
        """
        if new_upstream or upstream_head_commit != new_commit:
            return None
        if branch_created:
            self.delete_branch(git, branch, git_tmp)
        return False, branch_name, None, branch_created, new_commit

    def _push_check_ancestry(
        self, git: GitRunner, flags: Flags, new_upstream: bool, upstream_head_commit: str | None, branch: str
    ) -> None:
        """Ensure branch contains upstream HEAD before pushing, unless --force or nothing to compare against.

        upstream_head_commit is only known when we auto-fetched above (branch was
        None on entry); when the caller passes an explicit branch we have nothing
        to compare ancestry against, so the safety check is skipped rather than
        spuriously failing against a None commit-ish.
        """
        if flags.force or new_upstream or upstream_head_commit is None:
            return
        if not git.commit_in_rev_list(upstream_head_commit, branch):
            raise GitNestedError(f"Can't commit: '{branch}' doesn't contain upstream HEAD: {upstream_head_commit}")

    def _push_run_push(
        self, git: GitRunner, flags: Flags, config: NestedConfig, branch: str, branch_name: str, subref: str
    ) -> None:
        """Run the actual `git push` for the nested branch and record the push ref."""
        cmd = ['push']
        if flags.force:
            cmd.append('--force')
        cmd.extend([config.remote, f'{branch}:{branch_name}'])
        git.run(cmd)

        self.create_nested_ref(git, subref, 'push', branch)

    def get_diff(self, git: GitRunner, flags: Flags, config: NestedConfig, subdir: Path, subref: str) -> str:
        """Compute the diff between the local nested repository content and the freshly fetched upstream content.

        Returns:
            diff text (empty string if there are no differences)
        """
        upstream_head_commit = self.do_fetch(git, flags, config, subref)

        local_tree = git.check_output(['rev-parse', f'HEAD:{subdir}'])

        if config.filter:
            upstream_target = self.build_filtered_commit(git, Path.cwd(), config, upstream_head_commit)
        else:
            upstream_target = upstream_head_commit

        return git.check_output([
            'diff',
            local_tree,
            upstream_target,
            '--',
            ':(exclude,glob)**/.gitnested*',
        ])

    def do_fetch(self, git: GitRunner, flags: Flags, config: NestedConfig, subref: str) -> str:
        """Fetch upstream content.

        Returns:
            upstream_head_commit
        """
        if config.remote == 'none':
            raise GitNestedError("Can't fetch nested repository. Remote is 'none'.")

        branch_info = f"({config.branch})" if config.branch else ""
        self.verbose(f"Fetch the upstream: {config.remote} {branch_info}.", flags)

        cmd = ['fetch', '--no-tags', '--quiet', config.remote]
        if config.branch:
            cmd.append(config.branch)

        git.run(cmd)

        self.verbose("Get the upstream nested HEAD commit.", flags)
        upstream_head_commit = git.check_output(['rev-parse', FETCH_HEAD_REV])

        self.create_nested_ref(git, subref, 'fetch', FETCH_HEAD_REV)

        return upstream_head_commit

    def _check_parent_is_ancestor(self, git: GitRunner, config: NestedConfig, gitnested: Path, subdir: Path) -> None:
        """Raise a recovery-hint error unless config.parent is an ancestor of HEAD."""
        result = git.run(['merge-base', '--is-ancestor', config.parent, 'HEAD'], may_fail=True)
        if result.returncode == 0:
            return
        prev = git.check_output(['log', '-1', '-G', 'commit =', '--format=%H', gitnested], may_fail=True)
        if prev:
            prev = git.check_output(['log', '-1', '--format=%H', f'{prev.strip()}^'])
        raise GitNestedError(
            textwrap.dedent(
                f"""\
            The last sync point (where upstream and the nested were equal) is not an ancestor.
            This is usually caused by a rebase affecting that commit.
            To recover set the nested parent in '{gitnested}'
            to '{prev}'
            and validate the nested by comparing with 'git nested branch {subdir}'"""
            )
        )

    def _extract_gitrepo_commit(self, git: GitRunner, commit: str, subdir: Path) -> str | None:
        """Extract the recorded nested commit from commit's .gitnested file, or None."""
        gitrepo_content = git.check_output(['cat-file', '-p', f'{commit}:{subdir}/.gitnested'], may_fail=True)
        if not gitrepo_content:
            return None
        try:
            gitrepo_data = yaml.safe_load(gitrepo_content) or {}
            gitrepo_commit = gitrepo_data.get('nested', {}).get('commit', '')
        except yaml.YAMLError:
            return None
        if not gitrepo_commit:
            return None
        return gitrepo_commit.strip()

    def _is_direct_child(self, git: GitRunner, ancestor: str | None, commit: str) -> bool:
        """Check whether commit is a direct child of ancestor (always true if there's no ancestor yet)."""
        if not ancestor:
            return True
        parents = git.check_output(['show', '-s', '--pretty=format:%P', commit])
        return ancestor in parents

    def _check_rebase_safety(self, git: GitRunner, command: str, subref: str, gitrepo_commit: str) -> None:
        """Raise if a pull would silently accept a rewritten/unreachable upstream history."""
        refs_fetch = f'refs/nested/{subref}/fetch'
        if not (git.rev_exists(refs_fetch) and command == 'pull'):
            return
        result = git.run(['merge-base', '--is-ancestor', gitrepo_commit, refs_fetch], may_fail=True)
        if result.returncode == 0:
            return
        if not git.rev_exists(gitrepo_commit):
            raise GitNestedError(
                f"Local repository does not contain {gitrepo_commit}. Try to 'git nested fetch {subref}' or add the '-F' flag."
            )
        raise GitNestedError(
            f"Upstream history has been rewritten. Commit {gitrepo_commit} is not in the upstream history. Try to 'git nested fetch {subref}' or add the '-F' flag."
        )

    def _compute_second_parent(self, flags: Flags, config: NestedConfig, gitrepo_commit: str, state: dict) -> list[str]:
        """Compute the commit-tree second parent, tracking the first/last gitrepo commit seen."""
        second_parent: list[str] = []
        if not state['first_gitrepo_commit']:
            state['first_gitrepo_commit'] = gitrepo_commit
            second_parent = ['-p', gitrepo_commit]

        method = flags.method or config.method
        if method != 'rebase' and gitrepo_commit != state['last_gitrepo_commit']:
            second_parent = ['-p', gitrepo_commit]
            state['last_gitrepo_commit'] = gitrepo_commit

        return second_parent

    def _commit_has_subdir_content(self, git: GitRunner, commit: str, subdir: Path) -> bool:
        """Check whether commit has content under subdir/."""
        result = git.run(['cat-file', '-e', f'{commit}:{subdir}'], may_fail=True)
        return result.returncode == 0

    def _create_chain_commit(
        self, git: GitRunner, commit: str, subdir: Path, first_parent: list[str], second_parent: list[str]
    ) -> str:
        """Create one nested commit-tree entry, preserving the original author/committer/date."""
        author_date = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%ad', commit])
        author_email = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%ae', commit])
        author_name = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%an', commit])
        committer_date = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%cd', commit])
        committer_email = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%ce', commit])
        committer_name = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%cn', commit])
        commit_msg = git.check_output(['log', '-1', GIT_LOG_DATE_DEFAULT_FLAG, '--format=%B', commit])

        # Set author and committer info for deterministic commits
        env = os.environ.copy()
        env.update({
            'GIT_AUTHOR_DATE': author_date,
            'GIT_AUTHOR_EMAIL': author_email,
            'GIT_AUTHOR_NAME': author_name,
            'GIT_COMMITTER_DATE': committer_date,
            'GIT_COMMITTER_EMAIL': committer_email,
            'GIT_COMMITTER_NAME': committer_name,
        })

        tree_cmd = ['commit-tree', '-F', '-', *first_parent, *second_parent, f'{commit}:{subdir}']
        return git.check_output(tree_cmd, input=commit_msg, env=env)

    def _process_chain_commit(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        subdir: Path,
        subref: str,
        command: str,
        commit: str,
        state: dict,
    ) -> None:
        """Process one commit into the nested commit chain, updating state in place."""
        gitrepo_commit = self._extract_gitrepo_commit(git, commit, subdir)
        if not gitrepo_commit:
            return

        if not self._is_direct_child(git, state['ancestor'], commit):
            return
        state['ancestor'] = commit

        self._check_rebase_safety(git, command, subref, gitrepo_commit)

        first_parent: list[str] = ['-p', state['prev_commit']] if state['prev_commit'] else []
        second_parent = self._compute_second_parent(flags, config, gitrepo_commit, state)

        if self._commit_has_subdir_content(git, commit, subdir):
            state['prev_commit'] = self._create_chain_commit(git, commit, subdir, first_parent, second_parent)

    def _build_nested_commit_chain(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        commits: list[str],
        subdir: Path,
        subref: str,
        command: str,
    ) -> tuple[str | None, str | None]:
        """Walk commits and build the nested commit chain.

        Returns:
            tuple: (prev_commit, first_gitrepo_commit)
        """
        state = {'ancestor': None, 'first_gitrepo_commit': None, 'last_gitrepo_commit': None, 'prev_commit': None}
        for commit in commits:
            self._process_chain_commit(git, flags, config, subdir, subref, command, commit, state)
        return state['prev_commit'], state['first_gitrepo_commit']

    def _create_branch_from_parent(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        subdir: Path,
        gitnested: Path,
        subref: str,
        command: str,
        branch: str,
    ) -> str | None:
        """Build branch by replaying subdir content across the parent..HEAD commit range.

        Returns:
            first_gitrepo_commit (or None), used to scope the later history filtering.
        """
        self._check_parent_is_ancestor(git, config, gitnested, subdir)

        commits = git.check_output([
            'rev-list',
            '--reverse',
            '--ancestry-path',
            '--topo-order',
            f'{config.parent}..HEAD',
        ]).splitlines()

        prev_commit, first_gitrepo_commit = self._build_nested_commit_chain(
            git, flags, config, commits, subdir, subref, command
        )

        if prev_commit is None:
            # No commit in the parent..HEAD range ever touched subdir, so the
            # chain builder above never had content to build a nested commit from.
            raise GitNestedError(
                f"No commit between '{config.parent}' and HEAD touches '{subdir}'; "
                "can't reconstruct nested branch history."
            )
        git.run(['branch', branch, prev_commit])
        return first_gitrepo_commit

    def _create_branch_without_parent(self, git: GitRunner, subref: str, branch: str) -> None:
        """Build branch by taking the full HEAD history and filtering it down to subdir/."""
        git.run(['branch', branch, 'HEAD'])
        git.run(['filter-branch', '-f', '--subdirectory-filter', subref, branch], may_fail=True)

    def _filter_branch_history(self, git: GitRunner, branch: str, first_gitrepo_commit: str | None) -> None:
        """Strip the .gitnested file from branch's history."""
        filter_range = f'{first_gitrepo_commit}..{branch}' if first_gitrepo_commit else branch
        git.check_output(
            [
                'filter-branch',
                '-f',
                '--prune-empty',
                '--tree-filter',
                'rm -f .gitnested',
                '--',
                filter_range,
                '--first-parent',
            ],
            may_fail=True,
        )

    def create_nested_branch(
        self,
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
        self.verbose(f"Check if the '{branch}' branch already exists.", flags)
        if git.branch_exists(branch):
            return git_tmp / branch

        self.verbose(f"Nested repository parent: {config.parent}", flags)

        if config.parent:
            first_gitrepo_commit = self._create_branch_from_parent(
                git, flags, config, subdir, gitnested, subref, command, branch
            )
        else:
            first_gitrepo_commit = None
            self._create_branch_without_parent(git, subref, branch)

        # Remove .gitnested file
        self._filter_branch_history(git, branch, first_gitrepo_commit)

        subdir_worktree = self.create_worktree(git, branch, git_tmp)

        self.create_nested_ref(git, subref, 'branch', branch)

        return subdir_worktree

    def commit_nested_branch(
        self,
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
        self._verify_commit_ref(git, flags, nested_commit_ref, upstream_head_commit)

        self._replace_subdir_content(git, flags, subdir)

        self.verbose(f"Put remote nested content into '{subdir}/'.", flags)
        if not config.filter:
            self._place_full_content(git, subdir, nested_commit_ref)
        else:
            self._place_filtered_content(git, subdir, config, nested_commit_ref)

        # Create .gitnested.levelN files for nested-in-nested repositories
        # Level will be auto-detected based on existing level files
        self.create_level_gitnested_files(git, flags, subdir, head_commit)

        self._sync_gitnested_files(
            git, flags, config, gitnested, upstream_head_commit, nested_commit_ref, head_commit, command
        )

        self._finalize_commit(
            git, flags, config, subdir, nested_commit_ref, upstream_head_commit, subdir_worktree, command
        )

    def _verify_commit_ref(
        self, git: GitRunner, flags: Flags, nested_commit_ref: str, upstream_head_commit: str
    ) -> None:
        """Verify the nested commit exists and (unless --force) contains upstream HEAD."""
        self.verbose("Checking that the nested repository commit exists.", flags)
        if not git.rev_exists(nested_commit_ref):
            raise GitNestedError(f"Commit ref '{nested_commit_ref}' does not exist.")

        if flags.force:
            return
        self.verbose("Make sure that the commit contains the upstream HEAD.", flags)
        if not git.commit_in_rev_list(upstream_head_commit, nested_commit_ref):
            raise GitNestedError(f"Can't commit: '{nested_commit_ref}' doesn't contain upstream HEAD.")

    def _replace_subdir_content(self, git: GitRunner, flags: Flags, subdir: Path) -> None:
        """Remove any existing content of subdir/ before placing fresh upstream content."""
        has_files = git.check_output(['ls-files', '--', subdir], may_fail=True)
        if not has_files:
            return
        self.verbose("Remove old content of the subdir.", flags)
        git.run(['rm', '-r', '--', subdir])

    def _place_full_content(self, git: GitRunner, subdir: Path, nested_commit_ref: str) -> None:
        """Place the full upstream tree into subdir/ (the no-filter case)."""
        git.run(['read-tree', f'--prefix={subdir}', '-u', nested_commit_ref])

    def _place_literal_filter_entry(
        self, git: GitRunner, subdir: Path, nested_commit_ref: str, p: str, regex_patterns: list[re.Pattern]
    ) -> None:
        """Place one filter entry (a tree or a blob) into subdir/, else collect it as a regex pattern."""
        obj_type = git.check_output(['cat-file', '-t', f'{nested_commit_ref}:{p}'], may_fail=True)
        if obj_type == 'tree':
            git.run(['read-tree', f'--prefix={subdir}/{p}', '-u', f'{nested_commit_ref}:{p}'])
        elif obj_type == 'blob':
            file_path = subdir / p
            file_path.parent.mkdir(parents=True, exist_ok=True)
            content = git.run(['cat-file', 'blob', f'{nested_commit_ref}:{p}']).stdout
            file_path.write_text(content)
            git.run(['add', '-f', '--', str(file_path)])
        else:
            try:
                regex_patterns.append(re.compile(p))
            except re.error as e:
                raise GitNestedError(f"Invalid filter pattern '{p}': {e}") from e

    def _blob_needs_placement(self, blob_path: str, subdir: Path, regex_patterns: list[re.Pattern]) -> bool:
        """Check whether blob_path matches a regex filter pattern and hasn't been placed yet."""
        if not any(pattern.fullmatch(blob_path) for pattern in regex_patterns):
            return False
        return not (subdir / blob_path).exists()

    def _place_regex_matches(
        self, git: GitRunner, subdir: Path, nested_commit_ref: str, regex_patterns: list[re.Pattern]
    ) -> None:
        """Place every blob matching a regex filter pattern that hasn't already been placed."""
        all_blobs = (
            git.check_output(['ls-tree', '-r', '--name-only', nested_commit_ref], may_fail=True) or ''
        ).splitlines()
        for blob_path in all_blobs:
            if not self._blob_needs_placement(blob_path, subdir, regex_patterns):
                continue
            file_path = subdir / blob_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            content = git.run(['cat-file', 'blob', f'{nested_commit_ref}:{blob_path}']).stdout
            file_path.write_text(content)
            git.run(['add', '-f', '--', str(file_path)])

    def _place_filtered_content(
        self, git: GitRunner, subdir: Path, config: NestedConfig, nested_commit_ref: str
    ) -> None:
        """Place only the filtered upstream paths into subdir/ (literal paths + regex patterns)."""
        # Callers only reach this method when config.filter is truthy (see
        # commit_nested_branch's `if not config.filter: ... else:` guard).
        if config.filter is None:
            raise AssertionError(
                'config.filter must be set when _place_filtered_content is called'
            )  # pragma: no cover -- invariant guard, unreachable via the public API
        regex_patterns: list[re.Pattern] = []
        for p in config.filter:
            self._place_literal_filter_entry(git, subdir, nested_commit_ref, p, regex_patterns)

        if regex_patterns:
            self._place_regex_matches(git, subdir, nested_commit_ref, regex_patterns)

    def _sync_gitnested_files(
        self,
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
        self.verbose(f"Put info into '{gitnested}' file.", flags)
        self.update_gitrepo_file(
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
        self.verbose(f"Also updating {regular_gitnested} for consistency", flags)
        self.update_gitrepo_file(
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

    def _commit_gitnested_update(self, git: GitRunner, flags: Flags, msg: str) -> None:
        """Commit the staged .gitnested update directly onto the current branch.

        By the time this runs, check_repository()/check_worktree_clean() have already
        guaranteed a non-empty outer repo for every command that reaches here (clone's own
        do_clone() separately rejects an empty repo before any commit logic runs), so a
        plain 'git commit' -- which needs no pre-existing HEAD anyway -- always applies.
        """
        self.verbose("Commit .gitnested update to the current branch.", flags)
        if flags.message_file:
            git.run(['commit', '--file', flags.message_file])
        else:
            git.run(['commit', '-m', msg])

    def _finalize_commit(
        self,
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
            msg = flags.message or self.build_commit_message(
                git=git,
                config=config,
                upstream_head_commit=upstream_head_commit,
                nested_commit_ref=nested_commit_ref,
                subdir=subdir,
                command=command,
            )
            self._commit_gitnested_update(git, flags, msg)
        else:
            self.verbose("No changes to commit for .gitnested update", flags)

        self.remove_worktree(git, subdir_worktree)

        self.create_nested_ref(git, self.sanitize_subref(git, str(subdir)), 'commit', nested_commit_ref)

    def get_status(self, git: GitRunner, flags: Flags, git_tmp: Path) -> tuple[str, list[tuple[Path, NestedConfig]]]:
        """Get nested repository status.

        Returns:
            tuple: (output_text, list of (subdir, config) tuples)
        """
        nesteds = self.find_all_nested_repositories(git, flags)
        count = len(nesteds)
        header, done = self._status_header(flags, count)
        if done:
            return header, []
        output = [header] if header else []

        status_list = []
        for subdir in nesteds:
            lines, status_entries = self._status_for_subdir(git, flags, git_tmp, subdir)
            output.extend(lines)
            status_list.extend(status_entries)

        return ''.join(output), status_list

    def _status_header(self, flags: Flags, count: int) -> tuple[str, bool]:
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
        self, git: GitRunner, flags: Flags, git_tmp: Path, subdir: Path
    ) -> tuple[list[str], list[tuple[Path, NestedConfig]]]:
        """Build the status output lines for one nested subdir.

        Returns:
            tuple: (output_lines, status_entries). status_entries is empty when
            subdir isn't a nested repository, else a single (subdir, config) entry.
        """
        subdir = subdir if isinstance(subdir, Path) else Path(subdir)
        subref = self.sanitize_subref(git, str(subdir))

        gitrepo = subdir / GITNESTED_FILENAME
        if not gitrepo.is_file():
            return [f"'{subdir}' is not a nested repository\n"], []

        refs_fetch = f'refs/nested/{subref}/fetch'
        upstream_head = git.check_output(['rev-parse', '--short', refs_fetch], may_fail=True)

        config = self.read_config(gitrepo, flags)

        if flags.fetch:
            self.do_fetch(git, flags, config, subref)

        if flags.quiet:
            return [f"{subdir}\n"], [(subdir, config)]

        lines = self._status_detail_lines(git, flags, git_tmp, subdir, subref, config, upstream_head)
        return lines, [(subdir, config)]

    def _status_detail_lines(
        self,
        git: GitRunner,
        flags: Flags,
        git_tmp: Path,
        subdir: Path,
        subref: str,
        config: NestedConfig,
        upstream_head: str,
    ) -> list[str]:
        """Build the verbose per-subdir status lines shown when --quiet is not set."""
        output = [f"Git nested repository '{subdir}':\n"]
        output.extend(self._status_identity_lines(git, subref, config, upstream_head))
        output.extend(self._status_commit_lines(git, config))
        output.extend(self._status_worktree_lines(git, git_tmp, subdir))

        if flags.verbose:
            output.append(self.format_refs(git, subref))

        output.append("\n")
        return output

    def _status_identity_lines(
        self, git: GitRunner, subref: str, config: NestedConfig, upstream_head: str
    ) -> list[str]:
        """Build the branch/remote/tracking status lines for one nested subdir."""
        output = []
        if git.branch_exists(f'nested/{subref}'):
            output.append(f"  Nested Branch:  nested/{subref}\n")

        remote = f'nested/{subref}'
        url = git.check_output(['config', f'remote.{remote}.url'], may_fail=True)
        if url:
            output.append(f"  Remote Name:     nested/{subref}\n")

        output.append(f"  Remote URL:      {config.remote}\n")
        if upstream_head:
            output.append(f"  Upstream Ref:    {upstream_head}\n")
        output.append(f"  Tracking Branch: {config.branch}\n")
        return output

    def _status_commit_lines(self, git: GitRunner, config: NestedConfig) -> list[str]:
        """Build the pulled-commit/pull-parent status lines for one nested subdir."""
        output = []
        if config.commit:
            short = git.check_output(['rev-parse', '--short', config.commit])
            output.append(f"  Pulled Commit:   {short}\n")

        if config.parent:
            short = git.check_output(['rev-parse', '--short', config.parent])
            output.append(f"  Pull Parent:     {short}\n")
        return output

    def _status_worktree_lines(self, git: GitRunner, git_tmp: Path, subdir: Path) -> list[str]:
        """Build the worktree status line(s) for one nested subdir, if any exist."""
        worktree_list = git.check_output(['worktree', 'list'], may_fail=True) or ''
        return [f"  Worktree: {line}\n" for line in worktree_list.splitlines() if f'{git_tmp}/nested/{subdir}' in line]

    def _format_ref_line(self, git: GitRunner, subref: str, line: str) -> str | None:
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

    def format_refs(self, git: GitRunner, subref: str) -> str:
        """Format refs for status."""
        show_ref = git.check_output(['show-ref'], may_fail=True) or ''

        output = []
        for line in show_ref.splitlines():
            formatted = self._format_ref_line(git, subref, line)
            if formatted:
                output.append(formatted)

        if output:
            return "  Refs:\n" + ''.join(output)
        return ""

    def do_clean(self, git: GitRunner, flags: Flags, subdir: Path, git_tmp: Path) -> list[str]:
        """Clean nested branches and refs."""
        items = []
        subref = self.sanitize_subref(git, str(subdir))
        branch = f'nested/{subref}'
        ref = f'refs/heads/{branch}'
        subdir_worktree = git_tmp / branch

        self.remove_worktree(git, subdir_worktree)

        if git.branch_exists(branch):
            git.run(['update-ref', '-d', ref])
            items.append(f"branch '{branch}'")

        if flags.force:
            suffix = '' if flags.all else f'{subref}/'
            self._force_clean_refs(git, suffix)

        return items

    def _ref_matches_clean_target(self, ref: str, suffix: str) -> bool:
        """Check whether a ref name is one a force-clean of `suffix` should delete."""
        return ref.startswith((f'refs/nested/{suffix}', f'refs/original/refs/heads/nested/{suffix}'))

    def _force_clean_refs(self, git: GitRunner, suffix: str) -> None:
        """Delete every ref matching the nested/<suffix> prefix (the --force sweep)."""
        show_ref = git.check_output(['show-ref'], may_fail=True) or ''
        for line in show_ref.splitlines():
            parts = line.split()
            if len(parts) >= 2 and self._ref_matches_clean_target(parts[1], suffix):
                git.run(['update-ref', '-d', parts[1]])

    # -------------------------------------
    # Support Functions
    # -------------------------------------

    def guess_subdir(self, remote: str) -> str:
        """Guess subdirectory name from remote URL."""
        if not remote:
            raise GitNestedError("No remote specified for guessing subdir")
        name = Path(remote).name
        if name.endswith('.git'):
            name = name[:-4]
        return name

    def _is_valid_ref(self, git: GitRunner, ref: str) -> bool:
        """Check whether ref is already a valid git ref name (as a nested/ subref)."""
        result = git.run(['check-ref-format', f'nested/{ref}'], may_fail=True)
        return result.returncode == 0

    def _strip_forbidden_ref_chars(self, sanitized: str) -> str:
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

    def sanitize_subref(self, git: GitRunner, ref: str) -> str:
        """Sanitize subref to be a valid git ref."""
        # Check if already valid (check-ref-format succeeds), so no encoding needed
        if self._is_valid_ref(git, ref):
            return ref

        # URL encode the subdir, then remove forbidden characters
        sanitized = self._strip_forbidden_ref_chars(quote(ref, safe='/'))

        if not self._is_valid_ref(git, sanitized):
            raise GitNestedError(f"Can't determine valid subref from '{ref}'.")
        return sanitized

    def read_config(self, gitnested: Path, flags: Flags) -> NestedConfig:
        """Read .gitnested file."""
        if not gitnested.is_file():
            raise GitNestedError(f"No '{gitnested}' file.")

        config = NestedConfig.from_file(gitnested)

        # Apply explicitly given flags
        if flags.remote:
            config.remote = flags.remote
        if flags.branch:
            config.branch = flags.branch
        if flags.method:
            config.method = flags.method

        return config

    def update_gitrepo_file(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        gitnested: Path,
        upstream_head_commit: str,
        nested_commit_ref: str,
        head_commit: str,
        command: str,
    ):
        """Update .gitnested YAML file."""
        initial = not gitnested.exists()
        if initial and self._recreate_gitnested_from_parent(git, gitnested, head_commit):
            initial = False

        # Load existing data or create new
        data = self._read_yaml_config(gitnested) if gitnested.exists() else {}
        nested = data.setdefault('nested', {})

        # Update fields
        nested['commit'] = upstream_head_commit
        nested['method'] = flags.method or config.method or 'merge'
        nested['cmdver'] = VERSION
        if flags.filter:
            nested['filter'] = flags.filter

        self._update_remote_field(nested, initial, flags, config, command)
        self._update_branch_field(nested, initial, flags, config, command)
        self._update_parent_field(git, nested, head_commit, nested_commit_ref, upstream_head_commit)

        # Write YAML file and stage it
        self._write_yaml_config(gitnested, data)
        git.run(['add', '-f', '--', gitnested])

    def _recreate_gitnested_from_parent(self, git: GitRunner, gitnested: Path, head_commit: str) -> bool:
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

    def _should_update_field(self, flags_update: bool, command: str, override_value) -> bool:
        """Check if a config field should be overwritten, given --update and the command."""
        return (flags_update and override_value) or (command in ['push', 'clone'] and override_value)

    def _update_remote_field(
        self, nested: dict, initial: bool, flags: Flags, config: NestedConfig, command: str
    ) -> None:
        """Set nested['remote'] when it is initial or an override applies."""
        if initial or self._should_update_field(flags.update, command, flags.remote):
            nested['remote'] = config.remote

    def _update_branch_field(
        self, nested: dict, initial: bool, flags: Flags, config: NestedConfig, command: str
    ) -> None:
        """Set nested['branch'] when it is initial, a clone, or an override applies."""
        # For clone command, always update branch (including force reclone to different branch)
        if initial or command == 'clone' or self._should_update_field(flags.update, command, flags.branch):
            nested['branch'] = config.branch

    def _update_parent_field(
        self, git: GitRunner, nested: dict, head_commit: str, nested_commit_ref: str, upstream_head_commit: str
    ) -> None:
        """Set nested['parent'] once the nested commit has caught up with upstream."""
        if not (head_commit and nested_commit_ref):
            return
        nested_commit = git.check_output(['rev-parse', nested_commit_ref])
        if upstream_head_commit == nested_commit:
            nested['parent'] = head_commit

    # -------------------------------------
    # Checks and Validations
    # -------------------------------------

    def _check_current_branch(self, git: GitRunner, command: str) -> None:
        """Ensure a real branch (not a nested branch, not detached HEAD) is checked out."""
        current_branch = git.check_output(['symbolic-ref', '--short', '--quiet', 'HEAD'], may_fail=True)
        if current_branch.startswith('nested/'):
            raise GitNestedError(f"Can't '{command}' while a nested branch is checked out: {current_branch}")

        if not current_branch or current_branch in ['HEAD']:
            raise GitNestedError("Must be on a branch to run this command.")

    def check_repository(self, git: GitRunner, command: str) -> tuple[Path | None, str | None]:
        """Check that repository is ready.

        Returns:
            tuple: (git_tmp, head_commit)
        """
        if command in ['version']:
            return None, None

        try:
            git.run(['rev-parse', '--git-dir'])
        except GitNestedError:
            # git.run() already printed the underlying git error to stderr;
            # this is a deliberate, more user-friendly re-interpretation of
            # it, not an incidental failure, so the chain is suppressed.
            raise GitNestedError("Not inside a git repository.") from None

        git_common_dir = git.check_output(['rev-parse', '--git-common-dir'])
        git_tmp = Path(git_common_dir) / 'tmp'

        self._check_current_branch(git, command)

        inside_worktree = git.check_output(['rev-parse', '--is-inside-work-tree'], may_fail=True)
        if inside_worktree != 'true':
            raise GitNestedError("Must run inside a git working tree.")

        self.check_worktree_clean(git, command)

        parents = git.check_output(['rev-parse', '--show-prefix'], may_fail=True)
        if parents:
            raise GitNestedError("Need to run nested command from top level directory of the repo.")

        # Store the current HEAD (may fail in case of an empty repository)
        head_commit = git.check_output(['rev-parse', 'HEAD'], may_fail=True)

        return git_tmp, head_commit

    def _check_head_and_index_clean(self, git: GitRunner, command: str, pwd: Path) -> None:
        """Ensure HEAD is verifiable and the working tree/index have no pending changes."""
        if command == 'clone' and not git.rev_exists('HEAD'):
            # This may happen when cloning into an empty repository
            return

        result = git.run(['rev-parse', '--verify', 'HEAD'], may_fail=True)
        if result.returncode != 0:
            raise GitNestedError(f"HEAD cannot be verified ({pwd})")

        result = git.run(['diff-index', '--quiet', '--ignore-submodules', 'HEAD'], may_fail=True)
        if result.returncode != 0:
            raise GitNestedError(f"Can't {command} nested repository. Working tree has changes. ({pwd})")

        result = git.run(['diff-index', '--quiet', '--cached', '--ignore-submodules', 'HEAD'], may_fail=True)
        if result.returncode != 0:
            raise GitNestedError(f"Can't {command} nested repository. Index has changes. ({pwd})")

    def check_worktree_clean(self, git: GitRunner, command: str):
        """Ensure working copy has no uncommitted changes."""
        if command not in ['clone', 'init', 'pull', 'push', 'branch', 'commit', 'diff']:
            return

        pwd = Path.cwd()
        git.run(['update-index', '-q', '--ignore-submodules', '--refresh'], may_fail=True)

        # Check for unstaged changes
        result = git.run(['diff-files', '--quiet', '--ignore-submodules'], may_fail=True)
        if result.returncode != 0:
            raise GitNestedError(f"Can't {command} nested repository. Unstaged changes. ({pwd})")

        self._check_head_and_index_clean(git, command, pwd)

    def check_subdir_for_init(self, git: GitRunner, subdir: Path, gitnested: Path):
        """Check subdir is ready for init."""
        if not subdir.exists():
            raise GitNestedError(f"'{subdir}' does not exist.")

        if gitnested.exists():
            raise GitNestedError(f"'{subdir}' is already a nested repository.")

        if not git.is_tracked(subdir):
            raise GitNestedError(f"'{subdir}' exists, but nothing is tracked by git.")

    # -------------------------------------
    # Git Helpers
    # -------------------------------------

    def create_worktree(self, git: GitRunner, branch: str, git_tmp: Path) -> Path:
        """Create a worktree for the given branch."""
        subdir_worktree = git_tmp / branch
        git.run(['worktree', 'add', subdir_worktree, branch])
        return subdir_worktree

    def remove_worktree(self, git: GitRunner, worktree: Path | None):
        """Remove worktree."""
        if not worktree:
            return

        worktree_path = Path(worktree)
        if not worktree_path.is_dir():
            return

        with chdir(worktree):
            self.check_worktree_clean(git, 'clean')

        shutil.rmtree(worktree)
        git.run(['worktree', 'prune'])

    def delete_branch(self, git: GitRunner, branch: str, git_tmp: Path):
        """Delete a branch."""
        subdir_worktree = git_tmp / branch
        self.remove_worktree(git, subdir_worktree)
        git.run(['branch', '-D', branch], may_fail=True)

    # -------------------------------------
    # Utility Functions
    # -------------------------------------

    def _outermost_paths(self, paths: list[Path]) -> list[Path]:
        """Keep only the paths that are not nested inside another path in the list."""
        return [p for p in paths if not any(p.is_relative_to(other) for other in paths if p != other)]

    def find_all_nested_repositories(self, git: GitRunner, flags: Flags) -> list[Path]:
        """Find all nested repositories in repository."""
        tracked_files = git.check_output(['ls-files'])
        gitnesteds = sorted(
            Path(line).parent for line in tracked_files.splitlines() if line.endswith(GITNESTED_FILENAME)
        )
        if not flags.all_deep:
            # Filter the paths to contain only outermost nested repository paths
            gitnesteds = self._outermost_paths(gitnesteds)
        return gitnesteds

    def get_upstream_branch(self, git: GitRunner, config: NestedConfig) -> str:
        """Determine upstream default branch."""
        remote_branches = git.check_output(['ls-remote', '--symref', config.remote], may_fail=True)
        if not remote_branches:
            raise GitNestedError(f"Command failed: 'git ls-remote --symref {config.remote}'.")
        upstream_branch = re.search(r"^ref:\s+refs/heads/(\S+)\s+HEAD", remote_branches, re.MULTILINE)
        if not upstream_branch:
            raise GitNestedError("Problem finding remote default head branch.")
        return upstream_branch.group(1)

    def get_default_branch(self, git: GitRunner) -> str:
        """Get git's default branch name."""
        default_branch = git.check_output(['config', '--get', 'init.defaultbranch'], may_fail=True)
        if default_branch:
            return default_branch
        return "main"

    def build_commit_message(
        self,
        git: GitRunner,
        config: NestedConfig,
        upstream_head_commit: str,
        nested_commit_ref: str,
        subdir: Path,
        command: str,
    ) -> str:
        """Generate commit message."""
        upstream_commit = 'none'
        if upstream_head_commit:
            upstream_commit = git.check_output(['rev-parse', '--short', upstream_head_commit])
        commit = git.check_output(['rev-parse', '--short', nested_commit_ref])
        return textwrap.dedent(
            f"""\
            git nested {command}

            nested:
              subdir:   "{subdir}"
              merged:   "{commit}"
            upstream:
              remote:   "{config.remote}"
              branch:   "{config.branch}"
              commit:   "{upstream_commit}"
            git-nested:
              version:  "{VERSION}"
            """
        )


class GitNestedCommand:
    """Handles command-line interface and user I/O."""

    def __init__(self):
        """Wire up the git runner and repo/business-logic layer."""
        self.git = GitRunner()
        self.repo = GitNestedRepo()
        # For backward compatibility with tests
        self.flags = Flags()

    # -------------------------------------
    # User I/O methods
    # -------------------------------------

    def verbose(self, msg: str, flags: Flags | None = None):
        """Print verbose messages."""
        flags = flags or self.flags
        if flags.verbose:
            self.say(f"* {msg}", flags)

    def say(self, msg: str, flags: Flags | None = None):
        """Print message unless quiet."""
        flags = flags or self.flags
        if not flags.quiet:
            print(msg)

    def error(self, msg: str):
        """Print error and exit."""
        print(f"git-nested: {msg}", file=sys.stderr)
        raise GitNestedError(msg, print_to_stderr=False)

    def usage_error(self, msg: str):
        """Print usage error and exit."""
        print(f"git-nested: {msg}", file=sys.stderr)
        sys.exit(1)

    # -------------------------------------
    # main
    # -------------------------------------

    def _dispatch_all(self, command, flags, upstream, nested_commit_ref, git_tmp, head_commit):
        """Dispatch command across every nested repository (the --all flag)."""
        if flags.branch:
            self.error("options --branch and --all are not compatible")

        nesteds = self.repo.find_all_nested_repositories(self.git, flags)
        for subdir_path in nesteds:
            self.dispatch_command(command, flags, subdir_path, upstream, nested_commit_ref, git_tmp, head_commit)

    def main(self, args):
        """Main entry point."""
        command, flags, subdir, upstream, nested_commit_ref = self.parse_args(args)
        self.git.check()
        git_tmp, head_commit = self.repo.check_repository(self.git, command)

        if flags.all and command not in ['status']:
            self._dispatch_all(command, flags, upstream, nested_commit_ref, git_tmp, head_commit)
        else:
            self.dispatch_command(command, flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit)

    # (option name in valid_command_options, argparse flag names, argparse kwargs)
    _SUBPARSER_ARG_SPECS: ClassVar[list[tuple[str, tuple[str, ...], dict]]] = [
        ('all', ('-a', '--all'), {'action': 'store_true', 'dest': 'all_flag'}),
        ('ALL', ('-A', '--ALL'), {'action': 'store_true', 'dest': 'ALL_flag'}),
        ('branch', ('-b', '--branch'), {'dest': 'branch'}),
        ('commit', ('-c', '--commit'), {'action': 'store_true'}),
        ('force', ('-f', '--force'), {'action': 'store_true'}),
        ('filter', ('--filter',), {'action': 'append'}),
        ('fetch', ('-F', '--fetch'), {'action': 'store_true', 'dest': 'fetch_flag'}),
        ('method', ('-M', '--method'), {'dest': 'method'}),
        ('message', ('-m', '--message'), {'dest': 'message'}),
        ('msg_file', ('--file',), {'dest': 'msg_file'}),
        ('remote', ('-r', '--remote'), {'dest': 'remote'}),
        ('squash', ('-s', '--squash'), {'action': 'store_true'}),
        ('update', ('-u', '--update'), {'action': 'store_true'}),
    ]

    # (option name in args namespace, attribute name on Flags)
    _SUPPORTED_OPT_ATTRS: ClassVar[list[tuple[str, str]]] = [
        ('branch', 'branch'),
        ('remote', 'remote'),
        ('method', 'method'),
        ('message', 'message'),
        ('msg_file', 'message_file'),
    ]

    def _add_subparser_args(self, command_subparser, command: str, valid_command_options: dict) -> None:
        """Add the flag arguments supported by one command to its subparser."""
        opts = valid_command_options[command]
        for opt, arg_names, kwargs in self._SUBPARSER_ARG_SPECS:
            if opt in opts:
                command_subparser.add_argument(*arg_names, **kwargs)

    def _add_subparser_positionals(self, command_subparser, command: str) -> None:
        """Add the positional arguments supported by one command to its subparser."""
        if command in ('branch', 'commit', 'diff', 'fetch', 'init', 'pull', 'push', 'clean'):
            command_subparser.add_argument('subdir', nargs='?')
        if command == 'clone':
            command_subparser.add_argument('upstream')
            command_subparser.add_argument('subdir', nargs='?')
        if command == 'commit':
            command_subparser.add_argument('nested_commit_ref', nargs='?')
        if command == 'push':
            command_subparser.add_argument('nested_branch', nargs='?')

    def _build_arg_parser(self):
        """Build the top-level argument parser and all per-command subparsers.

        Returns:
            tuple: (parser, valid_command_options)
        """
        parser = argparse.ArgumentParser(prog='git nested')
        parser.add_argument('--version', action='store_true')
        parser.add_argument('-q', '--quiet', action='store_true')
        parser.add_argument('-v', '--verbose', action='count')

        valid_command_options = {
            'branch': ['all', 'fetch', 'force'],
            'clean': ['ALL', 'all', 'force'],
            'clone': ['branch', 'filter', 'force', 'message', 'method', 'filter'],
            'commit': ['fetch', 'force', 'message', 'msg_file'],
            'diff': ['all', 'branch', 'remote'],
            'fetch': ['all', 'branch', 'force', 'remote'],
            'init': ['branch', 'remote', 'method'],
            'pull': ['all', 'branch', 'force', 'message', 'method', 'remote', 'update'],
            'push': ['all', 'branch', 'commit', 'force', 'message', 'method', 'msg_file', 'remote', 'squash', 'update'],
            'status': ['ALL', 'all', 'fetch'],
            'version': [],
        }

        subparsers = parser.add_subparsers(dest='command')
        command_subparsers = {command: subparsers.add_parser(command) for command in valid_command_options}

        for command in valid_command_options:
            command_subparser = command_subparsers[command]
            self._add_subparser_args(command_subparser, command, valid_command_options)
            # Few commands also accept positional args
            self._add_subparser_positionals(command_subparser, command)

        return parser, valid_command_options

    def _resolve_positional_args(self, args):
        """Resolve upstream/subdir/nested_commit_ref from parsed args.

        Returns:
            tuple: (upstream, subdir, nested_commit_ref)
        """
        upstream = getattr(args, 'upstream', None)
        subdir = getattr(args, 'subdir', None)
        # 'commit's positional is named nested_commit_ref, 'push's is nested_branch --
        # only one of the two is ever present on args, depending on the subcommand.
        nested_commit_ref = getattr(args, 'nested_commit_ref', None) or getattr(args, 'nested_branch', None)

        if upstream and not subdir:
            subdir = self.repo.guess_subdir(upstream)

        return upstream, subdir, nested_commit_ref

    def _supported_and_set(self, args, opts: list | None, opt: str) -> bool:
        """Check whether opt is valid for the current command and was actually provided."""
        return opt in (opts or []) and getattr(args, opt, None) is not None

    def _apply_supported_options(self, args, flags: Flags, valid_command_options: dict) -> None:
        """Copy option values from args to flags when supported by the command and set."""
        opts = valid_command_options.get(args.command)
        for opt, flag_attr in self._SUPPORTED_OPT_ATTRS:
            if self._supported_and_set(args, opts, opt):
                setattr(flags, flag_attr, getattr(args, opt))

    def _validate_message_options(self, args, valid_command_options: dict) -> None:
        """Validate that -m/--file usage is consistent for the current command."""
        opts = valid_command_options.get(args.command)
        msg_file_set = self._supported_and_set(args, opts, 'msg_file')
        if msg_file_set and not Path(args.msg_file).is_file():
            self.error(f"Commit msg file at {args.msg_file} not found")
        if msg_file_set and self._supported_and_set(args, opts, 'message'):
            self.error("fatal: options '-m' and '--file' cannot be used together")

    def _flags_from_args(self, args, valid_command_options: dict) -> Flags:
        """Build a Flags object from parsed args, applying per-command option support rules."""
        flags = Flags()
        flags.all = getattr(args, 'all_flag', False)
        flags.all_deep = getattr(args, 'ALL_flag', False)
        flags.commit = getattr(args, 'commit', False)
        flags.filter = getattr(args, 'filter', [])
        flags.force = getattr(args, 'force', False)
        flags.fetch = getattr(args, 'fetch_flag', False)
        flags.squash = getattr(args, 'squash', False)
        flags.update = getattr(args, 'update', False)
        flags.quiet = getattr(args, 'quiet', False)
        flags.verbose = getattr(args, 'verbose', 0)

        if flags.all_deep:
            flags.all = True

        self._apply_supported_options(args, flags, valid_command_options)
        self._validate_message_options(args, valid_command_options)

        return flags

    def parse_args(self, args_list):
        """Parse command line arguments.

        Returns:
            tuple: (command, flags, subdir, upstream, nested_commit_ref)
        """
        parser, valid_command_options = self._build_arg_parser()

        # parse arguments
        # Note: subparsers handle positional and optional arguments for each command
        args = parser.parse_args(args_list)

        if args.version:
            args.command = 'version'

        if not args.command:
            self.usage_error("Missing command")

        upstream, subdir, nested_commit_ref = self._resolve_positional_args(args)
        flags = self._flags_from_args(args, valid_command_options)

        if flags.update and not (flags.branch or flags.remote):
            self.usage_error("Can't use '--update' without '--branch' or '--remote'.")

        return args.command, flags, subdir, upstream, nested_commit_ref

    def dispatch_command(self, command, flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit):
        """Dispatch to command function."""
        commands = {
            'clone': lambda: self.cmd_clone(flags, subdir, upstream, head_commit),
            'init': lambda: self.cmd_init(flags, subdir, upstream, head_commit),
            'pull': lambda: self.cmd_pull(flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit),
            'push': lambda: self.cmd_push(flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit),
            'fetch': lambda: self.cmd_fetch(flags, subdir, upstream),
            'diff': lambda: self.cmd_diff(flags, subdir, upstream),
            'branch': lambda: self.cmd_branch(flags, subdir, upstream, git_tmp),
            'commit': lambda: self.cmd_commit(flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit),
            'status': lambda: self.cmd_status(flags, git_tmp),
            'clean': lambda: self.cmd_clean(flags, subdir, upstream, git_tmp),
            'version': lambda: self.cmd_version(),
        }

        func = commands.get(command)
        if func:
            func()
        else:
            self.usage_error(f"Unknown command: {command}")

    # -------------------------------------
    # Commands
    # -------------------------------------

    def cmd_clone(self, flags, subdir, upstream, head_commit):
        """Clone a remote repository into a local subdirectory."""
        subdir, gitnested, subref, config = self.setup_command('clone', flags, subdir, upstream)

        up_to_date, config, nested_commit_ref, upstream_head_commit = self.repo.do_clone(
            git=self.git,
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
            self.verbose(f"Commit the new '{subdir}/' content.", flags)
            self.repo.commit_nested_branch(
                git=self.git,
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
            self.say(f"Nested repository '{subdir}' is up to date with upstream branch '{config.branch}'.", flags)
        else:
            self.say(f"Nested repository '{config.remote}' ({config.branch}) cloned into '{subdir}'.", flags)

    def cmd_init(self, flags, subdir, upstream, head_commit):
        """Initialize a subdirectory as a nested repo."""
        subdir, gitnested, subref, config = self.setup_command('init', flags, subdir, upstream)

        # Set defaults
        config.remote = config.remote or 'none'
        config.branch = config.branch or self.repo.get_default_branch(self.git)

        self.repo.do_init(
            git=self.git,
            flags=flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            head_commit=head_commit,
            subref=subref,
        )

        remote_msg = (
            "(with no remote)." if config.remote == 'none' else f"with remote '{config.remote}' ({config.branch})."
        )
        self.say(f"Nested repository created from '{subdir}' {remote_msg}", flags)

    def _pull_forced(self, flags, subdir, gitnested, subref, config, head_commit) -> None:
        """Handle cmd_pull's `--force` path: reclone via do_clone, committing the result if needed."""
        up_to_date, config, nested_commit_ref, upstream_head_commit = self.repo.do_clone(
            git=self.git,
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
            self.repo.commit_nested_branch(
                git=self.git,
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
        self.say(f"Nested repository '{subdir}' pulled from '{config.remote}' ({config.branch}).", flags)

    def _build_pull_conflict_help(self, subdir, subdir_worktree, method, flags, subref) -> str:
        """Build the operator-facing help text shown when a pull's merge/rebase conflicts."""
        branch_name = f'nested/{subref}'
        rebase_step = "git rebase --continue" if method == 'rebase' else "git commit"
        commit_cmd = (
            f"git nested commit --file={flags.message_file} {subdir}"
            if flags.message_file
            else f"git nested commit {subdir}"
        )
        rebase_note = ""
        if method == 'rebase':
            rebase_note = textwrap.dedent(
                f"""

                After you have performed the steps above you can push your local changes
                without repeating the rebase by:
                  1. git nested push {subdir} {branch_name}
                """
            )
        return textwrap.dedent(
            f"""\
            You will need to finish the pull by hand. A new working tree has been
            created at {subdir_worktree} so that you can resolve the conflicts
            shown in the output above.

            This is the common conflict resolution workflow:

              1. cd {subdir_worktree}
              2. Resolve the conflicts (see "git status").
              3. "git add" the resolved files.
              4. {rebase_step}
              5. If there are more conflicts, restart at step 2.
              6. cd {Path.cwd()}
              7. {commit_cmd}
            {rebase_note}
            See "git help {method}" for details.

            Alternatively, you can abort the pull and reset back to where you started:

              1. git nested clean {subdir}

            See "git help nested" for more help.
            """
        )

    def cmd_pull(self, flags, subdir, upstream, _nested_commit_ref, git_tmp, head_commit):
        """Pull upstream changes to the nested repo.

        _nested_commit_ref is unused: unlike push/commit, pull has no positional argument
        that populates it, but dispatch_command() calls every cmd_* with the same signature.
        """
        subdir, gitnested, subref, config = self.setup_command('pull', flags, subdir, upstream)

        if flags.force:
            self._pull_forced(flags, subdir, gitnested, subref, config, head_commit)
            return

        success, pulled_commit_ref, subdir_worktree, error_msg = self.repo.do_pull(
            git=self.git,
            flags=flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            git_tmp=git_tmp,
            subref=subref,
        )

        if not success and pulled_commit_ref is None:
            self.say(f"Nested repository '{subdir}' is up to date with upstream branch '{config.branch}'.", flags)
            return

        if not success:
            # do_pull's only other failure path (merge/rebase conflict) always pairs a
            # non-None pulled_commit_ref, subdir_worktree, and error_msg together.
            # _handle_pull_conflict() never returns: it always exits or raises.
            self._handle_pull_conflict(subdir, subdir_worktree, error_msg, config, flags, subref)

        self._finalize_successful_pull(
            flags, subdir, gitnested, subref, config, pulled_commit_ref, subdir_worktree, head_commit
        )

    def _handle_pull_conflict(self, subdir, subdir_worktree, error_msg, config, flags, subref) -> None:
        """Report a pull's merge/rebase conflict and exit, per do_pull's failure path."""
        if error_msg is None:
            raise AssertionError(
                'do_pull returned error_msg=None with success=False and nested_commit_ref set'
            )  # pragma: no cover -- invariant guard, unreachable via the public API
        # Print the error message to stdout
        self.say(error_msg, flags)
        # Merge/rebase failed
        method = flags.method or config.method
        msg = self._build_pull_conflict_help(subdir, subdir_worktree, method, flags, subref)
        print(msg, file=sys.stderr)
        sys.exit(1)

    def _finalize_successful_pull(
        self, flags, subdir, gitnested, subref, config, nested_commit_ref, subdir_worktree, head_commit
    ) -> None:
        """Commit a successfully-pulled nested branch and report success.

        do_pull's success path always pairs non-None nested_commit_ref and subdir_worktree.
        """
        if nested_commit_ref is None or subdir_worktree is None:
            raise AssertionError(
                'do_pull returned success=True without nested_commit_ref/subdir_worktree set'
            )  # pragma: no cover -- invariant guard, unreachable via the public API
        self.verbose(f"Commit the new '{nested_commit_ref}' content.", flags)
        upstream_head_commit = self.git.check_output(['rev-parse', f'refs/nested/{subref}/fetch'])
        self.repo.commit_nested_branch(
            git=self.git,
            flags=flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            nested_commit_ref=nested_commit_ref,
            upstream_head_commit=upstream_head_commit,
            head_commit=head_commit,
            subdir_worktree=subdir_worktree,
            command='pull',
        )
        self.say(f"Nested repository '{subdir}' pulled from '{config.remote}' ({config.branch}).", flags)

    def cmd_push(self, flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit):
        """Push local nested repo changes upstream."""
        subdir, gitnested, subref, config = self.setup_command('push', flags, subdir, upstream)

        self.verbose(f"Pushing {subdir} to upstream", flags)
        success, branch_name, subdir_worktree, branch_created, new_commit = self.repo.do_push(
            git=self.git,
            flags=flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            git_tmp=git_tmp,
            subref=subref,
            branch=nested_commit_ref,
        )

        if self._handle_push_failure(success, subdir_worktree, subdir, flags):
            return

        # do_push only returns success=True together with a non-None new_commit
        # (the None case is paired exclusively with success=False above).
        if new_commit is None:
            raise AssertionError(
                'do_push returned success=True with new_commit=None'
            )  # pragma: no cover -- invariant guard, unreachable via the public API

        if branch_created:
            self.verbose(f"Remove branch 'nested/{subref}'.", flags)
            self.repo.delete_branch(self.git, f'nested/{subref}', git_tmp)

        # Update .gitnested if --commit or if --remote/--branch specified
        if flags.commit:
            self._record_push_commit(flags, subdir, gitnested, config, new_commit, head_commit)

        self.say(
            f"Nested repository '{subdir}' pushed to '{config.remote}' ({branch_name}).",
            flags,
        )

    def _handle_push_failure(self, success, subdir_worktree, subdir, flags) -> bool:
        """Handle a failed do_push call (rebase failure or nothing to push).

        Returns:
            True if the caller should stop (push did not succeed), else False.
        """
        if not success and subdir_worktree:
            # Rebase failed
            self.say('The "git rebase" command failed', flags)
            sys.exit(1)

        if not success:
            self.say(f"Nested repository '{subdir}' has no new commits to push.", flags)
            return True

        return False

    def _record_push_commit(self, flags, subdir, gitnested, config, new_commit, head_commit):
        """Update `.gitnested` and create a commit recording the push (the --commit flag)."""
        self.verbose(f"Put updates into '{subdir}/.gitnested' file.", flags)

        self.repo.update_gitrepo_file(
            git=self.git,
            flags=flags,
            config=config,
            gitnested=gitnested,
            upstream_head_commit=new_commit,
            nested_commit_ref=new_commit,
            head_commit=head_commit,
            command='push',
        )

        msg = flags.message or self.repo.build_commit_message(
            git=self.git,
            config=config,
            upstream_head_commit=new_commit,
            nested_commit_ref=new_commit,
            subdir=subdir,
            command='push',
        )

        if flags.message_file:
            self.git.run(['commit', '--file', flags.message_file])
        else:
            self.git.run(['commit', '-m', msg])

    def cmd_fetch(self, flags, subdir, upstream):
        """Fetch a nested repo's remote branch."""
        subdir, _, subref, config = self.setup_command('fetch', flags, subdir, upstream)

        if config.remote == 'none':
            self.say(f"Ignored '{subdir}', no remote.", flags)
        else:
            self.repo.do_fetch(self.git, flags, config, subref)
            self.say(f"Fetched '{subdir}' from '{config.remote}' ({config.branch}).", flags)

    def cmd_diff(self, flags, subdir, upstream):
        """Show the local diff of a nested repo compared to upstream."""
        subdir, _gitnested, subref, config = self.setup_command('diff', flags, subdir, upstream)

        if config.remote == 'none':
            self.say(f"Ignored '{subdir}', no remote.", flags)
            return

        diff_output = self.repo.get_diff(self.git, flags, config, subdir, subref)

        if not diff_output:
            self.say(f"No differences between '{subdir}' and upstream '{config.remote}' ({config.branch}).", flags)
        else:
            self.say(diff_output, flags)

    def cmd_branch(self, flags, subdir, upstream, git_tmp):
        """Create a branch containing the local nested repo commits."""
        subdir, gitnested, subref, config = self.setup_command('branch', flags, subdir, upstream)

        if flags.fetch:
            self.repo.do_fetch(self.git, flags, config, subref)

        branch = f'nested/{subref}'
        if flags.force:
            self.repo.delete_branch(self.git, branch, git_tmp)
        elif self.git.branch_exists(branch):
            self.error(f"Branch '{branch}' already exists. Use '--force' to override.")

        subdir_worktree = self.repo.create_nested_branch(
            git=self.git,
            flags=flags,
            config=config,
            branch=branch,
            subdir=subdir,
            gitnested=gitnested,
            git_tmp=git_tmp,
            subref=subref,
            command='branch',
        )
        self.say(f"Created branch '{branch}' and worktree '{subdir_worktree}'.", flags)

    def cmd_commit(self, flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit):
        """Commit a merged nested branch."""
        subdir, gitnested, subref, config = self.setup_command('commit', flags, subdir, upstream)

        if flags.fetch:
            self.repo.do_fetch(self.git, flags, config, subref)

        refs_fetch = f'refs/nested/{subref}/fetch'
        if not self.git.rev_exists(refs_fetch):
            self.error(f"Can't find ref '{refs_fetch}'. Try using -F.")

        upstream_head_commit = self.git.check_output(['rev-parse', refs_fetch])
        nested_commit_ref = nested_commit_ref or f'nested/{subref}'

        self.repo.commit_nested_branch(
            git=self.git,
            flags=flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            nested_commit_ref=nested_commit_ref,
            upstream_head_commit=upstream_head_commit,
            head_commit=head_commit,
            subdir_worktree=git_tmp / f'nested/{subref}',
            command='commit',
        )
        self.say(f"Nested commit '{nested_commit_ref}' committed as subdir '{subdir}/' to current branch.", flags)

    def cmd_status(self, flags, git_tmp):
        """Get status of a nested repo (or all of them)."""
        output, _ = self.repo.get_status(self.git, flags, git_tmp)
        self.say(output, flags)

    def cmd_clean(self, flags, subdir, upstream, git_tmp):
        """Remove branches, remotes and refs for a nested repo."""
        subdir, _, _, _ = self.setup_command('clean', flags, subdir, upstream)

        for item in self.repo.do_clean(self.git, flags, subdir, git_tmp):
            self.say(f"Removed {item}.", flags)

    def cmd_version(self):
        """Print version information."""
        print(f"git-nested Version: {VERSION}")
        print("Copyright 2026 Thorsten Klein <thorsten.klein.git@gmail.com>")
        print("https://github.com/thorsten-klein/git-nested")
        print(Path(__file__).resolve())
        print(f"Git Version: {self.git.get_version()}")

    # -------------------------------------
    # Setup
    # -------------------------------------

    def setup_command(self, command, flags, subdir, upstream):
        """Setup command with parameters.

        Returns:
            tuple: (subdir, gitnested, subref, config)
        """
        if not subdir:
            self.error("subdir not set")

        subdir = Path(subdir)

        # Check for absolute path
        if subdir.is_absolute():
            self.usage_error(f"The subdir '{subdir}' should not be absolute path.")

        subref = self.repo.sanitize_subref(self.git, str(subdir))

        # Determine the appropriate .gitnested file to use by detecting existing level files
        gitnested = self._resolve_gitnested_file(subdir, flags)

        # Check for existing worktree
        if not flags.force:
            self._check_existing_worktree(flags, command, subdir, gitnested)

        # Read .gitnested file if exists
        config = self._load_config_for_setup(command, gitnested, flags, upstream)

        # Apply overrides (from command line flags)
        if flags.remote:
            config.remote = flags.remote
        if flags.branch:
            config.branch = flags.branch

        return subdir, gitnested, subref, config

    def _resolve_gitnested_file(self, subdir: Path, flags: Flags) -> Path:
        """Determine the .gitnested (or highest .gitnested.levelN) file to use for subdir."""
        gitnested = subdir / GITNESTED_FILENAME

        # Search for .gitnested.levelN files to determine the correct level
        level_files = sorted([
            f
            for f in subdir.glob(f'{GITNESTED_LEVEL_PREFIX}*')
            if f.is_file() and f.name.startswith(GITNESTED_LEVEL_PREFIX)
        ])

        if level_files:
            # Use the highest level file found (for deeply nested repos)
            gitnested = level_files[-1]
            self.verbose(f"Using {gitnested} for nested repository (detected from existing level files)", flags)

        return gitnested

    def _check_existing_worktree(self, flags: Flags, command: str, subdir: Path, gitnested: Path) -> None:
        """Error out if an existing worktree for subdir conflicts with this command."""
        self.verbose(f"Check for worktree with branch nested/{subdir}", flags)
        worktree_list = self.git.check_output(['worktree', 'list'], may_fail=True) or ''
        worktree_path = self._find_worktree_path(worktree_list, subdir)
        has_worktree = worktree_path is not None

        if command in ['commit'] and not has_worktree:
            self.error("There is no worktree available, use the branch command first")
        elif command not in ['branch', 'clean', 'commit', 'push'] and has_worktree:
            self._error_existing_worktree(subdir, gitnested, worktree_path)

    def _find_worktree_path(self, worktree_list: str, subdir: Path) -> str | None:
        """Find the worktree path whose branch matches nested/subdir, if one exists."""
        for line in worktree_list.splitlines():
            if f'[nested/{subdir}]' in line:
                return line.split()[0]
        return None

    def _error_existing_worktree(self, subdir: Path, gitnested: Path, worktree_path: str | None) -> None:
        """Raise the appropriate 'worktree already exists' error message."""
        if gitnested.exists():
            self.error(
                textwrap.dedent(
                    f"""\
                There is already a worktree with branch nested/{subdir}.
                Use the --force flag to override this check or perform a nested clean
                to remove the worktree."""
                )
            )
        else:
            self.error(
                textwrap.dedent(
                    f"""\
                There is already a worktree with branch nested/{subdir}.
                Use the --force flag to override this check or remove the worktree with
                1. rm -rf {worktree_path}
                2. git worktree prune
                """
                )
            )

    def _load_config_for_setup(self, command: str, gitnested: Path, flags: Flags, upstream: str | None) -> NestedConfig:
        """Load the existing .gitnested config, or initialize a fresh one for clone/init."""
        if command not in ['clone', 'init']:
            return self.repo.read_config(gitnested, flags)
        config = NestedConfig()
        if upstream:
            config.remote = upstream
        return config


def main():
    """Main entry point."""
    try:
        app = GitNestedCommand()
        app.main(sys.argv[1:])
    except GitNestedError:
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


# Backward compatibility alias
GitNested = GitNestedCommand


if __name__ == '__main__':  # pragma: no cover -- exercised only when run as a script, not on import
    main()
