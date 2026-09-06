"""The GitNestedCommand application object.

It owns the two things a running command needs -- a GitRunner and the
current Flags -- and dispatches argv to the right handler in `commands`.
"""

from __future__ import annotations

from typing import NoReturn

from .. import checks, commands, discovery, output
from ..git import GitRunner
from ..models import CommandContext, Flags
from ..repo import GitNestedRepo
from . import parser, setup


class GitNestedCommand:
    """Handles command-line interface and user I/O."""

    def __init__(self):
        """Wire up the git runner and repo/business-logic layer."""
        self.git = GitRunner()
        # Kept for callers that reach for the business-logic layer through
        # the command object; nothing in here needs it any more.
        self.repo = GitNestedRepo()
        self.flags = Flags()

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
        """Run the handler registered for `command`."""
        handler = commands.REGISTRY.get(command)
        if handler is None:
            self.usage_error(f"Unknown command: {command}")

        handler(
            CommandContext(
                git=self.git,
                flags=flags,
                subdir=subdir,
                upstream=upstream,
                nested_commit_ref=nested_commit_ref,
                git_tmp=git_tmp,
                head_commit=head_commit,
            )
        )

    def setup_command(self, command, flags, subdir, upstream):
        """Setup command with parameters.

        Returns:
            tuple: (subdir, gitnested, subref, config)
        """
        return setup.setup_command(self.git, command, flags, subdir, upstream)
