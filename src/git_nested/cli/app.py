"""The GitNestedCommand application object.

It owns the GitRunner a running command needs, and dispatches argv to the
right handler in `commands`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from .. import checks, commands, completion, content, discovery, output
from ..errors import GitNestedError
from ..git import GitRunner
from ..models import CommandContext
from . import location, parser


class GitNestedCommand:
    """Handles command-line interface and user I/O."""

    def __init__(self) -> None:
        """Wire up the git runner."""
        self.git = GitRunner()

    def main(self, args: list[str]) -> None:
        """Main entry point."""
        # Before the parser: `__complete` is deliberately not a subcommand.
        # It is an implementation detail of the printed completion scripts,
        # so it stays out of --help and out of its own candidate list.
        if completion.handle_dunder_complete(self.git, args):
            return

        # The handler goes on before the parser runs, because the parser is
        # itself allowed to report a bad command line; it comes off again in
        # a finally, because a single process may run many commands (the
        # test suite runs hundreds) and a handler left attached would print
        # every later line once more per command.
        detach = output.configure()
        try:
            self._run(args)
        except GitNestedError as exc:
            output.report(exc)
            raise
        finally:
            detach()

    def _run(self, args: list[str]) -> None:
        """Parse `args` and run the command it names, with output already wired up."""
        command, ctx = self.parse_args(args)
        output.set_level(ctx.flags)
        self.git.check()
        with location.at_top_level(self.git, command, ctx):
            ctx.git_tmp, ctx.head_commit = checks.check_repository(self.git, command, ctx.flags)

            # status and clean find all repositories themselves
            if not ctx.flags.all or command in ('status', 'clean'):
                self.dispatch_command(command, ctx)
                return
            if ctx.flags.branch:
                output.error("--branch and --all can't be used together")
            for subdir in discovery.find_all_nested_repositories(self.git, ctx.flags):
                self.dispatch_command(command, cast('CommandContext', replace(ctx, subdir=subdir)))
            if ctx.flags.single_commit:
                content.commit_all(self.git, ctx.flags, command)

    def parse_args(self, args_list: list[str]) -> tuple[str, CommandContext]:
        """Parse command line arguments.

        Returns:
            tuple: (command, context)
        """
        return parser.parse_args(self.git, args_list)

    def dispatch_command(self, command: str, ctx: CommandContext) -> None:
        """Run the handler registered for `command`."""
        handler = commands.REGISTRY.get(command)
        if handler is None:
            output.usage_error(f"unknown command {command}; 'git nested --help' lists them")
        handler(ctx)
