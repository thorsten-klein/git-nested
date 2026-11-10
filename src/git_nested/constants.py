"""Names shared across the package."""

from __future__ import annotations

REQUIRED_GIT_VERSION = "2.23.0"

GITNESTED_FILENAME = '.gitnested'
GITNESTED_LEVEL_PREFIX = '.gitnested.level'
FETCH_HEAD_REV = 'FETCH_HEAD^0'
GIT_LOG_DATE_DEFAULT_FLAG = '--date=default'

# The shells `git nested completion` can emit a script for.
COMPLETION_SHELLS = ('bash', 'zsh', 'fish')
