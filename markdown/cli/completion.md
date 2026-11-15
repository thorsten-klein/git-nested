# `git nested completion`

Print the shell completion script for git-nested.

```text
git nested completion [bash|zsh|fish]
```

## What it does

`completion` prints a script that turns on tab completion. Load it from your
shell profile.

With no shell named, git-nested guesses it from the program that started
it, and then from `$SHELL`.

The script comes from the same tables as the command line itself. So it
always matches the version you have. It completes:

- commands and options,
- values of options such as `-M`,
- nested folders,
- branch names, by asking git.

## Arguments

| Argument              | Meaning                           |
|-----------------------|-----------------------------------|
| `bash`, `zsh`, `fish` | the shell to print the script for |

## Setup

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

If you installed from source with `.rc` or `.fish.rc`, completion is on
already. See [Install git-nested](../introduction/install.md#shell-completion).
