# `git nested commit`

Add a nested branch to the current history as one commit.

```text
git nested commit [<options>] [<subdir> [<nested-commit>]]
```

## What it does

`commit` takes the nested branch and puts its content into `<subdir>`. It
updates `.gitnested` and makes one commit. Then it removes the worktree.

This is the last step of a pull you finished by hand. See
[Resolve conflicts](../guides/conflicts.md).

It needs a clean working tree, and a worktree of the nested branch.

## Arguments

| Argument | Meaning |
|---|---|
| `<subdir>` | the nested repository. Can be left out inside it |
| `<nested-commit>` | the branch or commit to add. Default: `nested/<subdir>` |

## Options

| Option | Meaning |
|---|---|
| `-F`, `--fetch` | fetch upstream first |
| `-f`, `--force` | commit even if the branch does not contain the fetched upstream commit |
| `-m`, `--message <message>` | the commit message |
| `--file <file>` | read the commit message from a file |
| `--pin <commit>` | record this pin in `.gitnested`. The help of a conflicted `pull --pin` passes it |
| `-S`, `--gpg-sign` | GPG-sign the commit |
| `--signoff` | add a `Signed-off-by:` trailer to the commit |

## Examples

```bash
git nested commit ext/lib
git nested commit --file=msg.txt ext/lib
```

## Notes

- `commit` needs the ref `refs/nested/<subdir>/fetch`. A pull or fetch makes
  it. Or pass `-F`.
- The branch must contain the fetched upstream commit. Otherwise upstream
  changes would be lost. `--force` skips this check.

## See also

- [`branch`](branch.md), [`pull`](pull.md)
