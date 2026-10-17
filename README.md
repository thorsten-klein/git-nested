# git-nested

> An alternative to git-submodule and git-subtree for managing nested repositories.

[![Test](https://github.com/thorsten-klein/git-nested/actions/workflows/test.yml/badge.svg)](https://github.com/thorsten-klein/git-nested/actions/workflows/test.yml)
[![Docs](https://github.com/thorsten-klein/git-nested/actions/workflows/docs.yml/badge.svg)](https://thorsten-klein.github.io/git-nested/)
[![codecov](https://codecov.io/gh/thorsten-klein/git-nested/branch/main/graph/badge.svg)](https://codecov.io/gh/thorsten-klein/git-nested)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=thorsten-klein_git-nested&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=thorsten-klein_git-nested)
[![PyPI](https://img.shields.io/pypi/v/git-nested.svg)](https://pypi.org/project/git-nested/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Overview

**git-nested** lets you set up a monorepo from multiple repositories.
Each git repository is placed as a copy in a subdirectory of your project.
But it's not just a copy—you can pull upstream changes and push local modifications with simple, intuitive commands that keep your git history clean.

### How it Works

git-nested copies source code from external repositories into your project, but it's more than a simple copy.
It uses git operations and a `.gitnested` metadata file to track the relationship with the upstream repository.
This allows you to run subsequent commands (pull, push, etc.) on the copied code as if you're working with the original repository directly.

### Why git-nested?

- **Self-contained**: Your repository becomes a monorepo. No need for additional access rights to nested repositories.
- **Simple**: Intuitive commands that feel like native git
- **Clean**: Keeps your git history tidy. One commit per pull is still the default.
- **Just Works**: Users get everything with a normal `git clone` - no special setup needed
- **Flexible**: Different branches can have different nested repos in different states
- **Safe**: Easy to try and reset without breaking anything

### Nested-in-Nested Support

git-nested now supports nested repositories within nested repositories (recursive nesting) through `.gitnested.levelN` files:

- When you clone a nested repository that itself contains nested repositories, git-nested automatically creates `.gitnested.level2`, `.gitnested.level3`, etc. files
- These level files allow you to pull/push sub-nested repositories directly from the parent repository
- The nesting level is automatically detected based on existing level files in the repository
- Example: `parent/nested1/nested2` can be pulled directly with `git nested pull nested1/nested2` using its `.gitnested.level2` file

## Quick Start

### Requirements

- Git >= 2.23
- Python >= 3.10 (for Python-based installation)

### Installation

### Method 1: Via pip (Recommended)

```bash
pip install git+https://github.com/thorsten-klein/git-nested
```

### Method 2: Standalone Executable (no Python needed)

Every [release](https://github.com/thorsten-klein/git-nested/releases) ships
one archive per platform: a single file with git-nested, its dependencies and
a Python interpreter inside. Only git itself has to be installed.

| Platform | Asset |
|---|---|
| Linux (x86_64) | `git-nested-<version>-x64-linux.tar.xz` |
| macOS (Apple silicon) | `git-nested-<version>-arm64-macos.tar.xz` |
| Windows (x86_64) | `git-nested-<version>-x64-windows.zip` |

```bash
# Find the Linux asset of the latest release
ASSET=$(curl -sSL https://api.github.com/repos/thorsten-klein/git-nested/releases/latest | grep -o 'https://[^"]*x64-linux\.tar\.xz')

# Download the asset and unpack it
curl -sSL "$ASSET" | tar -xJ
sudo install git-nested /usr/local/bin/   # any directory on PATH works
```

The file has to keep the name `git-nested` (`git-nested.exe` on Windows) —
that is how `git nested ...` finds it. Each archive also contains a versioned
copy of the binary (e.g. `git-nested-1.2.3`) that `git-nested` points to.

The Linux binary is built on x86_64 with glibc 2.28, so it runs on any x86_64
Linux from that version onwards (Ubuntu 20.04, Debian 10, RHEL/AlmaLinux 8 and
newer). Not on musl distros such as Alpine.

The macOS binary is not signed, so macOS quarantines it after a download. Run
`xattr -d com.apple.quarantine git-nested` once to let it start.

### Method 3: From Source with Shell Integration

Adds git-nested to PATH and enables tab completion:

```bash
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
echo 'source /path/to/git-nested/.rc' >> ~/.bashrc
source ~/.bashrc
```

`.rc` works for bash and zsh. Fish has its own:

```fish
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
echo 'source /path/to/git-nested/.fish.rc' >> ~/.config/fish/config.fish
```

### Method 4: From Source (Manual)

```bash
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
export PATH="/path/to/git-nested/bin:$PATH"
```

> **Note:** Add the export command to your shell profile (~/.bashrc, ~/.zshrc) to make it permanent.

### Shell Completion

Method 3 turns completion on for you. With any other installation method, add
the matching line to your shell profile:

```bash
# ~/.bashrc
eval "$(git-nested completion bash)"

# ~/.zshrc  (after compinit)
eval "$(git-nested completion zsh)"
```

```fish
# ~/.config/fish/config.fish
git-nested completion fish | source
```

The script is generated by git-nested itself from the same tables its argument
parser is built from, so the offered commands, flags and values always match
the version you have installed. It completes nested repository subdirectories
and branch names too, by asking git.

### Manual Page

`git nested --help` opens the manual page, so git has to be able to find it.
Methods 3 and 4 ship it in `man/`, and `.rc` puts that on `MANPATH` for you;
otherwise add it yourself:

```bash
export MANPATH="/path/to/git-nested/man:$MANPATH"
```

The standalone tarball contains the same page under `man/man1/`.

Per-command help needs nothing set up: `git nested pull --help` and the rest
print their options and a few examples directly.

### Usage

```bash
# Clone a nested repository
git nested clone https://github.com/user/nested path/to/nested

# Pull updates from upstream
git nested pull path/to/nested

# Push local changes upstream
git nested push path/to/nested

# Check status of all nested repos
git nested status
```

git-nested works from any directory of the repository. Like git's own
pathspecs, a `<subdir>` is relative to where you are, and inside a nested
repository it can be left out:

```bash
cd path/to/nested
git nested push        # same as 'git nested push path/to/nested' from the top
```

## Commands

### Getting help

```bash
git nested --help          # the manual page
git nested pull --help     # one command: what it does, its options, examples
```

### How much it tells you

These work with every command. They only affect what git-nested says about
its work, which goes to stderr -- a result you would pipe somewhere (`status`,
`diff`, `config`, `completion`) goes to stdout and is never gated.

```bash
git nested pull ext/lib -q     # only warnings and errors
git nested pull ext/lib        # the default: what changed
git nested pull ext/lib -v     # plus each step as it is taken
git nested pull ext/lib -vv    # plus every git command that is run
```

Colour is used when the output is a terminal. `NO_COLOR=1` turns it off,
`FORCE_COLOR=1` keeps it on when piping.

### `git nested clone`

Clone an external repository into a subdirectory of your project.

```bash
git nested clone --help
```

**Example:**
```bash
git nested clone https://github.com/user/lib ext/lib -b main
git nested clone --adopt https://github.com/user/lib ext/lib
```

This also works in a fresh repository with no commits yet. The clone commit
becomes the root commit, and the first later sync records the parent.

`--exclude <path>` leaves a path of upstream out, e.g. test data. `pull`
keeps it out, and `push` never deletes it upstream. `--filter <path>` does
the opposite: it keeps only that path. Both can be given more than once.

`--path <dir>` nests only that directory of upstream, at the root of the
subdir: `--path javascript` puts upstream's `javascript/` into `ext/js/`.
`pull` takes only that directory, and `push` puts your changes back under it.

If upstream has submodules, `--recurse-submodules` nests them too. Each one
stays at the commit upstream pins. Without it they stay empty, and
git-nested says so.

`pull` keeps them nested and moves each to the commit upstream pins after
the pull. `pull --recurse-submodules` also nests new ones. `push` sends
them to upstream as submodules again.

`--adopt` keeps the tracked content that is already in `<subdir>`. It looks
for the newest upstream commit with the same tree, records that as
`commit`, records the current `HEAD` as `parent`, and commits only the new
`.gitnested` file. If no upstream commit matches, use `init -r ... --commit`.

#### `git nested init`

### `git nested init`

Turn an existing subdirectory into a nested repository.

```bash
git nested init --help
```

**Example:**
```bash
git nested init ext/mylib -r https://github.com/user/mylib
git nested init ext/mylib -r https://github.com/user/mylib --commit abc123
```

`--from-submodule` turns a submodule into a nested repository, at the same
commit and url:

```bash
git nested init --from-submodule ext/mylib
```

### `git nested pull`

`--commit <sha>` says which upstream commit the current content is based on.
That gives the next `pull` or `push` a sync point, even when the directory
already has local changes on top of that upstream commit.

#### `git nested pull`

Update a nested repo with the latest upstream changes.

If upstream rewrote its history (a force-push), `pull` stops. `pull -M rebase`
then moves your local changes onto the new history. `pull --force` takes
upstream as it is and drops them.

```bash
git nested pull --help
```

`--no-squash` keeps the upstream commits as a second parent of the pull commit.
Or set `squash: false` in `.gitnested`.
It does not work with `--filter`, `--exclude` or `--path`.

**Example:**
```bash
git nested pull ext/lib
git nested pull --no-squash ext/lib
git nested pull --all  # Pull all nested repos
```

### `git nested push`

Push local changes back to the upstream repository.
Without `--commit`, other dirty paths in the parent repo do not block it.
Dirty tracked changes in the nested subdir are warned about and ignored.

```bash
git nested push --help
```

**Example:**
```bash
git nested push ext/lib
git nested push --all  # Push all nested repos
```

### `git nested status`

Show the status of nested repositories: where each comes from, how many local
commits it has since the last sync, how many upstream commits are not pulled
yet (after a fetch), and whether its content differs from upstream.
`--short` prints one line per repository, for scripts:

```
<subdir> <local commits> <upstream commits not pulled> <changed|same>
```

`-` stands where git-nested can't tell.

```bash
git nested status --help
```

### `git nested fetch`

Fetch remote content for a nested repository.

```bash
git nested fetch --help
```

### `git nested diff`

Show the local diff of a nested repo compared to upstream. It fetches the latest upstream
content first, so it always compares against the freshest available state. Other dirty
paths in the parent repo do not block it. Dirty tracked changes in the nested subdir are
warned about and ignored.

```bash
git nested diff --help
```

**Example:**
```bash
git nested diff ext/lib
git nested diff --all  # Diff all nested repos
```

### `git nested branch`

Create a branch with local nested commits for manual conflict resolution,
checked out in a worktree under `.git/tmp/nested/<subdir>` -- or wherever
`-d <dir>` says. Pointing `-d` at the worktree of the same nested repository
rebuilds the branch there; the worktree of another one is never touched.
`--name <name>` gives the branch another name than `nested/<subdir>`; it is
recorded in `.git/config` (`nested.<subdir>.branchname`), so `run`, `commit`,
`push`, `pull` and `status` use it too, until `git nested clean` forgets it.
A `/` in `<subdir>` becomes `%2F` in the branch name: `lib/inner` gets
`nested/lib%2Finner`. So it does not clash with `nested/lib`.
A branch named `nested` blocks the `nested/<subdir>` branches. Rename it, or
use `--name`.
In a linked worktree of the repository, the branch gets the worktree's name:
`nested/lib@wt`. So worktrees do not block each other.
Other dirty paths in the parent repo do not block `branch`. Dirty tracked
changes in `<subdir>` are warned about and ignored.

```bash
git nested branch --help
```

### `git nested run`

Run a git command in the worktree that `git nested branch` created, without
changing directory: `git nested run <subdir> log` is `git -C <worktree> log`.

```bash
git nested run --help
```

### `git nested commit`

Add a nested branch to current history as a single commit.

```bash
git nested commit --help
```

### `git nested repair`

Fix the `parent` in `.gitnested` after the branch a pull or clone was made on
was squash-merged or rebased (see
[Squash merges and rebases](#squash-merges-and-rebases)).

```bash
git nested repair --help
```

### `git nested clean`

Remove temporary branches, refs, and remotes created during nested operations.
It works without `.gitnested`, e.g. after a reset undid the clone.
`clean --force --all` also removes every leftover `nested/*` branch.

```bash
git nested clean --help
```

### `git nested config`

Read or update the `.gitnested` configuration of a nested repository.

```bash
git nested config <subdir>                  # print every field the file sets
git nested config <subdir> <key>            # print one field
git nested config <subdir> <key> <value>    # set one field
```

| Key | Meaning | Writable |
| --- | --- | --- |
| `remote` | the upstream repository | yes |
| `branch` | the upstream branch | yes |
| `method` | how upstream history is joined: `merge` or `rebase` | yes |
| `parent` | the commit the nested history hangs off | yes |
| `commit` | the upstream commit currently nested | no |
| `filter` | the paths of the upstream repository that are nested | no |
| `exclude` | the paths of the upstream repository that are left out | no |

| `path` | the directory of the upstream repository that is nested, at the root of the subdir | no |
| `cmdver` | the git-nested version that last wrote this file | no |
| `readonly` | `true` makes `push` refuse, for a repository that is only pulled | yes |

The read-only keys are written by the nested operations themselves; setting one
by hand would describe a state the repository is not in. A write stages the
changed `.gitnested` file, it does not commit it.

**Example:**
```bash
git nested config ext/lib method rebase
```

### `git nested completion`

Print the shell completion script. With no argument the shell is detected from
the parent process.

```bash
git nested completion [bash|zsh|fish]
```

See [Shell Completion](#shell-completion) for how to wire it up.

### `git nested version`

Display version information.

```bash
git nested version
git nested --version
```

## Why git-nested is Better

### Comparison with git-submodule

| git-submodule | git-nested |
|---------------|------------|
| Users must manually initialize submodules | Users get everything with `git clone` |
| Pulling doesn't update submodules automatically | No special commands needed |
| Breaks if remote repo disappears | Everything in your repo history |
| Removing/renaming requires many manual steps | Different branches automatically have correct nested state |
| Dependency on external repositories | Moving/renaming remotes doesn't break your repo |

### Comparison with git-subtree

| git-subtree | git-nested |
|-------------|------------|
| Must remember remote URL for every command | Remote/branch saved in `.gitnested` file |
| Verbose command syntax | Clean, intuitive commands |
| Collaborators aren't aware of subtrees | `.gitnested` file clearly indicates nested repos |
| Creates messy history with merge commits | Clean history with single commits |
| No state file to track remote/branch | Metadata file tracks all necessary information |
| Becomes slow with many commits | Optimized performance |

### Key Benefits

#### For Users
- Get everything with one `git clone`
- No need to install git-nested
- No special commands or knowledge required
- Works with normal git workflow

#### For Collaborators
- Only install git-nested if you need to push/pull nested repos
- No access to upstream nested repositories required
- Simple, intuitive commands for contributing changes upstream
- Tab completion support

#### For Maintainers
- Create a self-contained repository
- Make atomic changes across multiple nested repositories
- No configuration required

## Working with Nested Repos

### The `.gitnested` File

Each nested repository has a `.gitnested` metadata file that tracks its relationship with upstream:

```yaml
remote: https://github.com/user/repo   # where the content comes from
branch: main                           # the branch tracked there
commit: abc123...                      # the last upstream commit taken
parent: def456...                      # your commit the two were last equal at
method: merge                          # how pulls join upstream: merge or rebase
cmdver: 1.0.0                          # the git-nested version that wrote this
filter: []                             # paths to limit the nested repo to
```

Read and write it with [`git nested config`](#git-nested-config) rather than
by hand.

This file:
- Is committed to your parent repository
- Is **not** pushed to the nested repository's upstream
- Tracks the upstream location and current state
- Enables seamless pull/push operations

### Hooks

git-nested does not run the hooks of your repository. They are for your own
changes, not for the content of an upstream. To run `pre-commit` and
`commit-msg` on git-nested's commits too:

```bash
git config nested.verify true
```

### Signing

`--signoff` adds a `Signed-off-by:` trailer to the commit git-nested makes.
`-S` signs it with GPG. For `branch`, `pull` and `push`, `-S` also signs the
nested commits git-nested rebuilds. git's `user.signingKey` picks the key.

### Conflict Resolution

If a pull or push operation encounters merge conflicts, git-nested will guide you through manual resolution:

```bash
git nested fetch <subdir>   # Fetch the latest changes
git nested branch <subdir>  # Create a branch for manual resolution
# Resolve conflicts manually in your editor
git nested commit <subdir>  # Commit the resolved changes
git nested clean <subdir>   # Clean up temporary branches
```

### Squash merges and rebases

`parent` is the commit of your repository where the nested repository and its
upstream were last equal. `branch`, `pull` and `push` rebuild the nested
history from there.

A squash merge or a rebase can leave `parent` on a history you no longer
have. Then git-nested finds the sync point in your history itself: the
commit before the one that last changed `commit` in `.gitnested`. It warns
that it does so. To record it in `.gitnested`:

```bash
git nested repair <subdir>   # or --all
```

## Development

Everything about working on git-nested -- setting up, running the tests,
the checks that have to pass, the commit message convention -- is in
[CONTRIBUTING.md](CONTRIBUTING.md). The short version:

```bash
uv sync          # install everything
uv run poe all   # the full gate: lint, types, security, complexity, tests
uv run poe test  # just the tests
```

[docs/diagrams.md](docs/diagrams.md) shows the git commands each subcommand
runs, which is the fastest way to understand what one actually does.

## Authors

**git-nested:**
- **Thorsten Klein** - Python rewrite and enhancements

**Original [git-subrepo](https://github.com/ingydotnet/git-subrepo) authors:**
- **Ingy döt Net** - Original concept and implementation
- **Magnus Carlsson** - Contributor
- **Austin Morgan** - Contributor

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgments

This project is based on [git-subrepo](https://github.com/ingydotnet/git-subrepo) by Ingy döt Net.
git-nested is a Python rewrite with some modified features and improvements.

## Resources

- **GitHub**: https://github.com/thorsten-klein/git-nested
- **Issues**: https://github.com/thorsten-klein/git-nested/issues
- **Documentation**: https://thorsten-klein.github.io/git-nested/

## Contributing

Pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to
set up, what has to pass before a change can be merged, and how commits should
be worded.
