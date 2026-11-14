# `git nested diff`

Show a nested repository’s local changes against upstream.

```text
git nested diff [<options>] [<subdir>]
git nested diff --all
```

## What it does

`diff` fetches upstream first. Then it compares the committed content of
`<subdir>` with the newest upstream commit, and prints the result as a
normal git diff.

- Lines with `-` are in your copy only.
- Lines with `+` are in upstream only.

So the diff shows your local changes and the upstream changes you have not
pulled yet. `.gitnested` files are left out. With `filter`, `exclude` or
`path`, only the nested part of upstream is compared.

It reads only. Other changes in your working tree do not block it. If
`<subdir>` has uncommitted changes, `diff` warns and ignores them.

## Arguments

| Argument   | Meaning                                          |
|------------|--------------------------------------------------|
| `<subdir>` | the nested repository. Can be left out inside it |

## Options

| Option                    | Meaning                           |
|---------------------------|-----------------------------------|
| `-a`, `--all`             | diff all nested repositories      |
| `-b`, `--branch <branch>` | compare with this upstream branch |
| `-r`, `--remote <remote>` | compare with this upstream        |

## Examples

```bash
git nested diff ext/lib
git nested diff --all
git nested diff -b develop ext/lib
git nested diff ext/lib > lib.patch
```

With no difference it prints “no differences from …”. A nested repository
without a remote is skipped.

## See also

- [`status`](status.md)
