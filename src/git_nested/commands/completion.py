"""Printing the shell completion script."""

from __future__ import annotations

from ..completion import scripts
from ..models import CommandContext


def cmd_completion(ctx: CommandContext) -> None:
    """Print the completion script for the requested shell, or the detected one."""
    shell = ctx.completion_shell or scripts.detect_shell()
    print(scripts.script(shell, scripts.bind_names()), end='')
