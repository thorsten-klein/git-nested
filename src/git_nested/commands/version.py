"""Reporting git-nested's own version."""

from __future__ import annotations

from pathlib import Path

from .. import output
from .._version import VERSION
from ..models import CommandContext


def cmd_version(ctx: CommandContext) -> None:
    """Print version information."""
    git = ctx.git
    output.payload(
        '\n'.join([
            f"git-nested Version: {VERSION}",
            "Copyright 2026 Thorsten Klein <thorsten.klein.git@gmail.com>",
            "https://github.com/thorsten-klein/git-nested",
            str(Path(__file__).resolve()),
            f"Git Version: {git.get_version()}",
        ])
    )
