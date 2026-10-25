# `git nested fetch`

Fetch upstream content for a nested repository.

```text
git nested fetch [<options>] [<subdir>]
git nested fetch --all [<options>]
```

## What it does

`fetch` downloads the upstream branch into the ref
`refs/nested/<subdir>/fetch`. It changes no file and makes no commit.

Other commands fetch when they need to. Use `fetch` to look first, for
example with [`status`](status.md):

```bash
git nested fetch --all
git nested status --short
```

A nested repository without a remote is skipped.

## Arguments

| Argument   | Meaning                                          |
|------------|--------------------------------------------------|
| `<subdir>` | the nested repository. Can be left out inside it |

## Options

| Option                    | Meaning                                           |
|---------------------------|---------------------------------------------------|
| `-a`, `--all`             | fetch all nested repositories                     |
| `-b`, `--branch <branch>` | fetch this upstream branch instead                |
| `-r`, `--remote <remote>` | fetch from this upstream instead                  |
| `-f`, `--force`           | fetch even while a nested worktree is checked out |

## Examples

```bash
git nested fetch ext/lib
git nested fetch --all
git nested fetch --all -b release/2.0
```

With `--all -b`, a repository whose upstream has no such branch is skipped.

## Notes

- With a pin, the pinned commit is fetched. It must be on the branch.
- If the branch does not exist upstream yet, `fetch` says so. A
  [`push`](push.md) makes it.

## See also

- [`pull`](pull.md)
- [`status`](status.md)
