"""The one exception type git-nested raises."""

from __future__ import annotations

import sys


class GitNestedError(Exception):
    """Base exception for git-nested errors."""

    def __init__(self, message, print_to_stderr=True):
        """Store the message and optionally print it to stderr immediately."""
        self.message = message
        if print_to_stderr:
            print(f"git-nested: {message}", file=sys.stderr)
        super().__init__(self.message)
