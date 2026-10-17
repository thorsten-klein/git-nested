# Development

How to work on git-nested.

## Setup

You need [uv](https://docs.astral.sh/uv/) and git.

```bash
git clone https://github.com/YOUR_USERNAME/git-nested
cd git-nested
uv sync            # installs everything, the docs tools too
uv run poe all     # the full check, to see that your setup works
```

## Making changes

1. Branch off `main`.
2. Make your change and add tests for it.
3. Update the docs. See [Documentation](documentation.md).
4. Run `uv run poe all`.
5. Open a pull request against `main` and fill in the template.

## Tests

```text
tests/
  conftest.py   shared fixtures and the git-nested runner
  unit/         fast, no repositories: one function at a time, with fakes
  e2e/          real git repositories in a temp folder, driven through the CLI
```

Each folder is also a marker (`-m unit`, `-m e2e`). It is set by path, so a
new test file needs nothing extra.

```bash
uv run poe test                           # everything, with the coverage check
uv run poe test-unit                      # only the unit tests: seconds, no coverage check
uv run poe test tests/e2e/test_clone.py   # one file
uv run pytest -k clone                    # or pytest directly
```

`poe test` needs **100% line coverage**. A line that can not be reached gets
a `# pragma: no cover` with a comment that says why.

The tests run in parallel against real repositories, so a flaky test is
possible. To find one:

```bash
uv run poe flakefinder   # runs the suite 200 times; add -k to narrow it
```

### The standalone executable

Releases ship a single-file executable built with PyInstaller
(`scripts/create-python-exe.sh`). Freezing can break things the normal tests
do not see. So the whole suite can also run through the binary:

```bash
uv run poe test-exe   # build dist/git-nested and test it
uv run poe exe        # only build it
GIT_NESTED_EXE=dist/git-nested uv run pytest   # test a binary you have
```

CI does both. `test.yml` builds and tests the binary on every pull request.
`release-binary.yml` tests it on six Linux images before a release.

## Checks

`uv run poe all` runs every check CI runs. Each has its own task:

```bash
uv run poe lock-check   # uv.lock matches pyproject.toml
uv run poe pre-commit   # whitespace, YAML, TOML, JSON, shebangs
uv run poe lint         # ruff lint
uv run poe format       # ruff format
uv run poe mypy         # types
uv run poe pyright      # types, with a second checker
uv run poe bandit       # security lint
uv run poe pip-audit    # known holes in dependencies
uv run poe complexity   # cognitive complexity
uv run poe test         # tests with coverage
uv run poe docs         # the docs site, warnings are errors
```

## Adding a command

1. Add a module `src/git_nested/commands/<name>.py` with a `cmd_<name>`
   handler.
2. Add it to `REGISTRY` in `src/git_nested/commands/__init__.py`.
3. Add its options, help text and examples to `src/git_nested/cli/spec.py`.
4. Add tests.
5. Add `doc/cli/<name>.md`, a line in `doc/index.md` and `doc/cli/index.md`,
   the manual page `man/man1/git-nested.1`, and a diagram in
   `doc/architecture/diagrams.md`.

`tests/unit/test_docs.py` fails if a command or an option has no docs.

[Architecture](../architecture/index.md) explains how the parts fit.

## Commit messages

Use the imperative mood ("Add", not "Added"). Keep the first line under 72
characters. Name the issue where it fits.

## Reporting bugs and security issues

Open a GitHub issue with:

- the steps to reproduce it,
- what you expected and what happened,
- the output of `git nested version`.

For security problems, see
[SECURITY.md](https://github.com/thorsten-klein/git-nested/blob/main/SECURITY.md)
instead. Do not open a public issue.
