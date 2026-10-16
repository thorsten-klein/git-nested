"""Standard-library pieces that the oldest supported Python does not have yet.

They live in their own module, so the day the floor moves past 3.11,
deleting them here and re-pointing the imports is the whole change.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

if sys.version_info >= (3, 11):  # pragma: no cover -- the branch not taken is the other Python's
    chdir = contextlib.chdir
else:  # pragma: no cover -- only 3.10 runs this

    @contextlib.contextmanager
    def chdir(path: str | Path) -> Iterator[None]:
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


def _make_writable_and_retry(func: Callable[[str], object], path: str, _exc: object) -> None:
    """Clear the read-only flag that stopped `func`, and try once more."""
    os.chmod(path, stat.S_IWRITE)  # noqa: PTH101
    func(path)


def rmtree(path: Path) -> None:
    """shutil.rmtree, also for read-only files: git keeps its objects so on Windows."""
    if not path.exists():
        return
    if sys.version_info >= (3, 12):  # pragma: no cover -- the branch not taken is the other Python's
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    else:  # pragma: no cover -- only 3.10 and 3.11 run this
        shutil.rmtree(path, onerror=_make_writable_and_retry)
