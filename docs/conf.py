"""Sphinx config for git-nested."""

from __future__ import annotations

import sys
from pathlib import Path

from sphinx.application import Sphinx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from git_nested.docgen import write_sphinx_command_reference  # noqa: E402

project = 'git-nested'
copyright = '2026, Thorsten Klein'
author = 'Thorsten Klein'

extensions = [
    'myst_parser',
    'sphinx.ext.githubpages',
    'sphinxcontrib.mermaid',
]

exclude_patterns = ['_build']
html_baseurl = 'https://thorsten-klein.github.io/git-nested/'
html_theme = 'alabaster'
html_title = 'git-nested'
root_doc = 'index'

myst_enable_extensions = ['colon_fence']
myst_fence_as_directive = ['mermaid']


def _write_generated_docs(app: Sphinx) -> None:
    write_sphinx_command_reference(Path(app.srcdir))


def setup(app: Sphinx) -> None:
    """Register the hook that writes the generated command reference."""
    app.connect('builder-inited', _write_generated_docs)
