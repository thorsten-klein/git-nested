#!/usr/bin/env python3
"""
git-nested - Git Submodule Alternative

Copyright 2026 - Thorsten Klein <thorsten.klein.git@gmail.com>
"""

import contextlib
import sys
import os
import subprocess
import argparse
import re
import shutil
import textwrap
import yaml
from pathlib import Path
from typing import List
from dataclasses import dataclass
from urllib.parse import quote

VERSION = "1.0.0"
REQUIRED_GIT_VERSION = "2.23.0"


@contextlib.contextmanager
def chdir(path):
    """
    Backport of contextlib.chdir stdlib class added in Python 3.11.
    The current working directory is temporarily changed to given path
    for the duration of the `with` block. When the block exits, the
    working directory is restored to its original value.
    """
    oldpwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(oldpwd)


class GitNestedError(Exception):
    """Base exception for git-nested errors"""

    def __init__(self, message, print_to_stderr=True):
        self.message = message
        if print_to_stderr:
            print(f"git-nested: {message}", file=sys.stderr)
        super().__init__(self.message)


@dataclass
class Flags:
    """Command-line flags"""

    all: bool = False
    ALL: bool = False
    branch: None | str = None
    commit: bool = False
    filter: None | list[str] = None
    force: bool = False
    fetch: bool = False
    message: None | str = None
    message_file: None | str = None
    method: None | str = None
    remote: None | str = None
    squash: bool = False
    update: bool = False
    quiet: bool = False
    verbose: int = 0


@dataclass
class NestedConfig:
    """Nested configuration from .gitnested file"""

    remote: str = ''
    branch: str = ''
    commit: str = ''
    filter: None | list[str] = None
    parent: str = ''
    method: str = 'merge'

    @classmethod
    def from_file(cls, filepath: str):
        """Read config from .gitnested YAML file"""
        path = Path(filepath)
        if not path.is_file():
            raise GitNestedError(f"No '{filepath}' file.")
        with path.open('r') as f:
            data = yaml.safe_load(f) or {}
        nested_data = data.get('nested', {})

        config = cls()
        config.remote = nested_data.get('remote', '')
        config.branch = nested_data.get('branch', '')
        config.commit = nested_data.get('commit', '')
        config.filter = nested_data.get('filter', None)
        config.parent = nested_data.get('parent', '')
        method = nested_data.get('method', 'merge')
        config.method = 'rebase' if method == 'rebase' else 'merge'

        if not config.remote:
            raise GitNestedError(f"Missing required 'remote' in '{filepath}'.")
        if not config.branch:
            raise GitNestedError(f"Missing required 'branch' in '{filepath}'.")

        return config


class GitRunner:
    """Simplified git command execution"""

    def __init__(self):
        self.check()
        self.version = self.get_version()

    def run(self, args: List[str], may_fail=False, print_error=True, **kwargs) -> subprocess.CompletedProcess:
        """Run git command"""
        # Convert any Path objects to strings
        cmd = ['git'] + [str(arg) for arg in args]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)
        if result.returncode != 0:
            if not may_fail:
                raise GitNestedError(
                    f"Command failed: '{' '.join(cmd)}'.\n{str(result.stderr)}", print_to_stderr=print_error
                )

            # Exception occurred but may_fail=True: Create a fake CompletedProcess for exception case
            return subprocess.CompletedProcess(args=cmd, returncode=-1, stdout=result.stdout, stderr=result.stderr)

        # Command succeeded
        return result

    def check_output(self, args: List[str], may_fail=False, **kwargs) -> str:
        result = self.run(args=args, may_fail=may_fail, **kwargs)
        return result.stdout.strip()

    def is_tracked(self, path: Path) -> bool:
        """Check if given path is tracked by git"""
        result = self.run(['ls-files', '--', path], may_fail=True)
        return result.returncode == 0

    def rev_exists(self, rev: str) -> bool:
        """Check if revision exists"""
        result = self.run(['rev-list', rev, '-1'], may_fail=True)
        return result.returncode == 0

    def branch_exists(self, branch: str) -> bool:
        """Check if branch exists"""
        return self.rev_exists(f'refs/heads/{branch}')

    def commit_in_rev_list(self, commit: str, list_head: str) -> bool:
        """Check if commit is in rev-list (i.e., is an ancestor)"""
        result = self.run(['merge-base', '--is-ancestor', commit, list_head], may_fail=True)
        return result.returncode == 0

    def check(self):
        """Check that environment is suitable"""
        if not shutil.which('git'):
            raise GitNestedError("Can't find 'git' in PATH env variable.")
        version = self.get_version()

        def Version(v):
            return tuple(map(int, (v.split("."))))

        if not Version(version) >= Version(REQUIRED_GIT_VERSION):
            raise GitNestedError(f"Requires git version {REQUIRED_GIT_VERSION} or higher; you have '{version}'.")

    def get_version(self):
        git_version = self.check_output(['--version'])
        m = re.search(r'(\d+\.\d+\.\d+)', git_version)
        if not m:
            raise GitNestedError("Can't determine git version")
        return m.group(1)


class GitNestedRepo:
    """Handles repository operations and business logic"""

    def __init__(self):
        pass

    # -------------------------------------
    # Logging helpers (delegated to maintain separation)
    # -------------------------------------

    def verbose(self, msg: str, flags: Flags):
        """Print verbose messages"""
        if flags.verbose:
            print(f"* {msg}")

    def say(self, msg: str, flags: Flags):
        """Print message unless quiet"""
        if not flags.quiet:
            print(msg)

    # -------------------------------------
    # Helper methods
    # -------------------------------------

    def _read_yaml_config(self, filepath: Path) -> dict:
        """Read YAML configuration file"""
        with filepath.open('r') as f:
            return yaml.safe_load(f) or {}

    def _write_yaml_config(self, filepath: Path, data: dict) -> str:
        """Write YAML configuration file with header"""
        GITREPO_HEADER = textwrap.dedent("""\
            # This subdirectory is managed by "git nested".
            # Refer to: https://github.com/thorsten-klein/git-nested#readme
            #
            """)
        with filepath.open('w') as f:
            f.write(GITREPO_HEADER)
            return yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def create_nested_ref(self, git: GitRunner, subref: str, ref_type: str, commit: str):
        """Create a git ref pointing to commit"""
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
    ) -> tuple[bool, NestedConfig, str, str]:
        """Clone implementation

        Returns:
            tuple: (up_to_date, updated_config, nested_commit_ref, upstream_head_commit)
        """
        # Check if we can clone (fail if HEAD doesn't exist)
        if not git.rev_exists('HEAD'):
            raise GitNestedError("You can't clone into an empty repository")

        # Turn off force unless really a reclone
        force = flags.force
        if force and not gitnested.is_file():
            force = False

        branch = flags.branch
        if force:
            upstream_head_commit = self.do_fetch(git, flags, config, subref)
            config = self.read_config(gitnested, flags)

            self.verbose("Check if we already are up to date.", flags)
            if upstream_head_commit == config.commit:
                return True, config, None, upstream_head_commit

            self.verbose("Remove the existing subdir.", flags)
            git.run(['rm', '-r', '--', subdir])

            if not branch:
                self.verbose("Determine the upstream head branch.", flags)
                config.branch = self.get_upstream_branch(git, config)
                branch = config.branch
                # Fetch again from the new branch
                upstream_head_commit = self.do_fetch(git, flags, config, subref)
        else:
            if subdir.exists() and any(subdir.iterdir()):
                raise GitNestedError(f"The subdir '{subdir}' exists and is not empty.")

            if not config.branch:
                self.verbose("Determine the upstream head branch.", flags)
                config.branch = self.get_upstream_branch(git, config)

            upstream_head_commit = self.do_fetch(git, flags, config, subref)

        if flags.filter:
            config.filter = flags.filter

        self.verbose(f"Make the directory '{subdir}/' for the clone.", flags)
        subdir.mkdir(parents=True, exist_ok=True)

        nested_commit_ref = upstream_head_commit
        return False, config, nested_commit_ref, upstream_head_commit

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
        """Initialize a nested repository

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
    ) -> tuple[bool, str, Path, str]:
        """Pull implementation

        Returns:
            tuple: (success, nested_commit_ref, subdir_worktree, error_msg)
        """
        upstream_head_commit = self.do_fetch(git, flags, config, subref)

        if flags.force:
            # Force reclone - handled by caller
            return True, None, None, None

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
        refs_fetch = f'refs/nested/{subref}/fetch'

        try:
            if method == 'rebase':
                git.run(['rebase', refs_fetch, branch], cwd=subdir_worktree, print_error=False)
            else:
                git.run(['merge', refs_fetch], cwd=subdir_worktree, print_error=False)
        except GitNestedError as e:
            # Merge/rebase failed - return failure with error message
            error_msg = f'The "git {method}" command failed:\n{e.message}'
            return False, nested_commit_ref, subdir_worktree, error_msg

        self.create_nested_ref(git, subref, 'branch', branch)

        return True, nested_commit_ref, subdir_worktree, None

    def do_push(
        self,
        git: GitRunner,
        flags: Flags,
        config: NestedConfig,
        subdir: Path,
        gitnested: Path,
        git_tmp: Path,
        subref: str,
        branch: str = None,
    ) -> tuple[bool, str, Path, bool, str]:
        """Push implementation

        Returns:
            tuple: (success, branch_name, subdir_worktree, branch_created, new_commit)
        """
        new_upstream = False
        branch_created = False

        # Calculate the resulting branch name
        branch_name = flags.branch
        if not branch_name:
            toplevel = git.check_output(['rev-parse', '--show-toplevel'])
            repo_name = Path(toplevel).name
            branch_name = f"{repo_name}-{config.branch}"

        upstream_head_commit = None
        if not branch:
            # Fetch the resulting branch automatically first
            result = git.run(['fetch', '--no-tags', '--quiet', config.remote, branch_name], may_fail=True)
            if result.returncode != 0:
                stderr = result.stderr
                if re.search(r"(^|\n)fatal: couldn't find remote ref ", stderr.lower()):
                    new_upstream = True
                else:
                    raise GitNestedError(f"Fetch for push failed: {stderr}")
            else:
                upstream = git.check_output(['rev-parse', 'FETCH_HEAD^0'])
                if not flags.force:
                    if upstream != config.commit:
                        raise GitNestedError(f"There are new changes upstream ({branch_name}), you need to pull first.")
                else:
                    # Force mode: fetch original branch to be based on correct commit
                    if upstream != config.commit:
                        git.run(['fetch', '--no-tags', '--quiet', config.remote, config.branch])
                        upstream = git.check_output(['rev-parse', 'FETCH_HEAD^0'])
                upstream_head_commit = upstream

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
                    return False, branch_name, subdir_worktree, True

            branch_created = True
        else:
            if flags.squash:
                raise GitNestedError("Squash option (-s) can't be used with branch parameter")

        if not git.branch_exists(branch):
            raise GitNestedError(f"No nested branch '{branch}' to push.")

        new_commit = git.check_output(['rev-parse', branch])
        if not new_upstream and upstream_head_commit == new_commit:
            if branch_created:
                self.delete_branch(git, branch, git_tmp)
            return False, branch_name, None, branch_created, new_commit

        if not flags.force and not new_upstream:
            if not git.commit_in_rev_list(upstream_head_commit, branch):
                raise GitNestedError(f"Can't commit: '{branch}' doesn't contain upstream HEAD: {upstream_head_commit}")

        cmd = ['push']
        if flags.force:
            cmd.append('--force')
        cmd.extend([config.remote, f'{branch}:{branch_name}'])
        git.run(cmd)

        self.create_nested_ref(git, subref, 'push', branch)

        return True, branch_name, subdir_worktree, branch_created, new_commit

    def do_fetch(self, git: GitRunner, flags: Flags, config: NestedConfig, subref: str) -> str:
        """Fetch upstream content

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
        upstream_head_commit = git.check_output(['rev-parse', 'FETCH_HEAD^0'])

        self.create_nested_ref(git, subref, 'fetch', 'FETCH_HEAD^0')

        return upstream_head_commit

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
        """Create a nested branch

        Returns:
            subdir_worktree
        """
        if branch is None:
            branch = f'nested/{subref}'

        self.verbose(f"Check if the '{branch}' branch already exists.", flags)
        if git.branch_exists(branch):
            return git_tmp / branch

        self.verbose(f"Nested repository parent: {config.parent}", flags)

        first_gitrepo_commit = None
        last_gitrepo_commit = None

        if config.parent:
            # Check if parent is ancestor
            result = git.run(['merge-base', '--is-ancestor', config.parent, 'HEAD'], may_fail=True)
            if result.returncode != 0:
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

            # Get commit list
            commits = git.check_output([
                'rev-list',
                '--reverse',
                '--ancestry-path',
                '--topo-order',
                f'{config.parent}..HEAD',
            ]).splitlines()

            prev_commit = None
            ancestor = None

            for commit in commits:
                # Get .gitnested commit from YAML
                gitrepo_content = git.check_output(['cat-file', '-p', f'{commit}:{subdir}/.gitnested'], may_fail=True)

                if not gitrepo_content:
                    continue

                try:
                    gitrepo_data = yaml.safe_load(gitrepo_content) or {}
                    gitrepo_commit = gitrepo_data.get('nested', {}).get('commit', '')
                except yaml.YAMLError:
                    continue

                if not gitrepo_commit:
                    continue

                gitrepo_commit = gitrepo_commit.strip()

                # Check if direct child
                if ancestor:
                    parents = git.check_output(['show', '-s', '--pretty=format:%P', commit])
                    if ancestor not in parents:
                        continue

                ancestor = commit

                # Check for rebase (only during pull operations)
                refs_fetch = f'refs/nested/{subref}/fetch'
                if git.rev_exists(refs_fetch) and command == 'pull':
                    # Check if gitrepo_commit is reachable from refs_fetch
                    result = git.run(['merge-base', '--is-ancestor', gitrepo_commit, refs_fetch], may_fail=True)
                    if result.returncode != 0:
                        if not git.rev_exists(gitrepo_commit):
                            raise GitNestedError(
                                f"Local repository does not contain {gitrepo_commit}. Try to 'git nested fetch {subref}' or add the '-F' flag."
                            )
                        else:
                            raise GitNestedError(
                                f"Upstream history has been rewritten. Commit {gitrepo_commit} is not in the upstream history. Try to 'git nested fetch {subref}' or add the '-F' flag."
                            )

                # Find parents
                first_parent = ['-p', prev_commit] if prev_commit else []

                second_parent = []
                if not first_gitrepo_commit:
                    first_gitrepo_commit = gitrepo_commit
                    second_parent = ['-p', gitrepo_commit]

                method = flags.method or config.method
                if method != 'rebase':
                    if gitrepo_commit != last_gitrepo_commit:
                        second_parent = ['-p', gitrepo_commit]
                        last_gitrepo_commit = gitrepo_commit

                # Create new commit
                result = git.run(['cat-file', '-e', f'{commit}:{subdir}'], may_fail=True)
                has_content = True if (result.returncode == 0) else False

                if has_content:
                    # Extract author and committer information
                    author_date = git.check_output(['log', '-1', '--date=default', '--format=%ad', commit])
                    author_email = git.check_output(['log', '-1', '--date=default', '--format=%ae', commit])
                    author_name = git.check_output(['log', '-1', '--date=default', '--format=%an', commit])
                    committer_date = git.check_output(['log', '-1', '--date=default', '--format=%cd', commit])
                    committer_email = git.check_output(['log', '-1', '--date=default', '--format=%ce', commit])
                    committer_name = git.check_output(['log', '-1', '--date=default', '--format=%cn', commit])
                    commit_msg = git.check_output(['log', '-1', '--date=default', '--format=%B', commit])

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

                    tree_cmd = ['commit-tree', '-F', '-'] + first_parent + second_parent + [f'{commit}:{subdir}']
                    prev_commit = git.check_output(tree_cmd, input=commit_msg, env=env)

            git.run(['branch', branch, prev_commit])
        else:
            git.run(['branch', branch, 'HEAD'])

            # Filter branch
            git.run(['filter-branch', '-f', '--subdirectory-filter', subref, branch], may_fail=True)

        # Remove .gitnested file
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
        subdir_worktree: Path,
        command: str,
    ):
        """Commit a nested branch"""
        self.verbose("Checking that the nested repository commit exists.", flags)
        if not git.rev_exists(nested_commit_ref):
            raise GitNestedError(f"Commit ref '{nested_commit_ref}' does not exist.")

        if not flags.force:
            self.verbose("Make sure that the commit contains the upstream HEAD.", flags)
            if not git.commit_in_rev_list(upstream_head_commit, nested_commit_ref):
                raise GitNestedError(f"Can't commit: '{nested_commit_ref}' doesn't contain upstream HEAD.")

        has_files = git.check_output(['ls-files', '--', subdir], may_fail=True)
        if has_files:
            self.verbose("Remove old content of the subdir.", flags)
            git.run(['rm', '-r', '--', subdir])

        self.verbose(f"Put remote nested content into '{subdir}/'.", flags)

        subdirs = [subdir] if not config.filter else [f'{subdir}/{p}' for p in config.filter]
        for subdir in subdirs:
            git.run(['read-tree', f'--prefix={subdir}', '-u', nested_commit_ref])

        # Finally, update .gitnested file
        self.verbose(f"Put info into '{subdir}/.gitnested' file.", flags)
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

            self.verbose("Commit .gitnested update to the current branch.", flags)
            if head_commit != 'none':
                if flags.message_file:
                    git.run(['commit', '--file', flags.message_file])
                else:
                    git.run(['commit', '-m', msg])
            else:
                tree = git.check_output(['write-tree'])

                if flags.message_file:
                    commit_sha = git.check_output(['commit-tree', '--file', flags.message_file, tree])
                else:
                    commit_sha = git.check_output(['commit-tree', '-m', msg, tree])

                git.run(['reset', '--hard', commit_sha])
        else:
            self.verbose("No changes to commit for .gitnested update", flags)

        self.remove_worktree(git, subdir_worktree)

        self.create_nested_ref(git, self.sanitize_subref(git, str(subdir)), 'commit', nested_commit_ref)

    def get_status(self, git: GitRunner, flags: Flags, git_tmp: Path) -> tuple[str, List[tuple[Path, NestedConfig]]]:
        """Get nested repository status

        Returns:
            tuple: (output_text, list of (subdir, config) tuples)
        """
        output = []

        nesteds = self.find_all_nested_repositories(git, flags)
        count = len(nesteds)
        if not flags.quiet:
            if count == 0:
                return "No nested repositories.\n", []
            ies = 'ies' if count != 1 else 'y'
            output.append(f"{count} nested repositor{ies}:\n")

        status_list = []
        for subdir in nesteds:
            subdir = subdir if isinstance(subdir, Path) else Path(subdir)
            subref = self.sanitize_subref(git, str(subdir))

            gitrepo = subdir / '.gitnested'
            if not gitrepo.is_file():
                output.append(f"'{subdir}' is not a nested repository\n")
                continue

            refs_fetch = f'refs/nested/{subref}/fetch'
            upstream_head = git.check_output(['rev-parse', '--short', refs_fetch], may_fail=True)

            config = self.read_config(gitrepo, flags)

            if flags.fetch:
                self.do_fetch(git, flags, config, subref)

            status_list.append((subdir, config))

            if flags.quiet:
                output.append(f"{subdir}\n")
                continue

            output.append(f"Git nested repository '{subdir}':\n")

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

            if config.commit:
                short = git.check_output(['rev-parse', '--short', config.commit])
                output.append(f"  Pulled Commit:   {short}\n")

            if config.parent:
                short = git.check_output(['rev-parse', '--short', config.parent])
                output.append(f"  Pull Parent:     {short}\n")

            worktree_list = git.check_output(['worktree', 'list'], may_fail=True) or ''
            for line in worktree_list.splitlines():
                if f'{git_tmp}/nested/{subdir}' in line:
                    output.append(f"  Worktree: {line}\n")

            if flags.verbose:
                output.append(self.format_refs(git, subref))

            output.append("\n")

        return ''.join(output), status_list

    def format_refs(self, git: GitRunner, subref: str) -> str:
        """Format refs for status"""
        output = []
        show_ref = git.check_output(['show-ref'], may_fail=True) or ''

        for line in show_ref.splitlines():
            m = re.match(rf'^([0-9a-f]+)\s+refs/nested/{subref}/([a-z]+)', line)
            if m:
                sha_full = m.group(1)
                sha = git.check_output(['rev-parse', '--short', sha_full])
                ref_type = m.group(2)
                ref = f'refs/nested/{subref}/{ref_type}'

                labels = {
                    'branch': 'Branch Ref',
                    'commit': 'Commit Ref',
                    'fetch': 'Fetch Ref',
                    'pull': 'Pull Ref',
                    'push': 'Push Ref',
                }
                if ref_type in labels:
                    output.append(f"    {labels[ref_type]:14} {sha} ({ref})\n")

        if output:
            return "  Refs:\n" + ''.join(output)
        return ""

    def do_clean(self, git: GitRunner, flags: Flags, subdir: Path, git_tmp: Path) -> List[str]:
        """Clean nested branches and refs"""
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

            show_ref = git.check_output(['show-ref'], may_fail=True) or ''
            for line in show_ref.splitlines():
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    ref = parts[1]
                    if ref.startswith(f'refs/nested/{suffix}') or ref.startswith(
                        f'refs/original/refs/heads/nested/{suffix}'
                    ):
                        git.run(['update-ref', '-d', ref])

        return items

    # -------------------------------------
    # Support Functions
    # -------------------------------------

    def guess_subdir(self, remote: str) -> str:
        """Guess subdirectory name from remote URL"""
        if not remote:
            raise GitNestedError("No remote specified for guessing subdir")
        name = Path(remote).name
        if name.endswith('.git'):
            name = name[:-4]
        return name

    def sanitize_subref(self, git: GitRunner, ref: str) -> str:
        """Sanitize subref to be a valid git ref"""

        def is_valid_ref(ref):
            result = git.run(['check-ref-format', f'nested/{ref}'], may_fail=True)
            return result.returncode == 0

        # Check if already valid (check-ref-format succeeds), so no encoding needed
        if is_valid_ref(ref):
            return ref

        # URL encode the subdir
        sanitized = quote(ref, safe='/')
        # Remove forbidden characters
        for c in ['~', '..', ' ', '/']:
            sanitized = sanitized.replace(c, '_')
        # Remove forbidden leading characters
        if sanitized.startswith('.') or sanitized.startswith('-'):
            sanitized = '_' + sanitized[1:]
        if sanitized.endswith('.lock'):  # .lock ending is not allowed
            sanitized = sanitized[:-5] + '_lock'

        # Ref cannot end with a dot
        if sanitized.endswith('.'):
            sanitized = sanitized[:-1]

        if not is_valid_ref(sanitized):
            raise GitNestedError(f"Can't determine valid subref from '{ref}'.")
        return sanitized

    def read_config(self, gitnested: Path, flags: Flags) -> NestedConfig:
        """Read .gitnested file"""
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
        """Update .gitnested YAML file"""
        initial = not gitnested.exists()

        if initial:
            # Try to recreate from parent commit
            result = git.run(['cat-file', '-e', f'{head_commit}:{gitnested}'], may_fail=True)
            if result.returncode == 0:
                content = git.check_output(['cat-file', '-p', f'{head_commit}:{gitnested}'])
                gitnested.write_text(content)
                initial = False

        # Load existing data or create new
        data = self._read_yaml_config(gitnested) if gitnested.exists() else {}
        nested = data.setdefault('nested', {})

        def should_update(override_value):
            """Check if a config field should be updated"""
            return (flags.update and override_value) or (command in ['push', 'clone'] and override_value)

        # Update fields
        nested['commit'] = upstream_head_commit
        nested['method'] = flags.method or config.method or 'merge'
        nested['cmdver'] = VERSION
        if flags.filter:
            nested['filter'] = flags.filter
        if initial or should_update(flags.remote):
            nested['remote'] = config.remote
        # For clone command, always update branch (including force reclone to different branch)
        if initial or command == 'clone' or should_update(flags.branch):
            nested['branch'] = config.branch
        if head_commit and nested_commit_ref:
            nested_commit = git.check_output(['rev-parse', nested_commit_ref])
            if upstream_head_commit == nested_commit:
                nested['parent'] = head_commit

        # Write YAML file and stage it
        self._write_yaml_config(gitnested, data)
        git.run(['add', '-f', '--', gitnested])

    # -------------------------------------
    # Checks and Validations
    # -------------------------------------

    def check_repository(self, git: GitRunner, command: str) -> tuple[Path, str]:
        """Check that repository is ready

        Returns:
            tuple: (git_tmp, head_commit)
        """
        if command in ['version']:
            return None, None

        try:
            git.run(['rev-parse', '--git-dir'])
        except GitNestedError:
            raise GitNestedError("Not inside a git repository.")

        git_common_dir = git.check_output(['rev-parse', '--git-common-dir'])
        git_tmp = Path(git_common_dir) / 'tmp'

        # Get original branch
        current_branch = git.check_output(['symbolic-ref', '--short', '--quiet', 'HEAD'], may_fail=True)
        if current_branch.startswith('nested/'):
            raise GitNestedError(f"Can't '{command}' while a nested branch is checked out: {current_branch}")

        if not current_branch or current_branch in ['HEAD']:
            raise GitNestedError("Must be on a branch to run this command.")

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

    def check_worktree_clean(self, git: GitRunner, command: str):
        """Ensure working copy has no uncommitted changes"""
        if command not in ['clone', 'init', 'pull', 'push', 'branch', 'commit']:
            return

        pwd = Path.cwd()
        git.run(['update-index', '-q', '--ignore-submodules', '--refresh'], may_fail=True)

        # Check for unstaged changes
        result = git.run(['diff-files', '--quiet', '--ignore-submodules'], may_fail=True)
        if result.returncode != 0:
            raise GitNestedError(f"Can't {command} nested repository. Unstaged changes. ({pwd})")

        if command == 'clone' and not git.rev_exists('HEAD'):
            # This may happen when cloning into an empty repository
            return

        result = git.run(['rev-parse', '--verify', 'HEAD'])
        if result.returncode != 0:
            raise GitNestedError(f"HEAD cannot be verified ({pwd})")

        result = git.run(['diff-index', '--quiet', '--ignore-submodules', 'HEAD'], may_fail=True)
        if result.returncode != 0:
            raise GitNestedError(f"Can't {command} nested repository. Working tree has changes. ({pwd})")

        result = git.run(['diff-index', '--quiet', '--cached', '--ignore-submodules', 'HEAD'], may_fail=True)
        if result.returncode != 0:
            raise GitNestedError(f"Can't {command} nested repository. Index has changes. ({pwd})")

    def check_subdir_for_init(self, git: GitRunner, subdir: Path, gitnested: Path):
        """Check subdir is ready for init"""
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
        """Create a worktree for the given branch"""
        subdir_worktree = git_tmp / branch
        git.run(['worktree', 'add', subdir_worktree, branch])
        return subdir_worktree

    def remove_worktree(self, git: GitRunner, worktree: Path):
        """Remove worktree"""
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
        """Delete a branch"""
        subdir_worktree = git_tmp / branch
        self.remove_worktree(git, subdir_worktree)
        git.run(['branch', '-D', branch], may_fail=True)

    # -------------------------------------
    # Utility Functions
    # -------------------------------------

    def find_all_nested_repositories(self, git: GitRunner, flags: Flags) -> list[Path]:
        """Find all nested repositories in repository"""
        tracked_files = git.check_output(['ls-files'])
        gitnesteds = sorted(Path(line).parent for line in tracked_files.splitlines() if line.endswith('.gitnested'))
        if not flags.ALL:
            # Filter the paths to contain only outermost nested repository paths
            gitnesteds = [
                p for p in gitnesteds if not any(p.is_relative_to(other) for other in gitnesteds if p != other)
            ]
        return gitnesteds

    def get_upstream_branch(self, git: GitRunner, config: NestedConfig) -> str:
        """Determine upstream default branch"""
        remote_branches = git.check_output(['ls-remote', '--symref', config.remote], may_fail=True)
        if not remote_branches:
            raise GitNestedError(f"Command failed: 'git ls-remote --symref {config.remote}'.")
        upstream_branch = re.search(r"[0-9a-f]\s+refs/heads/(\S+)", remote_branches)
        if not upstream_branch:
            raise GitNestedError("Problem finding remote default head branch.")
        return upstream_branch.group(1)

    def get_default_branch(self, git: GitRunner) -> str:
        """Get git's default branch name"""
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
        """Generate commit message"""
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
    """Handles command-line interface and user I/O"""

    def __init__(self):
        self.git = GitRunner()
        self.repo = GitNestedRepo()
        # For backward compatibility with tests
        self.flags = Flags()

    # -------------------------------------
    # User I/O methods
    # -------------------------------------

    def verbose(self, msg: str, flags: Flags = None):
        """Print verbose messages"""
        flags = flags or self.flags
        if flags.verbose:
            self.say(f"* {msg}", flags)

    def say(self, msg: str, flags: Flags = None):
        """Print message unless quiet"""
        flags = flags or self.flags
        if not flags.quiet:
            print(msg)

    def error(self, msg: str):
        """Print error and exit"""
        print(f"git-nested: {msg}", file=sys.stderr)
        raise GitNestedError(msg, print_to_stderr=False)

    def usage_error(self, msg: str):
        """Print usage error and exit"""
        print(f"git-nested: {msg}", file=sys.stderr)
        sys.exit(1)

    # -------------------------------------
    # main
    # -------------------------------------

    def main(self, args):
        """Main entry point"""
        command, flags, subdir, upstream, nested_commit_ref = self.parse_args(args)
        self.git.check()
        git_tmp, head_commit = self.repo.check_repository(self.git, command)

        # Handle --all flag
        if flags.all and command not in ['status']:
            if flags.branch:
                self.error("options --branch and --all are not compatible")

            nesteds = self.repo.find_all_nested_repositories(self.git, flags)
            for subdir_path in nesteds:
                self.dispatch_command(command, flags, subdir_path, upstream, nested_commit_ref, git_tmp, head_commit)
        else:
            self.dispatch_command(command, flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit)

    def parse_args(self, args_list):
        """Parse command line arguments

        Returns:
            tuple: (command, flags, subdir, upstream, nested_commit_ref)
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
            'fetch': ['all', 'branch', 'force', 'remote'],
            'init': ['branch', 'remote', 'method'],
            'pull': ['all', 'branch', 'force', 'message', 'method', 'remote', 'update'],
            'push': ['all', 'branch', 'commit', 'force', 'message', 'method', 'remote', 'squash', 'update'],
            'status': ['ALL', 'all', 'fetch'],
            'version': [],
        }

        subparsers = parser.add_subparsers(dest='command')

        command_subparsers = {command: subparsers.add_parser(command) for command in valid_command_options.keys()}

        def add_subparser_args(command_subparser, command):
            opts = valid_command_options.get(command)
            if 'all' in opts:
                command_subparser.add_argument('-a', '--all', action='store_true', dest='all_flag')
            if 'ALL' in opts:
                command_subparser.add_argument('-A', '--ALL', action='store_true', dest='ALL_flag')
            if 'branch' in opts:
                command_subparser.add_argument('-b', '--branch', dest='branch')
            if 'commit' in opts:
                command_subparser.add_argument('-c', '--commit', action='store_true')
            if 'force' in opts:
                command_subparser.add_argument('-f', '--force', action='store_true')
            if 'filter' in opts:
                command_subparser.add_argument('--filter', action='append')
            if 'fetch' in opts:
                command_subparser.add_argument('-F', '--fetch', action='store_true', dest='fetch_flag')
            if 'method' in opts:
                command_subparser.add_argument('-M', '--method', dest='method')
            if 'message' in opts:
                command_subparser.add_argument('-m', '--message', dest='message')
            if 'msg_file' in opts:
                command_subparser.add_argument('--file', dest='msg_file')
            if 'remote' in opts:
                command_subparser.add_argument('-r', '--remote', dest='remote')
            if 'squash' in opts:
                command_subparser.add_argument('-s', '--squash', action='store_true')
            if 'update' in opts:
                command_subparser.add_argument('-u', '--update', action='store_true')

        for command in valid_command_options.keys():
            command_subparser = command_subparsers.get(command)

            add_subparser_args(command_subparser, command)

            # Few commands also accept positional args
            if command in ['branch', 'commit', 'fetch', 'init', 'pull', 'push']:
                command_subparser.add_argument('subdir', nargs='?')
            if command in ['clean']:
                command_subparser.add_argument('subdir', nargs='?')
            if command in ['clone']:
                command_subparser.add_argument('upstream')
                command_subparser.add_argument('subdir', nargs='?')
            if command in ['commit']:
                command_subparser.add_argument('nested_commit_ref', nargs='?')
            if command in ['push']:
                command_subparser.add_argument('nested_branch', nargs='?')

        # parse arguments
        # Note: subparsers handle positional and optional arguments for each command
        args = parser.parse_args(args_list)

        if args.version:
            args.command = 'version'

        if not args.command:
            self.usage_error("Missing command")

        ###############################
        # Process the args
        ###############################
        upstream = getattr(args, 'upstream', None)
        subdir = getattr(args, 'subdir', None)
        nested_commit_ref = getattr(args, 'nested_commit_ref', None)

        if upstream and not subdir:
            subdir = self.repo.guess_subdir(upstream)

        # Create flags object
        flags = Flags()
        flags.all = getattr(args, 'all_flag', False)
        flags.ALL = getattr(args, 'ALL_flag', False)
        flags.commit = getattr(args, 'commit', False)
        flags.filter = getattr(args, 'filter', [])
        flags.force = getattr(args, 'force', False)
        flags.fetch = getattr(args, 'fetch_flag', False)
        flags.squash = getattr(args, 'squash', False)
        flags.update = getattr(args, 'update', False)
        flags.quiet = getattr(args, 'quiet', False)
        flags.verbose = getattr(args, 'verbose', 0)

        if flags.ALL:
            flags.all = True

        def supported(opt):
            return opt in valid_command_options.get(args.command)

        def supported_and_set(opt):
            return supported(opt) and getattr(args, opt, None) is not None

        if supported_and_set('branch'):
            flags.branch = args.branch
        if supported_and_set('remote'):
            flags.remote = args.remote
        if supported_and_set('method'):
            flags.method = args.method
        if supported_and_set('message'):
            flags.message = args.message
        if supported_and_set('msg_file'):
            flags.message_file = args.msg_file

        # Check for invalid usage
        if supported_and_set('msg_file') and not Path(args.msg_file).is_file():
            self.error(f"Commit msg file at {args.msg_file} not found")
        if supported_and_set('message') and supported_and_set('msg_file'):
            self.error("fatal: options '-m' and '--file' cannot be used together")

        # Set command
        command = args.command

        if flags.update and not (flags.branch or flags.remote):
            self.usage_error("Can't use '--update' without '--branch' or '--remote'.")

        return command, flags, subdir, upstream, nested_commit_ref

    def dispatch_command(self, command, flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit):
        """Dispatch to command function"""
        commands = {
            'clone': lambda: self.cmd_clone(flags, subdir, upstream, head_commit),
            'init': lambda: self.cmd_init(flags, subdir, upstream, head_commit),
            'pull': lambda: self.cmd_pull(flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit),
            'push': lambda: self.cmd_push(flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit),
            'fetch': lambda: self.cmd_fetch(flags, subdir, upstream),
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
        """Clone a remote repository into a local subdirectory"""
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
        """Initialize a subdirectory as a nested repo"""
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

    def cmd_pull(self, flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit):
        """Pull upstream changes to the nested repo"""
        subdir, gitnested, subref, config = self.setup_command('pull', flags, subdir, upstream)

        if flags.force:
            _, config, _, _ = self.repo.do_clone(
                git=self.git,
                flags=flags,
                config=config,
                subdir=subdir,
                gitnested=gitnested,
                subref=subref,
            )
            self.say(f"Nested repository '{subdir}' pulled from '{config.remote}' ({config.branch}).", flags)
            return

        success, nested_commit_ref, subdir_worktree, error_msg = self.repo.do_pull(
            git=self.git,
            flags=flags,
            config=config,
            subdir=subdir,
            gitnested=gitnested,
            git_tmp=git_tmp,
            subref=subref,
        )

        if not success and nested_commit_ref is None:
            self.say(f"Nested repository '{subdir}' is up to date with upstream branch '{config.branch}'.", flags)
            return

        if not success:
            # Print the error message to stdout
            self.say(error_msg, flags)
            # Merge/rebase failed
            method = flags.method or config.method
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
            msg = textwrap.dedent(
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
            print(msg, file=sys.stderr)
            sys.exit(1)

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
        """Push local nested repo changes upstream"""
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

        if not success and subdir_worktree:
            # Rebase failed
            self.say('The "git rebase" command failed', flags)
            sys.exit(1)

        if not success:
            self.say(f"Nested repository '{subdir}' has no new commits to push.", flags)
            return

        if branch_created:
            self.verbose(f"Remove branch 'nested/{subref}'.", flags)
            self.repo.delete_branch(self.git, f'nested/{subref}', git_tmp)

        # Update .gitnested if --commit or if --remote/--branch specified
        if flags.commit:
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

        self.say(
            f"Nested repository '{subdir}' pushed to '{config.remote}' ({branch_name}).",
            flags,
        )

    def cmd_fetch(self, flags, subdir, upstream):
        """Fetch a nested repo's remote branch"""
        subdir, _, subref, config = self.setup_command('fetch', flags, subdir, upstream)

        if config.remote == 'none':
            self.say(f"Ignored '{subdir}', no remote.", flags)
        else:
            self.repo.do_fetch(self.git, flags, config, subref)
            self.say(f"Fetched '{subdir}' from '{config.remote}' ({config.branch}).", flags)

    def cmd_branch(self, flags, subdir, upstream, git_tmp):
        """Create a branch containing the local nested repo commits"""
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
        """Commit a merged nested branch"""
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
        """Get status of a nested repo (or all of them)"""
        output, _ = self.repo.get_status(self.git, flags, git_tmp)
        self.say(output, flags)

    def cmd_clean(self, flags, subdir, upstream, git_tmp):
        """Remove branches, remotes and refs for a nested repo"""
        subdir, _, _, _ = self.setup_command('clean', flags, subdir, upstream)

        for item in self.repo.do_clean(self.git, flags, subdir, git_tmp):
            self.say(f"Removed {item}.", flags)

    def cmd_version(self):
        """Print version information"""
        print(f"git-nested Version: {VERSION}")
        print("Copyright 2026 Thorsten Klein <thorsten.klein.git@gmail.com>")
        print("https://github.com/thorsten-klein/git-nested")
        print(Path(__file__).resolve())
        print(f"Git Version: {self.git.get_version()}")

    # -------------------------------------
    # Setup
    # -------------------------------------

    def setup_command(self, command, flags, subdir, upstream):
        """Setup command with parameters

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
        gitnested = subdir / '.gitnested'

        # Check for existing worktree
        if not flags.force:
            self.verbose(f"Check for worktree with branch nested/{subdir}", flags)
            worktree_list = self.git.check_output(['worktree', 'list'], may_fail=True) or ''

            has_worktree = False
            worktree_path = None
            for line in worktree_list.splitlines():
                if f'[nested/{subdir}]' in line:
                    has_worktree = True
                    worktree_path = line.split()[0]
                    break

            if command in ['commit'] and not has_worktree:
                self.error("There is no worktree available, use the branch command first")
            elif command not in ['branch', 'clean', 'commit', 'push'] and has_worktree:
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

        # Read .gitnested file if exists
        if command not in ['clone', 'init']:
            config = self.repo.read_config(gitnested, flags)
        else:
            config = NestedConfig()
            if upstream:
                config.remote = upstream

        # Apply overrides (from command line flags)
        if flags.remote:
            config.remote = flags.remote
        if flags.branch:
            config.branch = flags.branch

        return subdir, gitnested, subref, config


def main():
    """Main entry point"""
    try:
        app = GitNestedCommand()
        app.main(sys.argv[1:])
    except GitNestedError:
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


# Backward compatibility alias
GitNested = GitNestedCommand


if __name__ == '__main__':
    main()
