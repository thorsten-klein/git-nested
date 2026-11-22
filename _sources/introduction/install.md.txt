# Install git-nested

## Requirements

- git 2.23 or newer
- Python 3.10 or newer. The standalone executable does not need Python.

## Pick a way to install

| Way | Good for |
|---|---|
| [From PyPI](#from-pypi) | Most people |
| [Standalone executable](#standalone-executable) | Machines without Python |
| [From source, with shell setup](#from-source-with-shell-setup) | Working on git-nested |
| [From source, by hand](#from-source-by-hand) | Full control |
| [From source, editable mode](#from-source-editable-mode) | Using your own changes everywhere |

After the install, `git nested` works like any git command. git finds it
because the program is called `git-nested` and is on your `PATH`.

### From PyPI

```bash
pip install git-nested
```

Or as a tool of its own, with `uv` or `pipx`:

```bash
uv tool install git-nested
pipx install git-nested
```

To get the newest code from GitHub instead of a release:

```bash
pip install git+https://github.com/thorsten-klein/git-nested
```

### Standalone executable

Each [release](https://github.com/thorsten-klein/git-nested/releases) has
one archive per platform. The archive holds a single file with git-nested,
Python and everything else it needs. Only git has to be installed.

| Platform | Asset |
|---|---|
| Linux (x86_64) | `git-nested-<version>-x64-linux.tar.xz` |
| macOS (Apple silicon) | `git-nested-<version>-arm64-macos.tar.xz` |
| Windows (x86_64) | `git-nested-<version>-x64-windows.zip` |

On Linux:

```bash
# find the Linux asset of the newest release
ASSET=$(curl -sSL https://api.github.com/repos/thorsten-klein/git-nested/releases/latest | grep -o 'https://[^"]*x64-linux\.tar\.xz')

# download and unpack it
curl -sSL "$ASSET" | tar -xJ
sudo install git-nested /usr/local/bin/   # any folder on PATH works
```

Keep the file name `git-nested` (`git-nested.exe` on Windows). That is how
git finds it. The archive also has a copy with the version in its name, for
example `git-nested-1.2.3`.

> [!NOTE]
> The Linux binary needs glibc 2.28 or newer. It runs on Ubuntu 20.04,
> Debian 10, RHEL 8 and newer. It does not run on musl systems such as
> Alpine.

> [!NOTE]
> The macOS binary is not signed. macOS blocks it after the download. Run
> this once to allow it:
>
> ```bash
> xattr -d com.apple.quarantine git-nested
> ```

### From source, with shell setup

This puts git-nested on your `PATH`, adds the manual page and turns on tab
completion.

For bash and zsh:

```bash
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
echo 'source /path/to/git-nested/.rc' >> ~/.bashrc
source ~/.bashrc
```

For fish:

```fish
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
echo 'source /path/to/git-nested/.fish.rc' >> ~/.config/fish/config.fish
```

### From source, by hand

```bash
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
export PATH="/path/to/git-nested/bin:$PATH"
```

Add the `export` line to your shell profile (`~/.bashrc`, `~/.zshrc`) to
keep it.

### From source, editable mode

This installs git-nested from your clone. Changes to the code work right
away. You do not have to install again.

```bash
git clone https://github.com/thorsten-klein/git-nested /path/to/git-nested
pip install -e /path/to/git-nested
```

Or as a tool of its own, with `uv`:

```bash
uv tool install --editable /path/to/git-nested
```

## Shell completion

The shell setup from source turns completion on for you. For any other way,
add one line to your shell profile:

```bash
# ~/.bashrc
eval "$(git-nested completion bash)"

# ~/.zshrc, after compinit
eval "$(git-nested completion zsh)"
```

```fish
# ~/.config/fish/config.fish
git-nested completion fish | source
```

The script comes from git-nested itself. So it always matches the version
you have. It completes commands, options, nested folders and branch names.
See [`git nested completion`](../cli/completion.md).

## Manual page

`git nested --help` opens the manual page. git has to find it on your
`MANPATH`.

- The shell setup from source does this for you.
- The standalone archive has the page in `man/man1/`.
- Otherwise add it yourself:

```bash
export MANPATH="/path/to/git-nested/man:$MANPATH"
```

Help for one command needs no setup. `git nested pull --help` prints the
options and some examples.

## Check the install

```bash
git nested version
```

This prints the git-nested version, where it is installed and the git
version.

## Next step

[git-nested in 5 minutes](../quickstart/05-minutes.md)
