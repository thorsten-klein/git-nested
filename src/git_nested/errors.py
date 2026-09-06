"""The one exception type git-nested raises."""

from __future__ import annotations


class GitNestedError(Exception):
    """Base exception for git-nested errors.

    Raising is not reporting: this only carries the message. `cli.app` prints
    it, once, if the error makes it all the way out of the command -- which
    is what lets the several places that catch one and re-interpret it do so
    without a stray line already on stderr.
    """

    def __init__(self, message: str) -> None:
        """Store the message."""
        self.message = message
        super().__init__(self.message)
