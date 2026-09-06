"""git-nested - Git Submodule Alternative.

Copyright 2026 - Thorsten Klein <thorsten.klein.git@gmail.com>
"""

# Postponed evaluation (PEP 563). The 3.9 floor that originally required this
# is gone, but it stays: annotations become lazily-parsed strings, which is
# what lets modules reference each other's types under `if TYPE_CHECKING:`
# without the import cycles a package of this shape would otherwise grow.
from __future__ import annotations

from contextlib import chdir

from ._version import VERSION
from .cli.app import GitNestedCommand
from .cli.main import main
from .errors import GitNestedError
from .git import GitRunner
from .models import Flags, NestedConfig
from .repo import GitNestedRepo

# Backward compatibility alias
GitNested = GitNestedCommand

# The package's public surface. Names are re-exported here so that
# `from git_nested import X` keeps working as the internals are split up --
# note that this means monkeypatching git_nested.X patches the re-export, not
# the definition, so tests must reach for the defining module instead.
__all__ = [
    'VERSION',
    'Flags',
    'GitNested',
    'GitNestedCommand',
    'GitNestedError',
    'GitNestedRepo',
    'GitRunner',
    'NestedConfig',
    'chdir',
    'main',
]
