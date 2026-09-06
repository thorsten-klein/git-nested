"""Entry point for `python -m git_nested`."""

from __future__ import annotations

import sys

from . import main

if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
