"""Standard-library pieces that the oldest supported Python does not have yet.

One entry so far. It lives in its own module rather than inline so that the
day the floor moves past 3.10, deleting this file and re-pointing the one
import is the whole of the change.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path

if sys.version_info >= (3, 11):  # pragma: no cover -- the branch not taken is the other Python's
    chdir = contextlib.chdir
else:  # pragma: no cover -- only 3.10 runs this

    @contextlib.contextmanager
    def chdir(path) -> Iterator[None]:
        """Backport of contextlib.chdir, added to the standard library in 3.11.

        The working directory is changed for the duration of the `with` block
        and restored afterwards, whatever the block does.
        """
        previous = Path.cwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(previous)
