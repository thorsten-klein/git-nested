"""The GitNestedCommand application object.

It owns the two things a running command needs -- a GitRunner and the
current Flags -- and dispatches argv to the right handler in `commands`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import NoReturn, cast

from .. import checks, commands, completion, discovery, output
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

    def _dispatch_all(self, command: str, ctx: CommandContext) -> None:
        """Dispatch command across every nested repository (the --all flag)."""
        if ctx.flags.branch:
            self.error("options --branch and --all are not compatible")

        for subdir_path in discovery.find_all_nested_repositories(self.git, ctx.flags):
            subdir_ctx = cast(CommandContext, replace(ctx, subdir=subdir_path))
            self.dispatch_command(command, subdir_ctx)

    def main(self, args):
        """Main entry point."""
        # Before the parser: `__complete` is deliberately not a subcommand.
        # It is an implementation detail of the printed completion scripts,
        # so it stays out of --help and out of its own candidate list.
        if completion.handle_dunder_complete(self.git, args):
            return

        command, ctx = self.parse_args(args)
        self.git.check()
        ctx.git_tmp, ctx.head_commit = checks.check_repository(self.git, command)

        if ctx.flags.all and command not in ['status']:
            self._dispatch_all(command, ctx)
        else:
            self.dispatch_command(command, ctx)

    def parse_args(self, args_list):
        """Parse command line arguments.

        Returns:
            tuple: (command, context)
        """
        return parser.parse_args(self.git, args_list)

    def dispatch_command(self, command: str, ctx: CommandContext) -> None:
        """Run the handler registered for `command`."""
        handler = commands.REGISTRY.get(command)
        if handler is None:
            self.usage_error(f"Unknown command: {command}")

        handler(ctx)

    def setup_command(self, command, flags, subdir, upstream):
        """Setup command with parameters.

        Returns:
            tuple: (subdir, gitnested, subref, config)
        """
        return setup.setup_command(self.git, command, flags, subdir, upstream)
