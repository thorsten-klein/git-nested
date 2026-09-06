"""The GitNestedRepo facade.

Every attribute that is not defined on the class resolves to the
module-level function of the same name in one of `_MODULES`. New code
imports those functions directly; this exists so that `GitNestedRepo()`
keeps working for anything that already depends on it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from . import checks, content, discovery, filters, gitfile, history, output, refs, worktree, yamlio
from .constants import FETCH_HEAD_REV, GITNESTED_FILENAME
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags, NestedConfig

# Scanned in order by GitNestedRepo.__getattr__. A name defined by two of
# these modules would resolve to whichever comes first, so a unit test
# asserts the exported names are disjoint.
_MODULES = (
    checks,
    content,
    discovery,
    filters,
    gitfile,
    history,
    output,
    refs,
    worktree,
    yamlio,
)


class GitNestedRepo:
    """Handles repository operations and business logic."""

    def __init__(self):
        """No state to initialize; all methods operate on their arguments."""

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

        output.verbose(f"Make the directory '{subdir}/' for the clone.", flags)
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
        config = gitfile.read_config(gitnested, flags)

        output.verbose("Check if we already are up to date.", flags)
        if upstream_head_commit == config.commit:
            return True, config, upstream_head_commit

        output.verbose("Remove the existing subdir.", flags)
        git.run(['rm', '-r', '--', subdir])

        if not branch:
            output.verbose("Determine the upstream head branch.", flags)
            config.branch = discovery.get_upstream_branch(git, config)
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
            output.verbose("Determine the upstream head branch.", flags)
            config.branch = discovery.get_upstream_branch(git, config)

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
        checks.check_subdir_for_init(git, subdir, gitnested)
        nested_commit_ref = head_commit

        output.verbose(f"Put info into '{subdir}/.gitnested' file.", flags)
        gitfile.update_gitrepo_file(
            git=git,
            flags=flags,
            config=config,
            gitnested=gitnested,
            upstream_head_commit='',  # No upstream for init
            nested_commit_ref=nested_commit_ref,
            head_commit=head_commit,
            command='init',
        )

        output.verbose(f"Add the new '{subdir}/.gitnested' file.", flags)
        git.run(['add', '-f', '--', gitnested])

        output.verbose("Commit the changes.", flags)
        msg = discovery.build_commit_message(
            git=git,
            config=config,
            upstream_head_commit=head_commit,
            nested_commit_ref=nested_commit_ref,
            subdir=subdir,
            command='init',
        )
        git.run(['commit', '-m', msg])

        refs.create_nested_ref(git, subref, 'commit', nested_commit_ref)

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
        worktree.delete_branch(git, branch, git_tmp)
        nested_commit_ref = branch

        output.verbose(f"Create nested branch '{branch}'.", flags)
        subdir_worktree = content.create_nested_branch(
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

        refs.create_nested_ref(git, subref, 'branch', branch)

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
        return filters.build_filtered_commit(git, subdir_worktree, config, upstream_head_commit)

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
        worktree.delete_branch(git, branch, git_tmp)

        updated_config = config
        if flags.squash:
            updated_config = NestedConfig(
                remote=config.remote,
                branch=config.branch,
                commit=config.commit,
                parent='HEAD^',
                method=config.method,
            )

        subdir_worktree = content.create_nested_branch(
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
            worktree.delete_branch(git, branch, git_tmp)
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

        refs.create_nested_ref(git, subref, 'push', branch)

    def get_diff(self, git: GitRunner, flags: Flags, config: NestedConfig, subdir: Path, subref: str) -> str:
        """Compute the diff between the local nested repository content and the freshly fetched upstream content.

        Returns:
            diff text (empty string if there are no differences)
        """
        upstream_head_commit = self.do_fetch(git, flags, config, subref)

        local_tree = git.check_output(['rev-parse', f'HEAD:{subdir}'])

        if config.filter:
            upstream_target = filters.build_filtered_commit(git, Path.cwd(), config, upstream_head_commit)
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
        output.verbose(f"Fetch the upstream: {config.remote} {branch_info}.", flags)

        cmd = ['fetch', '--no-tags', '--quiet', config.remote]
        if config.branch:
            cmd.append(config.branch)

        git.run(cmd)

        output.verbose("Get the upstream nested HEAD commit.", flags)
        upstream_head_commit = git.check_output(['rev-parse', FETCH_HEAD_REV])

        refs.create_nested_ref(git, subref, 'fetch', FETCH_HEAD_REV)

        return upstream_head_commit

    def get_status(self, git: GitRunner, flags: Flags, git_tmp: Path) -> tuple[str, list[tuple[Path, NestedConfig]]]:
        """Get nested repository status.

        Returns:
            tuple: (output_text, list of (subdir, config) tuples)
        """
        nesteds = discovery.find_all_nested_repositories(git, flags)
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
        subref = refs.sanitize_subref(git, str(subdir))

        gitrepo = subdir / GITNESTED_FILENAME
        if not gitrepo.is_file():
            return [f"'{subdir}' is not a nested repository\n"], []

        refs_fetch = f'refs/nested/{subref}/fetch'
        upstream_head = git.check_output(['rev-parse', '--short', refs_fetch], may_fail=True)

        config = gitfile.read_config(gitrepo, flags)

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
        subref = refs.sanitize_subref(git, str(subdir))
        branch = f'nested/{subref}'
        ref = f'refs/heads/{branch}'
        subdir_worktree = git_tmp / branch

        worktree.remove_worktree(git, subdir_worktree)

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

    def __getattr__(self, name: str) -> Callable[..., object]:
        """Resolve `name` to the module-level function of the same name."""
        for module in _MODULES:
            func = getattr(module, name, None)
            if func is not None:
                return func
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")
