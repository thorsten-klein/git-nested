"""Printing the shell completion script."""

from __future__ import annotations

from .. import output
from ..completion import scripts
from ..models import CommandContext


def cmd_completion(ctx: CommandContext) -> None:
    """Print the completion script for the requested shell, or the detected one."""
    shell = ctx.completion_shell or scripts.detect_shell()
    # The script already ends in a newline, which payload would double.
    output.payload(scripts.script(shell, scripts.bind_names()).rstrip('\n'))
