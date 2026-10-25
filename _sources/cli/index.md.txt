# Overview and common options

```text
git nested [--version] [-q | -v | -vv] <command> [<options>] [<args>]
```

Each command has its own page. This page lists what they share.

## Commands

| Command | What it does |
|---|---|
| [`clone`](clone.md) | clone an upstream repository into a subdirectory |
| [`init`](init.md) | turn an existing subdirectory into a nested repository |
| [`pull`](pull.md) | update a nested repository from its upstream |
| [`push`](push.md) | push a nested repository's local changes upstream |
| [`fetch`](fetch.md) | fetch upstream content for a nested repository |
| [`status`](status.md) | report on the nested repositories of this repository |
| [`diff`](diff.md) | show a nested repository's local changes against upstream |
| [`branch`](branch.md) | create a branch holding the local nested commits |
| [`run`](run.md) | run a git command in the worktree of a nested repository |
| [`commit`](commit.md) | add a nested branch to the current history as one commit |
| [`repair`](repair.md) | point a nested repository's sync point back into the current history |
| [`clean`](clean.md) | remove the branches, refs and remotes nested operations created |
| [`config`](config.md) | read or write a nested repository's configuration |
| [`completion`](completion.md) | print the shell completion script for git-nested |
| [`version`](version.md) | print version information |

## Getting help

```bash
git nested --help          # the manual page
git nested pull --help     # one command: what it does, its options, examples
git nested pull -h         # the same
```

## The `<subdir>` argument

Most commands take the nested folder as their first argument.

- It is relative to the folder you are in, like git's own paths.
- It must be inside the repository. An absolute path is refused.
- Inside a nested folder you can leave it out. git-nested then uses the
  nearest nested folder at or above where you are.

```bash
git nested pull ext/lib    # from the top of the repository

cd ext/lib
git nested pull            # the same
```

`status`, `clone`, `init`, `completion` and `version` never guess the
folder.

## Options for all commands

These go **before** the command name: `git nested -v pull`, not
`git nested pull -v`.

| Option | Meaning |
|---|---|
| `-h`, `--help` | print help and stop |
| `--version` | print the git-nested version, the same as [`version`](version.md) |
| `-q`, `--quiet` | report only warnings and errors |
| `-v`, `--verbose` | narrate the steps being taken; twice to log every git command |

### How much it tells you

```bash
git nested -q pull ext/lib     # only warnings and errors
git nested pull ext/lib        # the default: what changed
git nested -v pull ext/lib     # plus each step
git nested -vv pull ext/lib    # plus every git command
```

These only change the messages about the work, on stderr. A result you may
pipe somewhere goes to stdout and is never hidden. That is the output of
`status`, `diff`, `config`, `completion`, `version` and `run`.

In a terminal git-nested also names each remote it contacts, shows git's
progress, and counts commits while it rebuilds a nested history.

### Color

Output is colored when it goes to a terminal.

- `NO_COLOR=1` turns color off.
- `FORCE_COLOR=1` keeps color on, for example in a pipe.

See [Environment variables](environment-variables.md).

### Credentials

git-nested hides the user name and password of URLs in its output. So
`https://user:token@host/repo` is shown as `https://***@host/repo`.

## Options many commands share

The details are on each command's page. In short:

| Option | Meaning |
|---|---|
| `-a`, `--all` | act on all nested repositories |
| `-A`, `--ALL` | act on all nested repositories and their sub-nesteds |
| `-b`, `--branch <branch>` | use this upstream branch for this run |
| `-r`, `--remote <remote>` | use this upstream URL or path for this run |
| `-u`, `--update` | write the `-b` / `-r` value to `.gitnested` |
| `-M`, `--method <merge\|rebase>` | the join method for this run |
| `--merge`, `--rebase` | short for `-M merge` and `-M rebase` |
| `-m`, `--message <message>` | the message of the commit git-nested makes |
| `--file <file>` | read that message from a file |
| `-F`, `--fetch` | fetch upstream first |
| `-f`, `--force` | force the operation; what it does differs per command |
| `-S`, `--gpg-sign` | GPG-sign the commits git-nested makes |
| `--signoff` | add a `Signed-off-by:` trailer |
| `--single-commit` | with `--all`: one commit for all |

### `--all` and `-b`

With `--all` the command runs once for each nested repository. Only the
outermost ones are used. A nested repository inside another one is reached
with `-A`, where the command has it.

`-b` together with `--all` works for `fetch`, `pull` and `push`. A
repository whose upstream has no such branch is skipped.

See [Many nested repositories at once](../guides/many.md).

## Exit status

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | the command failed; the reason is on stderr |
| `2` | an unknown option, or a missing argument |
| `130` | interrupted, for example with Ctrl-C |

`run` exits with the exit code of the git command it ran.
