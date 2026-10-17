# git-nested

<img src="https://raw.githubusercontent.com/thorsten-klein/git-nested/main/doc/_static/logo.svg" alt="logo" width="500"/>

> An alternative to git-submodule and git-subtree for managing nested repositories.

[![Test](https://github.com/thorsten-klein/git-nested/actions/workflows/test.yml/badge.svg)](https://github.com/thorsten-klein/git-nested/actions/workflows/test.yml)
[![Docs](https://github.com/thorsten-klein/git-nested/actions/workflows/docs.yml/badge.svg)](https://thorsten-klein.github.io/git-nested/)
[![codecov](https://codecov.io/gh/thorsten-klein/git-nested/branch/main/graph/badge.svg)](https://codecov.io/gh/thorsten-klein/git-nested)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=thorsten-klein_git-nested&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=thorsten-klein_git-nested)
[![PyPI](https://img.shields.io/pypi/v/git-nested.svg)](https://pypi.org/project/git-nested/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**📖 Documentation: <https://thorsten-klein.github.io/git-nested/>**

## What is git-nested?

git-nested puts another git repository into a folder of your repository.
The files are ordinary files in ordinary commits. You can still pull new
changes from the other repository, and push your changes back to it.

```bash
git nested clone https://github.com/user/lib ext/lib   # copy it in
git nested pull ext/lib                                # get new upstream changes
git nested push ext/lib                                # send your changes back
git nested status                                      # see where everything stands
```

A small `.gitnested` file in the folder remembers the URL, the branch and
the upstream commit. So the commands stay short.

## Why git-nested?

- **Self-contained.** Your repository has all files. A plain `git clone`
  gets everything. No access to the other repositories is needed.
- **Simple.** The commands feel like git.
- **Clean history.** By default one pull is one commit.
- **Flexible.** Each branch can have its nested repositories in another
  state.
- **Safe to try.** Everything is a normal commit. `git reset` undoes it.

Only people who pull or push nested repositories need git-nested. See
[Compared to submodule and subtree](https://github.com/thorsten-klein/git-nested/blob/main/doc/concepts/comparison.md).

## Install

```bash
pip install git-nested
```

git 2.23 and Python 3.10 or newer are needed. There is also a
[standalone executable](https://github.com/thorsten-klein/git-nested/blob/main/doc/introduction/install.md#standalone-executable)
that needs no Python. See [Install git-nested](https://github.com/thorsten-klein/git-nested/blob/main/doc/introduction/install.md)
for all ways, shell completion and the manual page.

## Documentation

The full documentation is in [`doc/`](https://github.com/thorsten-klein/git-nested/blob/main/doc/README.md), and online at
<https://thorsten-klein.github.io/git-nested/>.

- [About git-nested](https://github.com/thorsten-klein/git-nested/blob/main/doc/introduction/index.md)
- [git-nested in 5 minutes](https://github.com/thorsten-klein/git-nested/blob/main/doc/quickstart/05-minutes.md)
- [Everyday tasks](https://github.com/thorsten-klein/git-nested/blob/main/doc/quickstart/everyday.md)
- [How it works](https://github.com/thorsten-klein/git-nested/blob/main/doc/concepts/how-it-works.md)
- [Command reference](https://github.com/thorsten-klein/git-nested/blob/main/doc/cli/index.md)
- [The `.gitnested` file](https://github.com/thorsten-klein/git-nested/blob/main/doc/configuration/gitnested-file.md)
- [Guides](https://github.com/thorsten-klein/git-nested/blob/main/doc/README.md#guides): conflicts, partial upstreams, pins,
  submodules and more

Help on the command line:

```bash
git nested --help          # the manual page
git nested pull --help     # one command: what it does, its options, examples
```

## Contributing

Pull requests are welcome. See [Development](https://github.com/thorsten-klein/git-nested/blob/main/doc/contributing/development.md)
for the setup and the checks. The short version:

```bash
uv sync          # install everything
uv run poe all   # every check CI runs
```

Report security problems as described in [SECURITY.md](https://github.com/thorsten-klein/git-nested/blob/main/SECURITY.md).

## Authors

**git-nested:**
- **Thorsten Klein** - Python rewrite and enhancements

**Original [git-subrepo](https://github.com/ingydotnet/git-subrepo) authors:**
- **Ingy döt Net** - Original concept and implementation
- **Magnus Carlsson** - Contributor
- **Austin Morgan** - Contributor

## License

MIT. See [LICENSE](https://github.com/thorsten-klein/git-nested/blob/main/LICENSE).

## Acknowledgments

This project is based on [git-subrepo](https://github.com/ingydotnet/git-subrepo) by Ingy döt Net.
git-nested is a Python rewrite with some modified features and improvements.
