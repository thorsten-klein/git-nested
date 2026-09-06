"""The process entry point."""

from __future__ import annotations

import sys

from ..errors import GitNestedError
from .app import GitNestedCommand


def main():
    """Run git-nested, mapping its two expected failures onto exit codes."""
    try:
        app = GitNestedCommand()
        app.main(sys.argv[1:])
    except GitNestedError:
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
