"""Printing to the user."""

from __future__ import annotations

from .models import Flags


def verbose(msg: str, flags: Flags):
    """Print verbose messages."""
    if flags.verbose:
        print(f"* {msg}")


def say(msg: str, flags: Flags):
    """Print message unless quiet."""
    if not flags.quiet:
        print(msg)
