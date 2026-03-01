# git-nested

> An alternative to git-submodule and git-subtree for managing nested repositories.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

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
- **Clean**: Keeps your git history squeaky clean (single commit per operation)
- **Just Works**: Users get everything with a normal `git clone` - no special setup needed
- **Flexible**: Different branches can have different nested repos in different states
- **Safe**: Easy to try and reset without breaking anything

### Limitations

- git-nested cannot handle nested-in-nested repositories as the `.gitnested` file contains upstream commits. They would not exist if git-nested works with temporary worktrees.
- git-nested squashes the commits during a `git nested pull` into one commit. Otherwise the tool cannot determine at a later point of time, that the commit was pulled or not. This feature might be added in future, so that the commit message is adapted to indicate that a commit has been pulled via git-nested.

## Quick Start

### Requirements

- Git >= 2.23
- Python >= 3.9 (for Python-based installation)

### Installation

#### Method 1: Via pip (Recommended)

```bash
pip install git+https://github.com/thorsten-klein/git-nested
```

#### Method 2: From Source with Shell Integration

Adds git-nested to PATH and enables tab completion:

```bash
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
echo 'source /path/to/git-nested/.rc' >> ~/.bashrc
source ~/.bashrc
```

#### Method 3: From Source (Manual)

```bash
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
export PATH="/path/to/git-nested/lib:$PATH"
```

> **Note:** Add the export command to your shell profile (~/.bashrc, ~/.zshrc) to make it permanent.

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

## Commands

#### `git nested help`

Show help documentation.

```bash
git nested --help
```

#### `git nested clone`

Clone an external repository into a subdirectory of your project.

```bash
git nested clone --help
```

**Example:**
```bash
git nested clone https://github.com/user/lib ext/lib -b main
```

#### `git nested init`

Turn an existing subdirectory into a nested repository.

```bash
git nested init --help
```

**Example:**
```bash
git nested init ext/mylib -r https://github.com/user/mylib
```

#### `git nested pull`

Update a nested repo with the latest upstream changes.

```bash
git nested pull --help
```

**Example:**
```bash
git nested pull ext/lib
git nested pull --all  # Pull all nested repos
```

#### `git nested push`

Push local changes back to the upstream repository.

```bash
git nested push --help
```

**Example:**
```bash
git nested push ext/lib
git nested push --all  # Push all nested repos
```

#### `git nested status`

Show the status of nested repositories.

```bash
git nested status --help
```

#### `git nested fetch`

Fetch remote content for a nested repository.

```bash
git nested fetch --help
```

#### `git nested branch`

Create a branch with local nested commits for manual conflict resolution.

```bash
git nested branch --help
```

#### `git nested commit`

Add a nested branch to current history as a single commit.

```bash
git nested commit --help
```

#### `git nested clean`

Remove temporary branches, refs, and remotes created during nested operations.

```bash
git nested clean --help
```

#### `git nested config`

Read or update the configuration of a nested repository.

```bash
git nested config --help
```

**Example:**
```bash
git nested config ext/lib method rebase
```

#### `git nested version`

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

```ini
[nested]
    filter: list                            # Clone filter (e.g., blob:none, tree:0)
    remote: https://github.com/user/repo    # Upstream repository URL
    branch: main                             # Tracked branch
    commit: abc123...                        # Current commit from upstream
    parent: def456...                        # Parent commit in main repo
    method: merge                            # Integration method (merge/rebase)
    cmdver: 1.0.0                            # git-nested version used
```

This file:
- Is committed to your parent repository
- Is **not** pushed to the nested repository's upstream
- Tracks the upstream location and current state
- Enables seamless pull/push operations

### Conflict Resolution

If a pull or push operation encounters merge conflicts, git-nested will guide you through manual resolution:

```bash
git nested fetch <subdir>   # Fetch the latest changes
git nested branch <subdir>  # Create a branch for manual resolution
# Resolve conflicts manually in your editor
git nested commit <subdir>  # Commit the resolved changes
git nested clean <subdir>   # Clean up temporary branches
```

## Development

### Setting Up Development Environment

```bash
# Install dependencies with uv (recommended)
uv sync --dev

# Or with pip
pip install -e ".[dev]"
```

### Development Workflow

```bash
# Run all checks (recommended before committing)
uv run poe all

# Or run individual checks:
uv run poe lint       # Check code quality with ruff
uv run poe format     # Format code with ruff
uv run poe test       # Run test suite with pytest
```

## Testing

### Running Tests

```bash

# Optional: Setup a venv using a specific python version
uv venv --python 3.11

# All Python tests with pytest
uv run poe test

# Specific test file
uv run poe test test/test_clone.py
# or
uv run pytest test/test_clone.py

# With verbose output
uv run poe test -vv
```

## Authors

**git-nested:**
- **Thorsten Klein** - Python rewrite and enhancements

**Original [git-subrepo](https://github.com/ingydotnet/git-subrepo) authors:**
- **Ingy döt Net** - Original concept and implementation
- **Magnus Carlsson** - Contributor
- **Austin Morgan** - Contributor

## License

MIT License

Copyright (c) 2026-present Thorsten Klein

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Acknowledgments

This project is based on [git-subrepo](https://github.com/ingydotnet/git-subrepo) by Ingy döt Net.
git-nested is a Python rewrite with some modified features and improvements.

## Resources

- **GitHub**: https://github.com/thorsten-klein/git-nested
- **Issues**: https://github.com/thorsten-klein/git-nested/issues
- **Documentation**: https://github.com/thorsten-klein/git-nested#readme

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Clone your fork locally
3. Create your feature branch (`git checkout -b feature/amazing-feature`)
4. Make your changes and add tests
5. Run all checks (`uv run poe all`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to your fork (`git push origin feature/amazing-feature`)
8. Open a Pull Request on GitHub
