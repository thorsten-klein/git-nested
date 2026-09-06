"""Reporting git-nested's own version."""

from __future__ import annotations

from pathlib import Path

from .._version import VERSION
from ..models import CommandContext


def cmd_version(ctx: CommandContext) -> None:
    """Print version information."""
    git = ctx.git
    print(f"git-nested Version: {VERSION}")
    print("Copyright 2026 Thorsten Klein <thorsten.klein.git@gmail.com>")
    print("https://github.com/thorsten-klein/git-nested")
    print(Path(__file__).resolve())
    print(f"Git Version: {git.get_version()}")
