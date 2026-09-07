# Contributing to git-nested

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/git-nested
cd git-nested
uv sync --dev      # or: pip install -e ".[dev]"
uv run poe all     # verify your setup: the full gate
```

## Making changes

1. Branch off `main`.
2. Make your change and add tests for it.
3. Run `uv run poe all` before opening a PR.
4. Open a PR against `main` and fill out the template.

## How the tests are laid out

```
tests/
  conftest.py   shared fixtures and the git-nested runner
  unit/         fast, no repositories -- one function at a time, with fakes
  e2e/          real git repositories in a temp dir, driven through the CLI
```

Each directory is also a marker (`-m unit`, `-m e2e`), applied by path, so a
new test file needs nothing added to it.

```bash
uv run poe test         # everything, with the coverage gate
uv run poe test-unit    # just the unit tests -- seconds, no coverage gate
uv run poe test tests/e2e/test_clone.py   # one file
uv run pytest -k clone                    # or pytest directly
```

`poe test` requires **100% line coverage** and fails below it. A line that
genuinely cannot be reached gets a `# pragma: no cover` with a comment saying
why.

Tests run in parallel against real repositories, so a flake is possible. To
hunt one down:

```bash
uv run poe flakefinder   # reruns the suite 200 times; add -k to narrow it
```

### The standalone executable

Releases ship a single-file executable built with PyInstaller
(`scripts/create-python-exe.sh`). Freezing can break things the module tests
never see, so the whole suite can also run *through* the binary:

```bash
uv run poe test-exe   # build dist/git-nested and test it
uv run poe exe        # just build it
GIT_NESTED_EXE=dist/git-nested uv run pytest   # test an existing binary
```

CI does both: `test.yml` builds the binary and tests it on every PR;
`release-binary.yml` repeats that across six distro images before attaching
the asset to a release.

## Code quality

`uv run poe all` runs the full gate CI enforces. Each check has its own task:

```bash
uv run poe pre-commit   # repo hygiene: whitespace, YAML/TOML/JSON, shebangs
uv run poe lint         # ruff lint
uv run poe format       # ruff format
uv run poe mypy         # static typing
uv run poe pyright      # static typing (different checker, both must pass)
uv run poe bandit       # security linting
uv run poe pip-audit    # dependency vulnerability scan
uv run poe complexity   # cognitive complexity (complexipy)
```

## Commit messages

Imperative mood ("Add", not "Added"), first line under 72 characters,
reference issues where relevant.

## Documentation

Update [README.md](README.md) for user-facing changes and
[docs/diagrams.md](docs/diagrams.md) when a command's underlying git calls
change.

## Reporting bugs and security issues

Open a GitHub issue with steps to reproduce, expected vs. actual behaviour,
and your git-nested/git/Python versions. For security vulnerabilities, see
[SECURITY.md](SECURITY.md) instead of opening a public issue.
