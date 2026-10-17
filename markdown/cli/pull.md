# `git nested pull`

Update a nested repository from its upstream.

```text
git nested pull [<options>] [<subdir>]
git nested pull --all [<options>]
```

## What it does

1. Fetch the upstream branch.
2. If there is nothing new, stop and say “already up to date”.
3. Build the nested branch with your local changes.
4. Join the new upstream commits into it, by merge or by rebase.
5. Put the result into `<subdir>`, update `.gitnested` and make one commit.

The commit message lists the upstream commits it brings in, up to 20.

If step 4 has conflicts, `pull` stops and prints what to do. See
[Resolve conflicts](../guides/conflicts.md).

It needs a clean working tree.

## Arguments

| Argument   | Meaning                                          |
|------------|--------------------------------------------------|
| `<subdir>` | the nested repository. Can be left out inside it |

## Options

| Option                          | Meaning                                                           |
|---------------------------------|-------------------------------------------------------------------|
| `-a`, `--all`                   | pull all nested repositories                                      |
| `--single-commit`               | with `--all`: one commit for all of them                          |
| `-b`, `--branch <branch>`       | pull this upstream branch, just this time                         |
| `-r`, `--remote <remote>`       | pull from this upstream, just this time                           |
| `-u`, `--update`                | write the `-b` / `-r` value to `.gitnested`                       |
| `-M`, `--method <merge|rebase>` | the join method, just this time                                   |
| `--merge`, `--rebase`           | short for `-M merge` and `-M rebase`                              |
| `--no-squash`                   | keep the upstream commits as the second parent of the pull commit |
| `--pin <commit|tag>`            | move the pin to this commit or tag                                |
| `--recurse-submodules`          | also nest submodules upstream added                               |
| `-f`, `--force`                 | take upstream as it is and drop local changes                     |
| `-m`, `--message <message>`     | the commit message. Default: a generated one                      |
| `-S`, `--gpg-sign`              | GPG-sign the commits git-nested makes, nested ones too            |
| `--signoff`                     | add a `Signed-off-by:` trailer to the commit                      |

## Examples

```bash
git nested pull ext/lib
git nested pull --rebase ext/lib
git nested pull --all
git nested pull --all --single-commit
```

### Switch to another branch

Just this once:

```bash
git nested pull -b release/2.0 ext/lib
```

For good, so later pulls follow it too:

```bash
git nested pull -b release/2.0 -u ext/lib
```

The same for every nested repository whose upstream has that branch:

```bash
git nested pull --all -b release/2.0
```

### Keep the upstream history

```bash
git nested pull --no-squash ext/lib
```

The pull commit becomes a merge commit. Its second parent holds each
upstream commit, moved into `ext/lib/`. `git log ext/lib` then shows them.

To make this the default for a nested repository:

```bash
git nested config ext/lib squash false
```

`--no-squash` does not work with `filter`, `exclude` or `path`. Those
commits would bring back the files that are left out.

### Upstream rewrote its history

If upstream was force-pushed, a normal pull stops. Then pick one:

```bash
git nested pull --rebase ext/lib   # move your local changes onto the new history
git nested pull --force ext/lib    # take upstream as it is, drop your local changes
```

### Move a pin

```bash
git nested pull --pin v1.3 ext/lib
```

This is a normal pull to `v1.3`. Your local changes stay. See
[Pin a release](../guides/pin.md).

## Notes

- `-b` without `-u` does not change `.gitnested`. Only the upstream commit
  is recorded.
- A pin stays where it is on a normal pull. Only `--pin` moves it.
- Submodules of upstream that are nested already stay nested. Each one moves
  to the commit upstream pins after the pull. `--recurse-submodules` also
  nests new ones.
- A worktree left from an earlier pull blocks a new one. Finish it, or run
  [`clean`](clean.md).

## See also

- [`fetch`](fetch.md): only download, change nothing.
- [Resolve conflicts](../guides/conflicts.md)
- [How it works](../concepts/how-it-works.md#pull)
