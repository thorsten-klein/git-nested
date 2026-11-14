# `git nested repair`

Point a nested repository's sync point back into the current history.

```text
git nested repair [<options>] [<subdir>]
git nested repair --all [<options>]
```

## What it does

`parent` in `.gitnested` is the sync point. A squash merge or a rebase can
leave it on a history you do not have any more. Then `repair` finds the new
sync point, writes it to `parent` and commits that.

The new sync point is the commit before the one that last changed `commit`
in `.gitnested`. That is what the pull would have recorded, had it been made
on this history.

A sync point that is still in your history is left alone.

It needs a clean working tree.

## Arguments

| Argument | Meaning |
|---|---|
| `<subdir>` | the nested repository. Can be left out inside it |

## Options

| Option | Meaning |
|---|---|
| `-a`, `--all` | repair all nested repositories |
| `-m`, `--message <message>` | the commit message |
| `--file <file>` | read the commit message from a file |
| `-S`, `--gpg-sign` | GPG-sign the commit |
| `--signoff` | add a `Signed-off-by:` trailer to the commit |

## Examples

```bash
git nested repair ext/lib
git nested repair --all
```

## Notes

You do not have to run `repair` at once. Until you do, `branch`, `pull` and
`push` find the sync point the same way, and warn about it.

## See also

- [Squash merges and rebases](../guides/squash-merges.md)
