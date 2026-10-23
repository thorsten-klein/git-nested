# Documentation

The docs are the Markdown files in `doc/`. GitHub shows them as they are.
Sphinx builds the same files into the website.

## Build

```bash
uv run poe docs
```

This builds the site twice:

- `doc/_build/html/`: the website. Open `doc/_build/html/index.html`.
- `doc/_build/html/markdown/`: the same pages as plain Markdown, for AI
  tools.

Every warning fails the build. A broken link or a page missing from the
menu is a warning.

`uv run poe docs-clean` removes `doc/_build/`.

## Where to write what

| Change | Update |
|---|---|
| a new command | `doc/cli/<command>.md`, the lists in `doc/index.md` and `doc/cli/index.md` |
| a new option | the page of each command that takes it |
| a new `.gitnested` field | `doc/configuration/gitnested-file.md` and `doc/cli/config.md` |
| other git calls in a command | `doc/architecture/diagrams.md` |
| a new task or workflow | a page in `doc/guides/` |
| the command line | `src/git_nested/cli/spec.py` and `man/man1/git-nested.1` |

`tests/unit/test_docs.py` checks that every command, option and
`.gitnested` field appears in the docs, and every command in the manual
page.

## Layout

| Path | What |
|---|---|
| `doc/README.md` | start page on GitHub. Not part of the site |
| `doc/index.md` | start page of the site. It holds the menu |
| `doc/conf.py` | Sphinx config |
| `doc/_templates/`, `doc/_static/` | small changes to the theme |
| `doc/introduction/`, `doc/quickstart/`, … | the pages |

A new page has to be in a `toctree` in `doc/index.md`. Add a line to
`doc/README.md` too.

## Writing style

Keep it short and easy:

- Use short sentences and common words.
- Say one thing per sentence.
- Show a command, then say what it does.
- Use `ext/lib` and `https://github.com/user/lib` in examples.

## Markdown

The pages are GitHub Markdown, read by [MyST](https://myst-parser.readthedocs.io/).

- Link to other pages by their `.md` path: `[pull](../cli/pull.md)`.
- Link to a heading with `#`: `[pin](gitnested-file.md#pin)`.
- Link to files outside `doc/` with a full GitHub URL. Sphinx can not
  follow those links.
- Draw diagrams in a ` ```mermaid ` block. GitHub and the site both draw it.
- Use GitHub alerts: `> [!NOTE]`, `> [!TIP]`, `> [!WARNING]`.

## Publishing

`.github/workflows/docs.yml` builds the docs on every pull request. On a
push to `main`, it also publishes the site to the `gh_pages` branch. GitHub
Pages serves it at <https://thorsten-klein.github.io/git-nested/>.

A release tag like `1.2.0` publishes the site again. Then the site shows
the release version.

To publish by hand, start the workflow in the Actions tab, or run:

```bash
gh workflow run docs.yml
```
