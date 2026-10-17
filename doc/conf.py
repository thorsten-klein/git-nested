"""Sphinx config for the git-nested docs.

The pages are the Markdown files in doc/. GitHub shows the same files.
doc/README.md is the start page on GitHub, doc/index.md the start page
of the site. So README.md is left out of the build.

`uv run poe docs` builds the site twice: as HTML and as Markdown. The
Markdown copy is for AI tools. .github/workflows/docs.yml publishes both
to the gh_pages branch.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from docutils import nodes
from sphinx.application import Sphinx

project = 'git-nested'
copyright = 'Thorsten Klein'
author = 'Thorsten Klein'

_HERE = Path(__file__).resolve().parent


def _git(*args: str) -> str:
    """The output of a git command in this checkout, or '' if git fails."""
    try:
        done = subprocess.run(['git', '-C', str(_HERE), *args], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ''
    return done.stdout.strip() if done.returncode == 0 else ''


# The version in the sidebar, e.g. "1.1.1" or "1.1.1-8-g21900a7" after a tag.
release = _git('describe', '--tags', '--match', '*.*.*')
version = release

github_user = 'thorsten-klein'
github_repo = 'git-nested'
github_url = f'https://github.com/{github_user}/{github_repo}'

# The version links to the commit the site was built from.
_sha = re.search(r'-g([0-9a-f]{7,40})$', release)
_ref = _git('rev-parse', 'HEAD') or (_sha.group(1) if _sha else release)
version_url = f'{github_url}/tree/{_ref}' if _ref else ''

# -- General ------------------------------------------------------------------

extensions = [
    'myst_parser',
    'sphinx.ext.githubpages',
    'sphinx_copybutton',
    # the 'markdown' builder, for the Markdown copy of the site
    'sphinx_markdown_builder',
    'sphinxcontrib.mermaid',
]

myst_enable_extensions = ['colon_fence', 'deflist']
# Links like "gitnested-file.md#remote" point at headings.
myst_heading_anchors = 3
# A plain ```mermaid fence becomes a diagram. GitHub draws the same fence.
myst_fence_as_directive = ['mermaid']

source_suffix = {'.md': 'markdown'}
root_doc = 'index'
exclude_patterns = ['README.md', '_build', 'Thumbs.db', '.DS_Store']

# Warn about every broken reference. The build fails on warnings.
nitpicky = True

# -- HTML ---------------------------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_title = 'git-nested'
html_baseurl = 'https://thorsten-klein.github.io/git-nested/'

templates_path = ['_templates']
html_static_path = ['_static']
html_css_files = ['custom.css']
html_js_files = ['custom.js']

html_theme_options = {
    'collapse_navigation': False,
    'navigation_depth': 3,
}

# The "Edit on GitHub" link.
html_context = {
    'display_github': True,
    'github_user': github_user,
    'github_repo': github_repo,
    'github_version': 'main',
    'conf_py_path': '/doc/',
    # read by doc/_templates/layout.html
    'version_url': version_url,
}


def _mermaid_to_markdown(translator: nodes.NodeVisitor, node: nodes.Element) -> None:
    """Write a diagram as a ```mermaid fence in the Markdown copy.

    sphinxcontrib.mermaid has no visitor for the markdown builder. Without
    this one the build warns, and so fails.
    """
    translator.add('```mermaid', prefix_eol=1, suffix_eol=1)
    translator.add(node['code'].strip(), suffix_eol=1)
    translator.add('```', suffix_eol=2)
    raise nodes.SkipNode


def setup(app: Sphinx) -> None:
    """Teach the markdown builder about diagrams."""
    from sphinxcontrib.mermaid import mermaid  # noqa: PLC0415

    # override=True keeps the HTML visitors and adds the Markdown one.
    app.add_node(mermaid, override=True, markdown=(_mermaid_to_markdown, None))
