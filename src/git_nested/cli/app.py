"""The GitNestedCommand application object.

It owns the three things a running command needs -- a GitRunner, the
repo/business-logic layer and the current Flags -- and dispatches argv to
the right `cmd_*` handler.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import NoReturn

from .. import checks, content, discovery, gitfile, output, worktree
from .._version import VERSION
from ..git import GitRunner
from ..models import Flags
from ..repo import GitNestedRepo
from . import parser, setup


class GitNestedCommand:
    """Handles command-line interface and user I/O."""

    def __init__(self):
        """Wire up the git runner and repo/business-logic layer."""
        self.git = GitRunner()
        self.repo = GitNestedRepo()
        # For backward compatibility with tests
        self.flags = Flags()

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

    def error(self, msg: str) -> NoReturn:
        """Report a failure and abort the command."""
        output.error(msg)

    def usage_error(self, msg: str) -> NoReturn:
        """Report a malformed command line and exit."""
        output.usage_error(msg)

    def _dispatch_all(self, command, flags, upstream, nested_commit_ref, git_tmp, head_commit):
        """Dispatch command across every nested repository (the --all flag)."""
        if flags.branch:
            self.error("options --branch and --all are not compatible")

        nesteds = discovery.find_all_nested_repositories(self.git, flags)
        for subdir_path in nesteds:
            self.dispatch_command(command, flags, subdir_path, upstream, nested_commit_ref, git_tmp, head_commit)

    def main(self, args):
        """Main entry point."""
        command, flags, subdir, upstream, nested_commit_ref = self.parse_args(args)
        self.git.check()
        git_tmp, head_commit = checks.check_repository(self.git, command)

        if flags.all and command not in ['status']:
            self._dispatch_all(command, flags, upstream, nested_commit_ref, git_tmp, head_commit)
        else:
            self.dispatch_command(command, flags, subdir, upstream, nested_commit_ref, git_tmp, head_commit)

    def parse_args(self, args_list):
        """Parse command line arguments.

        Returns:
            tuple: (command, flags, subdir, upstream, nested_commit_ref)
        """
        return parser.parse_args(args_list)

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
            content.commit_nested_branch(
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
        config.branch = config.branch or discovery.get_default_branch(self.git)

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
            content.commit_nested_branch(
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
        content.commit_nested_branch(
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
            worktree.delete_branch(self.git, f'nested/{subref}', git_tmp)

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

        gitfile.update_gitrepo_file(
            git=self.git,
            flags=flags,
            config=config,
            gitnested=gitnested,
            upstream_head_commit=new_commit,
            nested_commit_ref=new_commit,
            head_commit=head_commit,
            command='push',
        )

        msg = flags.message or discovery.build_commit_message(
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
            worktree.delete_branch(self.git, branch, git_tmp)
        elif self.git.branch_exists(branch):
            self.error(f"Branch '{branch}' already exists. Use '--force' to override.")

        subdir_worktree = content.create_nested_branch(
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

        content.commit_nested_branch(
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
        report, _ = self.repo.get_status(self.git, flags, git_tmp)
        self.say(report, flags)

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

    def setup_command(self, command, flags, subdir, upstream):
        """Setup command with parameters.

        Returns:
            tuple: (subdir, gitnested, subref, config)
        """
        return setup.setup_command(self.git, command, flags, subdir, upstream)
