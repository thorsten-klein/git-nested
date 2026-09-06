"""The version git-nested reports.

Its own module so tests can monkeypatch _pkg_version at the definition
site; patching a re-export on the package would no longer reach it.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version


def _detect_version() -> str:
    """Return the installed 'git-nested' package version, or a placeholder when unpackaged."""
    try:
        return _pkg_version("git-nested")
    except PackageNotFoundError:
        return "0.99.99"


VERSION = _detect_version()
